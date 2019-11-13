from concurrent.futures import ThreadPoolExecutor
import ctypes
from functools import lru_cache
from itertools import chain
from queue import Queue
from time import time

from euclid3 import Matrix4
import imgui
import pyglet
from pyglet import gl
from pyglet.window import key

from ugly.framebuffer import FrameBuffer
from ugly.glutil import gl_matrix, load_png
from ugly.shader import Program, VertexShader, FragmentShader
from ugly.texture import Texture, ByteTexture, ImageTexture
from ugly.util import try_except_log, enabled
from ugly.vao import VertexArrayObject
from ugly.vertex import SimpleVertices

from .brush import RectangleBrush, EllipseBrush
from .imgui_pyglet import PygletRenderer
from .layer import Layer
from .picture import Picture, LongPicture
from .rect import Rectangle
from .stack import Stack
from .stroke import make_stroke
from .tool import (PencilTool, PointsTool, LineTool, RectangleTool, EllipseTool,
                   SelectionTool, PickerTool, FillTool)
from .util import Selectable
from . import ui


BG_COLOR = (gl.GLfloat * 4)(0.5, 0.5, 0.5, 1)
ZERO_COLOR = (gl.GLfloat * 4)(0, 0, 0, 0)

MIN_ZOOM = -2
MAX_ZOOM = 5


def no_imgui_events(f):
    "Decorator for event callbacks that should ignore events on imgui windows."
    def inner(*args):
        io = imgui.get_io()
        if not io.want_capture_mouse:
            f(*args)
    return inner


