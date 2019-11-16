from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import lru_cache
from itertools import chain
from queue import Queue
from threading import Thread
from tkinter import Tk, filedialog

from euclid3 import Matrix4
import imgui
import pyglet
from pyglet import gl
from pyglet.window import key
# from IPython import start_ipython

from fogl.framebuffer import FrameBuffer
from fogl.glutil import load_png
from fogl.shader import Program, VertexShader, FragmentShader
from fogl.texture import Texture, ByteTexture, ImageTexture
from fogl.util import try_except_log, enabled
from fogl.vao import VertexArrayObject
from fogl.vertex import SimpleVertices

from .brush import RectangleBrush, EllipseBrush
from .drawing import Drawing
from .imgui_pyglet import PygletRenderer
from .layer import Layer
from .picture import LongPicture
from .rect import Rectangle
from .render import render_drawing
from .stroke import make_stroke
from .tool import (PencilTool, PointsTool, SprayTool,
                   LineTool, RectangleTool, EllipseTool,
                   SelectionTool, PickerTool, FillTool)
from .util import Selectable, make_view_matrix
from . import ui


MIN_ZOOM = -2
MAX_ZOOM = 5

BG_COLOR = (gl.GLfloat * 4)(0.5, 0.5, 0.5, 1)


def no_imgui_events(f):
    "Decorator for event callbacks that should ignore events on imgui windows."
    def inner(*args):
        io = imgui.get_io()
        if not io.want_capture_mouse:
            f(*args)
    return inner


class Drawings(Selectable):
    pass