class OldpaintWindow(pyglet.window.Window):

    def __init__(self, **kwargs):

        super().__init__(**kwargs, resizable=True, vsync=False)

        size = (1600, 1200)
        self.stack = Stack(size, layers=[Layer(Picture(size)), Layer(Picture(size))])
        self.overlay = Layer(LongPicture(size))  # A temporary drawing layer

        self.offscreen_buffer = FrameBuffer(size, textures=dict(color=Texture(size, unit=0)))
        self.vao = VertexArrayObject()

        self.draw_program = Program(VertexShader("glsl/palette_vert.glsl"),
                                    FragmentShader("glsl/palette_frag.glsl"))
        self.copy_program = Program(VertexShader("glsl/copy_vert.glsl"),
                                    FragmentShader("glsl/copy_frag.glsl"))
        self.line_program = Program(VertexShader("glsl/triangle_vert.glsl"),
                                    FragmentShader("glsl/triangle_frag.glsl"))

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
                    "brush", "ellipse", "floodfill", "line",
                    "pencil", "picker", "points", "rectangle"
            ]
        }
        self.tools = Selectable([PencilTool, PointsTool,
                                 LineTool, RectangleTool, EllipseTool, FillTool,
                                 SelectionTool, PickerTool])
        self.brushes = Selectable([RectangleBrush((1, 1)), EllipseBrush((10, 20)), ])
        self.highlighted_layer = None

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

        self.loader = None
        self.saver = None

        # tablets = pyglet.input.get_tablets()
        # if tablets:
        #     self.tablet = tablets[0]
        #     self.canvas = self.tablet.open(self)

        #     @self.canvas.event
        #     def on_motion(cursor, x, y, pressure, a, b):
        #         self._update_cursor(x, y)
        #         if self.mouse_event_queue:
        #             self.mouse_event_queue.put(("mouse_drag", (self._to_image_coords(x, y), 0, 0)))

    @no_imgui_events
    def on_mouse_press(self, x, y, button, modifiers):
        if self.mouse_event_queue:
            return
        if button in (pyglet.window.mouse.LEFT,
                      pyglet.window.mouse.RIGHT):
            self.mouse_event_queue = Queue()
            color = (self.stack.palette.foreground if button == pyglet.window.mouse.LEFT
                     else self.stack.palette.background)
            tool = self.tools.current(self.stack, self.brushes.current, color, self._to_image_coords(x, y))
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
        self._draw_brush_preview(x - dx, y - dy, x, y)

    def on_mouse_leave(self, x, y):
        self.mouse_position = None
        if self.brush_preview_dirty:
            self.overlay.clear(self.brush_preview_dirty)

    def on_key_press(self, symbol, modifiers):
        if symbol == key.UP:
            self.stack.next_layer()
        elif symbol == key.DOWN:
            self.stack.prev_layer()
        if symbol == key.E:
            self.stack.palette.foreground += 1
        elif symbol == key.D:
            self.stack.palette.foreground -= 1

        elif symbol == key.DELETE:
            self.stack.clear_layer(color=self.stack.palette.background)

        elif symbol == key.Z:
            self.stack.undo()
        elif symbol == key.Y:
            self.stack.redo()

        elif symbol == key.S:
            self.stack.save_ora("/tmp/hej.ora")

        else:
            super().on_key_press(symbol, modifiers)

    @try_except_log
    def on_draw(self):

        with self.vao, self.offscreen_buffer, self.draw_program:
            w, h = self.offscreen_buffer.size
            gl.glViewport(0, 0, w, h)
            gl.glDisable(gl.GL_BLEND)
            gl.glClearBufferfv(gl.GL_COLOR, 0, ZERO_COLOR)

            gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)

            stack = self.stack

            overlay = self.overlay
            overlay_texture = self._get_overlay_texture(overlay)

            if overlay.dirty and overlay.lock.acquire(timeout=0.03):
                # Since we're drawing in a separate thread, we need to be very careful
                # when accessing the overlay, otherwise we can get nasty problems.
                # While we have the lock, the thread won't draw, so we can safely copy data.
                rect = overlay.dirty
                subimage = overlay.get_subimage(rect)
                data = bytes(subimage.data)  # TODO Is this making a copy?

                # Now update the texture with the changed part of the layer.
                gl.glTextureSubImage2D(overlay_texture.name, 0, *rect.points,
                                       gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, data)

                overlay.dirty = None
                overlay.lock.release()  # Allow layer to change again.

            for layer in self.stack:

                if not self.highlighted_layer or self.highlighted_layer == layer:

                    layer_texture = self._get_layer_texture(layer)
                    if layer.dirty and layer.lock.acquire(timeout=0.03):
                        rect = layer.dirty
                        subimage = layer.get_subimage(rect)
                        data = bytes(subimage.data)
                        gl.glTextureSubImage2D(layer_texture.name, 0, *rect.points,
                                               gl.GL_RED, gl.GL_UNSIGNED_BYTE, data)

                        layer.dirty = None
                        layer.lock.release()

                    if not layer.visible:
                        continue

                    with layer_texture:
                        if layer == stack.current:
                            # The overlay is combined with the layer
                            with overlay_texture:
                                gl.glUniform4fv(1, 256, self._get_colors(stack.palette.get_rgba()))
                                gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
                        else:
                            with self._get_empty_texture(stack):
                                gl.glUniform4fv(1, 256, self._get_colors(stack.palette.get_rgba()))
                                gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)

        window_size = self.get_size()
        gl.glViewport(0, 0, *window_size)
        gl.glClearBufferfv(gl.GL_COLOR, 0, BG_COLOR)

        vm = make_view_matrix(window_size, stack.size, self.zoom, self.offset)

        with self.vao, self.copy_program, self.offscreen_buffer["color"]:
            gl.glEnable(gl.GL_BLEND)
            gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE, (gl.GLfloat*16)(*vm))
            gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)

            self._draw_mouse_cursor()

        # Selection rectangle, if any
        if self.tools.current.tool == "brush" and self.stack.selection:
            self.set_selection(self.stack.selection)
            with self.selection_vao, self.line_program:
                gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE, (gl.GLfloat*16)(*vm))
                gl.glUniform3f(1, 1., 1., 0.)
                gl.glLineWidth(1)
                gl.glDrawArrays(gl.GL_LINE_LOOP, 0, 4)

        self._render_gui()

        # gl.glFinish()  # No double buffering, to minimize latency (does this work?)

    def on_resize(self, w, h):
        return pyglet.event.EVENT_HANDLED  # Work around pyglet internals

    # === Other callbacks ===

    def _finish_stroke(self, stroke):
        # Since this is a callback, stroke is a Future and is guaranteed to be finished.
        tool = stroke.result()
        print("stroke finished", tool.rect)
        if tool.rect:
            self.stack.update(self.overlay.get_subimage(tool.rect), tool.rect)
            self.overlay.clear(tool.rect)

        # if tool.rect:
        #     #self.stack.update(self.overlay.get_subimage(tool.rect), tool.rect)
        #     self.overlay.clear(tool.rect)
        self.stroke = None
        # TODO here we should handle undo history etc

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
                    self.stack.current.flip_horizontal()
                if imgui.menu_item("Flip vertically", "V", False, True)[0]:
                    self.stack.current.flip_vertical()
                if imgui.menu_item("Clear", "Delete", False, True)[0]:
                    self.stack.current.clear()
                imgui.end_menu()
            imgui.end_main_menu_bar()

        imgui.begin("Tools", True)

        ui.render_tools(self.tools, self.icons)
        #imgui.core.separator()
        imgui.end()

        ui.render_brushes(self.brushes, self.stack.brushes, self.get_brush_preview_texture)

        self.highlighted_layer = ui.render_layers(self.stack)
        ui.render_palette(self.stack.palette)

        if self.loader:
            if self.loader.done:
                self.loader = None
            else:
                ui.render_open_file_dialog(self.loader)

        if self.saver:
            if self.saver.done:
                self.saver = None
            else:
                ui.render_save_file_dialog(self.saver)

        # ui.render_layers(self.stack, self.get_layer_preview_texture)

        imgui.render()
        imgui.end_frame()

        self.imgui_renderer.render(imgui.get_draw_data())

    @lru_cache(1)
    def _get_colors(self, colors):
        colors = chain.from_iterable(colors)
        return (gl.GLfloat*(4*256))(*colors)

    @lru_cache(1)
    def _get_empty_texture(self, stack):
        texture = Texture(stack.size, unit=1)
        texture.clear()
        return texture

    @lru_cache(1)
    def _get_overlay_texture(self, overlay):
        texture = Texture(overlay.size, unit=1)
        texture.clear()
        return texture

    @lru_cache(32)
    def _get_layer_texture(self, layer):
        texture = ByteTexture(layer.size)
        texture.clear()
        return texture

    def _to_image_coords(self, x, y):
        "Convert window coordinates to image coordinates."
        w, h = self.stack.size
        ww, wh = self.get_size()
        scale = 2 ** self.zoom
        ox, oy = self.offset
        ix = (x - (ww / 2 + ox)) / scale + w / 2
        iy = -(y - (wh / 2 + oy)) / scale + h / 2
        return ix, iy

    def _to_window_coords(self, x, y):
        "Convert image coordinates to window coordinates"
        w, h = self.stack.size
        ww, wh = self.get_size()
        scale = 2 ** self.zoom
        ox, oy = self.offset
        wx = scale * (x - w / 2) + ww / 2 + ox
        wy = -(scale * (y - h / 2) - wh / 2 - oy)
        return wx, wy

    @lru_cache(1)
    def _over_image(self, x, y):
        ix, iy = self._to_image_coords(x, y)
        w, h = self.stack.size
        return 0 <= ix < w and 0 <= iy < h

    #@lru_cache(128)
    def set_selection(self, rect):
        x0, y0 = rect.topleft
        x1, y1 = rect.bottomright
        w, h = self.stack.size
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
        brush = self.brushes.current
        bw, bh = brush.size
        cx, cy = brush.center
        # Clear the previous brush preview
        # TODO when leaving the image, or screen, we also need to clear
        old_rect = Rectangle((ix0 - cx, iy0 - cy), brush.size)
        overlay.clear(old_rect)
        rect = Rectangle((ix - cx, iy - cy), brush.size)
        overlay.blit(brush.get_pic(color=self.stack.palette.foreground), rect)
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

        if isinstance(brush.original, Picture):
            data = bytes(brush.original.as_rgba(self.stack.palette.colors, False).data)
        else:
            data = bytes(brush.original.data)
        w, h = brush.size
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)
        gl.glTextureSubImage2D(texture.name, 0, 0, 0, w, h, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, data)
        return texture


@lru_cache(1)
def make_view_matrix(window_size, image_size, zoom, offset):
    "Calculate a view matrix that places the image on the screen, at scale."
    ww, wh = window_size
    iw, ih = image_size

    scale = 2**zoom
    width = ww / iw / scale
    height = wh / ih / scale
    far = 10
    near = -10

    frust = Matrix4()
    frust[:] = (2/width, 0, 0, 0,
                0, 2/height, 0, 0,
                0, 0, -2/(far-near), 0,
                0, 0, -(far+near)/(far-near), 1)

    x, y = offset
    lx = x / iw / scale
    ly = y / ih / scale

    view = (Matrix4()
            .new_translate(lx, ly, 0))

    return frust * view


@lru_cache(1)
def make_view_matrix_inverse(window_size, image_size, zoom, offset):
    return make_view_matrix(window_size, image_size, zoom, offset).inverse()


@lru_cache(32)
def get_brush_preview_texture(brush):
    texture = render_brush_preview_texture(brush)
    print("create brush texture", texture)
    return texture


def render_brush_preview_texture(brush, colors):
    texture = Texture(brush.size)
    #brush.original.putpalette(self.stack.palette.get_pil_palette())  # TODO do this when palette changes
    #brush.set_palette(self.stack.palette)
    #rawdata = brush.original.convert("RGBA").getdata()
    rgbdata = brush.original.as_rgba(self.stack.palette.colors, False).data
    # TODO alpha mask
    data = (gl.GLuint * len(rgbdata))(*rgbdata)
    w, h = brush.size
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)
    gl.glTextureSubImage2D(texture.name, 0, 0, 0, w, h, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, data)
    return texture