class OldpaintWindow(pyglet.window.Window):

    def __init__(self, **kwargs):

        super().__init__(**kwargs, resizable=True, vsync=False)

        self.drawings = Drawings([
            Drawing((640, 480), layers=[Layer(LongPicture((640, 480))),
                                        Layer(LongPicture((640, 480))),]),
            Drawing((800, 600), layers=[Layer(LongPicture((800, 600))),
                                        Layer(LongPicture((800, 600)))])
        ])

        self.tools = Selectable([PencilTool, PointsTool, SprayTool,
                                 LineTool, RectangleTool, EllipseTool, FillTool,
                                 SelectionTool, PickerTool])
        self.brushes = Selectable([RectangleBrush((1, 1)), EllipseBrush((10, 20)), ])
        self.highlighted_layer = None
        self.drawing_brush = None

        # Some gl setup
        self.copy_program = Program(VertexShader("glsl/copy_vert.glsl"),
                                    FragmentShader("glsl/copy_frag.glsl"))
        self.line_program = Program(VertexShader("glsl/triangle_vert.glsl"),
                                    FragmentShader("glsl/triangle_frag.glsl"))
        self.vao = VertexArrayObject()

        # All the drawing will happen in a thread, managed by this executor
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.stroke = None
        self.mouse_event_queue = None

        # Keep track of what we're looking at
        self.offset = (0, 0)
        self.zoom = 0

        # Mouse cursor setup
        self.mouse_texture = ImageTexture(*load_png("icons/cursor.png"))
        self.mouse_position = None
        self.brush_preview_dirty = None  # A hacky way to keep brush preview dirt away

        # UI stuff
        self.imgui_renderer = PygletRenderer(self)
        self.icons = {
            name: ImageTexture(*load_png(f"icons/{name}.png"))
            for name in [
                    "brush", "ellipse", "floodfill", "line", "spray",
                    "pencil", "picker", "points", "rectangle"
            ]
        }

        io = imgui.get_io()
        self._font = io.fonts.add_font_from_file_ttf(
            "ttf/dpcomic.ttf", 14, io.fonts.get_glyph_ranges_latin()
        )
        self.imgui_renderer.refresh_font_texture()

        self.selection = None
        self.selection_vao = VertexArrayObject(vertices_class=SimpleVertices)
        self.selection_vertices = self.selection_vao.create_vertices(
            [((0, 0, 0),),
             ((0, 0, 0),),
             ((0, 0, 0),),
             ((0, 0, 0),)])

        # tablets = pyglet.input.get_tablets()
        # if tablets:
        #     self.tablet = tablets[0]
        #     self.canvas = self.tablet.open(self)

        #     @self.canvas.event
        #     def on_motion(cursor, x, y, pressure, a, b):
        #         self._update_cursor(x, y)
        #         if self.mouse_event_queue:
        #             self.mouse_event_queue.put(("mouse_drag", (self._to_image_coords(x, y), 0, 0)))

        Tk().withdraw() # disables TkInter GUI

        @contextmanager
        def blah():
            yield self.overlay
            rect = self.overlay.dirty
            self.drawing.update(self.overlay.get_subimage(rect), rect)
            self.overlay.clear(rect)

        # TODO this works, but figure out a way to exit automatically when the application closes.
        # Thread(target=start_ipython,
        #        kwargs=dict(colors="neutral", user_ns={"drawing": self.drawing, "blah": blah})).start()

    @property
    def overlay(self):
        return self.drawings.current.overlay

    @property
    def drawing(self):
        return self.drawings.current

    @property
    def brush(self):
        return self.drawing_brush or self.brushes.current

    @no_imgui_events
    def on_mouse_press(self, x, y, button, modifiers):
        if self.mouse_event_queue:
            return
        if button in (pyglet.window.mouse.LEFT,
                      pyglet.window.mouse.RIGHT):

            if self.brush_preview_dirty:
                self.overlay.clear(self.brush_preview_dirty)
                self.brush_preview_dirty = None

            self.mouse_event_queue = Queue()
            initial_point = self._to_image_coords(x, y)
            self.mouse_event_queue.put(("mouse_down", (initial_point, button, modifiers)))
            color = (self.drawing.palette.foreground if button == pyglet.window.mouse.LEFT
                     else self.drawing.palette.background)
            tool = self.tools.current(self.drawing, self.brush, color, initial_point)

            self.stroke = self.executor.submit(make_stroke, self.overlay, self.mouse_event_queue, tool)
            self.stroke.add_done_callback(lambda s: self.executor.submit(self._finish_stroke, s))

    def on_mouse_release(self, x, y, button, modifiers):
        if self.mouse_event_queue:
            self.mouse_event_queue.put(("mouse_up", (self._to_image_coords(x, y), button, modifiers)))
            self.mouse_event_queue = None

    @no_imgui_events
    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        ox, oy = self.offset
        ix, iy = self._to_image_coords(x, y)
        self.zoom = max(min(self.zoom + scroll_y, MAX_ZOOM), MIN_ZOOM)
        x2, y2 = self._to_window_coords(ix, iy)
        self.offset = ox + (x - x2), oy + (y - y2)

    @no_imgui_events
    def on_mouse_drag(self, x, y, dx, dy, button, modifiers):
        if (x, y) == self.mouse_position:
            # The mouse hasn't actually moved; do nothing
            return
        self._update_cursor(x, y)
        if self.mouse_event_queue:
            ipos = self._to_image_coords(x, y)
            self.mouse_event_queue.put(("mouse_drag", (ipos, button, modifiers)))
        elif button == pyglet.window.mouse.MIDDLE:
            ox, oy = self.offset
            self.offset = ox + dx, oy + dy

    def on_mouse_motion(self, x, y, dx, dy):
        if (x, y) == self.mouse_position:
            return
        self._update_cursor(x, y)
        if self.tools.current.brush_preview:
            self._draw_brush_preview(x - dx, y - dy, x, y)

    def on_mouse_leave(self, x, y):
        self.mouse_position = None
        if self.brush_preview_dirty:
            self.overlay.clear(self.brush_preview_dirty)

    def on_key_press(self, symbol, modifiers):
        if symbol == key.UP:
            self.drawing.next_layer()
        elif symbol == key.DOWN:
            self.drawing.prev_layer()
        if symbol == key.E:
            self.drawing.palette.foreground += 1
        elif symbol == key.D:
            self.drawing.palette.foreground -= 1

        elif symbol == key.DELETE:
            self.drawing.clear_layer(color=self.drawing.palette.background)

        elif symbol == key.Z:
            self.drawing.undo()
        elif symbol == key.Y:
            self.drawing.redo()

        elif symbol == key.TAB and modifiers & key.MOD_ALT:
            # TODO make this toggle to most-recently-used instead
            self.overlay.clear()
            self.drawings.cycle_forward()

        # TODO the file dialogs are blocking.
        elif symbol == key.S:
            path = filedialog.asksaveasfilename(title="Select file",
                                                filetypes=(("ORA files", "*.ora"),
                                                           #("PNG files", "*.png"),
                                                           ("all files", "*.*")))
            if path:
                if path.endswith(".ora"):
                    self.drawing.save_ora(path)
        elif symbol == key.O:
            path = filedialog.askopenfilename(title="Select file",
                                              filetypes=(("ORA files", "*.ora"),
                                                         ("PNG files", "*.png"),
                                                         ("all files", "*.*")))
            if path:
                if path.endswith(".ora"):
                    drawing = Drawing.from_ora(path)
                    self.drawings.add(drawing)
                    self.drawings.select(drawing)
                elif path.endswith(".png"):
                    self.drawing = Drawing.from_png(path)
                    self.drawings.add(drawing)
                    self.drawings.select(drawing)
        else:
            super().on_key_press(symbol, modifiers)

    @try_except_log
    def on_draw(self):

        offscreen_buffer = render_drawing(self.drawing)

        window_size = self.get_size()
        gl.glViewport(0, 0, *window_size)
        gl.glClearBufferfv(gl.GL_COLOR, 0, BG_COLOR)

        vm = make_view_matrix(window_size, self.drawing.size, self.zoom, self.offset)

        with self.vao, self.copy_program, offscreen_buffer["color"]:
            gl.glEnable(gl.GL_BLEND)
            gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE, (gl.GLfloat*16)(*vm))
            gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)

            self._draw_mouse_cursor()

        # Selection rectangle, if any
        if self.tools.current.tool == "brush" and self.drawing.selection:
            self.set_selection(self.drawing.selection)
            with self.selection_vao, self.line_program:
                gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE, (gl.GLfloat*16)(*vm))
                gl.glUniform3f(1, 1., 1., 0.)
                gl.glLineWidth(1)
                gl.glDrawArrays(gl.GL_LINE_LOOP, 0, 4)

        self._render_gui()

        gl.glFinish()  # No double buffering, to minimize latency (does this work?)

    def on_resize(self, w, h):
        return pyglet.event.EVENT_HANDLED  # Work around pyglet internals

    # === Other callbacks ===

    def _finish_stroke(self, stroke):
        # Since this is a callback, stroke is a Future and is guaranteed to be finished.
        tool = stroke.result()
        if tool.rect:
            self.drawing.update(self.overlay.get_subimage(tool.rect), tool.rect)
            self.overlay.clear(tool.rect)

        self.stroke = None

    # === Helper functions ===

    def _render_gui(self):

        imgui.new_frame()

        # with imgui.font(self._font):

        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File", True):

                clicked_quit, selected_quit = imgui.menu_item(
                    "Quit", 'Cmd+Q', False, True
                )
                if clicked_quit:
                    exit(1)

                clicked_load, selected_load = imgui.menu_item("Load", "Ctrl+F", False, True)
                if clicked_load:
                    self.dispatch_event("on_load_file")

                clicked_save, selected_save = imgui.menu_item("Save", "Ctrl+S", False, True)
                if clicked_save:
                    self.dispatch_event("on_save_file")

                imgui.end_menu()
            if imgui.begin_menu("Layer", True):
                if imgui.menu_item("Flip horizontally", "H", False, True)[0]:
                    self.drawing.current.flip_horizontal()
                if imgui.menu_item("Flip vertically", "V", False, True)[0]:
                    self.drawing.current.flip_vertical()
                if imgui.menu_item("Clear", "Delete", False, True)[0]:
                    self.drawing.current.clear()
                imgui.end_menu()
            imgui.end_main_menu_bar()

        # Tools & brushes
        imgui.begin("Tools", True)

        ui.render_tools(self.tools, self.icons)
        imgui.core.separator()

        brush = ui.render_brushes(self.brushes, self.get_brush_preview_texture)
        if brush:
            self.drawing_brush = None
        imgui.core.separator()

        if imgui.button("Delete"):
            self.drawing.brushes.remove()
        imgui.begin_child("brushes", border=False)
        brush = ui.render_brushes(self.drawing.brushes, self.get_brush_preview_texture)
        if brush:
            self.drawing_brush = brush
        imgui.end()

        imgui.end()

        self.highlighted_layer = ui.render_layers(self.drawing)
        ui.render_palette(self.drawing.palette)

        # if self.loader:
        #     if self.loader.done:
        #         self.loader = None
        #     else:
        #         ui.render_open_file_dialog(self.loader)

        # if self.saver:
        #     if self.saver.done:
        #         self.saver = None
        #     else:
        #         ui.render_save_file_dialog(self.saver)

        # ui.render_layers(self.drawing, self.get_layer_preview_texture)

        imgui.render()
        imgui.end_frame()

        self.imgui_renderer.render(imgui.get_draw_data())

    @lru_cache(1)
    def _get_offscreen_buffer(self, drawing):
        return FrameBuffer(drawing.size, textures=dict(color=Texture(drawing.size, unit=0)))

    @lru_cache(1)
    def _get_overlay_texture(self, overlay):
        texture = Texture(overlay.size, unit=1)
        texture.clear()
        return texture

    def _to_image_coords(self, x, y):
        "Convert window coordinates to image coordinates."
        w, h = self.drawing.size
        ww, wh = self.get_size()
        scale = 2 ** self.zoom
        ox, oy = self.offset
        ix = (x - (ww / 2 + ox)) / scale + w / 2
        iy = -(y - (wh / 2 + oy)) / scale + h / 2
        return ix, iy

    def _to_window_coords(self, x, y):
        "Convert image coordinates to window coordinates"
        w, h = self.drawing.size
        ww, wh = self.get_size()
        scale = 2 ** self.zoom
        ox, oy = self.offset
        wx = scale * (x - w / 2) + ww / 2 + ox
        wy = -(scale * (y - h / 2) - wh / 2 - oy)
        return wx, wy

    @lru_cache(1)
    def _over_image(self, x, y):
        ix, iy = self._to_image_coords(x, y)
        w, h = self.drawing.size
        return 0 <= ix < w and 0 <= iy < h

    #@lru_cache(128)
    def set_selection(self, rect):
        x0, y0 = rect.topleft
        x1, y1 = rect.bottomright
        w, h = self.drawing.size
        w2 = w / 2
        h2 = h / 2
        xw0 = (x0 - w2) / w
        yw0 = (h2 - y0) / h
        xw1 = (x1 - w2) / w
        yw1 = (h2 - y1) / h
        self.selection_vertices.vertex_buffer.write([
            ((xw0, yw0, 0),),
            ((xw1, yw0, 0),),
            ((xw1, yw1, 0),),
            ((xw0, yw1, 0),)
        ])

    @try_except_log
    def _draw_brush_preview(self, x0, y0, x, y):
        if self.brush_preview_dirty:
            self.overlay.clear(self.brush_preview_dirty)
        self.brush_preview_dirty = None
        if self.stroke or not self._over_image(x, y):
            return
        ix0, iy0 = self._to_image_coords(x0, y0)
        ix, iy = self._to_image_coords(x, y)
        overlay = self.overlay
        brush = self.brush
        bw, bh = brush.size
        cx, cy = brush.center
        # Clear the previous brush preview
        # TODO when leaving the image, or screen, we also need to clear
        old_rect = Rectangle((ix0 - cx, iy0 - cy), brush.size)
        overlay.clear(old_rect)
        rect = Rectangle((ix - cx, iy - cy), brush.size)
        overlay.blit(brush.get_pic(color=self.drawing.palette.foreground), rect)
        self.brush_preview_dirty = rect

    def _update_cursor(self, x, y):
        over_image = self._over_image(x, y)
        if over_image:
            io = imgui.get_io()
            if io.want_capture_mouse:
                self.mouse_position = None
                self.set_mouse_visible(True)
            else:
                self.mouse_position = x, y
                self.set_mouse_visible(False)
        else:
            self.mouse_position = None
            self.set_mouse_visible(True)

    def _draw_mouse_cursor(self):
        """ If the mouse is over the image, draw a cursom crosshair. """
        if self.mouse_position is None:
            return
        w, h = self.get_size()
        x, y = self.mouse_position
        vm = self._make_cursor_view_matrix(x, y)
        with self.mouse_texture:
            gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE_MINUS_SRC_ALPHA)
            gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE, (gl.GLfloat*16)(*vm))
            gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
            gl.glBlendFunc(gl.GL_ONE, gl.GL_ZERO)

    @lru_cache(256)
    def _make_cursor_view_matrix(self, x, y):

        "Calculate a view matrix for placing the custom cursor on screen."

        ww, wh = self.get_size()
        iw, ih = self.mouse_texture.size

        scale = 1
        width = ww / iw / scale
        height = wh / ih / scale
        far = 10
        near = -10

        frust = Matrix4()
        frust[:] = (2/width, 0, 0, 0,
                    0, 2/height, 0, 0,
                    0, 0, -2/(far-near), 0,
                    0, 0, -(far+near)/(far-near), 1)

        x -= ww // 2
        y -= wh // 2
        lx = x / iw / scale
        ly = y / ih / scale

        view = Matrix4().new_translate(lx, ly, 0)

        return frust * view

    @lru_cache(32)
    def get_brush_preview_texture(self, brush):
        texture = Texture(brush.size)

        # if isinstance(brush.original, Picture):
        #     data = bytes(brush.original.as_rgba(self.drawing.palette.colors, False).data)
        # else:
        data = bytes(brush.original.data)
        w, h = brush.size
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)
        gl.glTextureSubImage2D(texture.name, 0, 0, 0, w, h, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, data)
        return texture


@lru_cache(32)
def get_brush_preview_texture(brush):
    texture = render_brush_preview_texture(brush)
    print("create brush texture", texture)
    return texture


def render_brush_preview_texture(brush, colors):
    texture = Texture(brush.size)
    #brush.original.putpalette(self.drawing.palette.get_pil_palette())  # TODO do this when palette changes
    #brush.set_palette(self.drawing.palette)
    #rawdata = brush.original.convert("RGBA").getdata()
    rgbdata = brush.original.as_rgba(self.drawing.palette.colors, False).data
    # TODO alpha mask
    data = (gl.GLuint * len(rgbdata))(*rgbdata)
    w, h = brush.size
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)
    gl.glTextureSubImage2D(texture.name, 0, 0, 0, w, h, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, data)
    return texture
