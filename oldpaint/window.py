from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import lru_cache, partial
import os
from queue import Queue

from euclid3 import Matrix4
import imgui
import pyglet
from pyglet import gl
from pyglet.window import key
# from IPython import start_ipython

from fogl.framebuffer import FrameBuffer
from fogl.glutil import load_png
from fogl.shader import Program, VertexShader, FragmentShader
from fogl.texture import Texture, ImageTexture
from fogl.util import try_except_log
from fogl.vao import VertexArrayObject
from fogl.vertex import SimpleVertices

from .brush import PicBrush, RectangleBrush, EllipseBrush
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
from .util import Selectable, make_view_matrix, show_load_dialog, show_save_dialog
from . import ui


MIN_ZOOM = -2
MAX_ZOOM = 5

BG_COLOR = (gl.GLfloat * 4)(0.25, 0.25, 0.25, 1)


def no_imgui_events(f):
    "Decorator for event callbacks that should ignore events on imgui windows."
    def inner(*args):
        io = imgui.get_io()
        if not (io.want_capture_mouse or io.want_capture_keyboard):
            f(*args)
    return inner


class Drawings(Selectable):
    pass


class OldpaintWindow(pyglet.window.Window):

    def __init__(self, recent_files, drawing_specs, **kwargs):

        super().__init__(**kwargs, resizable=True, vsync=False)

        self.drawings = Drawings([
            (Drawing((s[0], s[1]), layers=[Layer(LongPicture((s[0], s[1])))])
             if isinstance(s, tuple) else Drawing.from_ora(s))
            for s in drawing_specs or []
        ])
        self.tools = Selectable([
            PencilTool, PointsTool, SprayTool,
            LineTool, RectangleTool, EllipseTool, FillTool,
            SelectionTool, PickerTool
        ])
        self.brushes = Selectable([
            RectangleBrush((1, 1)),
            RectangleBrush((2, 2)),
            RectangleBrush((3, 3)),
            EllipseBrush((8, 8)),
            EllipseBrush((10, 20)),
        ])
        self.highlighted_layer = None

        # Some gl setup
        self.copy_program = Program(VertexShader("glsl/copy_vert.glsl"),
                                    FragmentShader("glsl/copy_frag.glsl"))
        self.line_program = Program(VertexShader("glsl/triangle_vert.glsl"),
                                    FragmentShader("glsl/triangle_frag.glsl"))
        self.vao = VertexArrayObject()

        # All the drawing will happen in a thread, managed by this executor
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.stroke = None
        self.stroke_tool = None
        self.mouse_event_queue = None

        # Mouse cursor setup
        self.mouse_texture = ImageTexture(*load_png("icons/cursor.png"))
        self.mouse_position = None
        self.brush_preview_dirty = None  # A hacky way to keep brush preview dirt away

        # UI stuff
        self.show_ui = None
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
            "ttf/Topaznew.ttf", 16, io.fonts.get_glyph_ranges_latin()
        )
        self.imgui_renderer.refresh_font_texture()

        style = imgui.get_style()
        style.window_border_size = 0
        style.window_rounding = 0
        io.config_resize_windows_from_edges = True  # TODO does not seem to work?

        self.selection = None  # Rectangle e.g. for selecting brush region
        self.selection_vao = VertexArrayObject(vertices_class=SimpleVertices)
        self.selection_vertices = self.selection_vao.create_vertices(
            [((0, 0, 0),),
             ((0, 0, 0),),
             ((0, 0, 0),),
             ((0, 0, 0),)])

        self._new_drawing = None  # Set when configuring a new drawing
        self._unsaved = None
        self.recent_files = OrderedDict((k, None) for k in recent_files)

        # TODO This is the basics for using tablet pressure info
        # tablets = pyglet.input.get_tablets()
        # if tablets:
        #     self.tablet = tablets[0]
        #     self.canvas = self.tablet.open(self)

        #     @self.canvas.event
        #     def on_motion(cursor, x, y, pressure, a, b):
        #         self._update_cursor(x, y)
        #         if self.mouse_event_queue:
        #             self.mouse_event_queue.put(("mouse_drag", (self._to_image_coords(x, y), 0, 0)))

        @contextmanager
        def blah():
            yield self.overlay
            rect = self.overlay.dirty
            self.drawing.update(self.overlay, rect)
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
        return self.drawing.brushes.current or self.brushes.current

    @property
    def zoom(self):
        return self.drawings.current.zoom

    @zoom.setter
    def zoom(self, zoom):
        self.drawings.current.zoom = zoom

    @property
    def offset(self):
        return self.drawings.current.offset

    @offset.setter
    def offset(self, offset):
        self.drawings.current.offset = offset

    def add_recent_file(self, filename, maxsize=10):
        self.recent_files[filename] = None
        if len(self.recent_files) > maxsize:
            for f in self.recent_files:
                del self.recent_files[f]
                break

    def get_latest_dir(self):
        if self.recent_files:
            f = list(self.recent_files.keys())[-1]
            return os.path.dirname(f)

    @no_imgui_events
    def on_mouse_press(self, x, y, button, modifiers):
        if not self.drawing:
            return
        if self.mouse_event_queue:
            return
        if button in (pyglet.window.mouse.LEFT,
                      pyglet.window.mouse.RIGHT):

            if self.brush_preview_dirty:
                self.overlay.clear(self.brush_preview_dirty)
                self.brush_preview_dirty = None

            self.mouse_event_queue = Queue()
            x, y = self._to_image_coords(x, y)
            initial_point = int(x), int(y)
            self.mouse_event_queue.put(("mouse_down", (initial_point, button, modifiers)))
            color = (self.drawing.palette.foreground if button == pyglet.window.mouse.LEFT
                     else self.drawing.palette.background)
            tool = self.tools.current(self.drawing, self.brush, color, initial_point)

            self.stroke = self.executor.submit(make_stroke, self.overlay, self.mouse_event_queue, tool)
            self.stroke.add_done_callback(lambda s: self.executor.submit(self._finish_stroke, s))
            self.stroke_tool = tool

    def on_mouse_release(self, x, y, button, modifiers):
        if self.mouse_event_queue:
            x, y = self._to_image_coords(x, y)
            pos = int(x), int(y)
            self.mouse_event_queue.put(("mouse_up", (pos, button, modifiers)))

    @no_imgui_events
    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        ox, oy = self.offset
        ix, iy = self._to_image_coords(x, y)
        self.zoom = max(min(self.zoom + scroll_y, MAX_ZOOM), MIN_ZOOM)
        self._to_image_coords.cache_clear()
        x2, y2 = self._to_window_coords(ix, iy)
        self.offset = ox + (x - x2), oy + (y - y2)
        self._to_image_coords.cache_clear()

    @no_imgui_events
    def on_mouse_drag(self, x, y, dx, dy, button, modifiers):
        if (x, y) == self.mouse_position:
            # The mouse hasn't actually moved; do nothing
            return
        self._update_cursor(x, y)
        if self.mouse_event_queue:
            x, y = self._to_image_coords(x, y)
            ipos = int(x), int(y)
            self.mouse_event_queue.put(("mouse_drag", (ipos, button, modifiers)))
        elif button == pyglet.window.mouse.MIDDLE:
            ox, oy = self.offset
            self.offset = ox + dx, oy + dy
            self._to_image_coords.cache_clear()

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
        if self.stroke:
            return

        if self.drawing:

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

            elif symbol == key.W:
                if modifiers & key.MOD_SHIFT:
                    self.drawing.move_layer_up()
                else:
                    self.drawing.next_layer()
                    self.highlighted_layer = self.drawing.layers.current
            elif symbol == key.S:
                if modifiers & key.MOD_SHIFT:
                    self.drawing.move_layer_down()
                elif modifiers & key.MOD_CTRL:
                    self.drawing and self.save_drawing()
                else:
                    self.drawing.prev_layer()
                    self.highlighted_layer = self.drawing.layers.current

            elif symbol == key.V:
                if modifiers & key.MOD_SHIFT:
                    self.drawing.current.toggle_visibility()
                else:
                    self.highlighted_layer = self.drawing.layers.current

            elif symbol == key.TAB and modifiers & key.MOD_ALT:
                # TODO make this toggle to most-recently-used instead
                self.overlay.clear()
                self.drawings.cycle_forward(cyclic=True)

    def on_key_release(self, symbol, modifiers):
        self.highlighted_layer = None

    @try_except_log
    def on_draw(self):

        gl.glClearBufferfv(gl.GL_COLOR, 0, BG_COLOR)

        if self.drawing:

            window_size = self.get_size()

            vm = make_view_matrix(window_size, self.drawing.size, self.zoom, self.offset)
            offscreen_buffer = render_drawing(self.drawing, self.highlighted_layer)

            gl.glViewport(0, 0, *window_size)

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

    def on_close(self):
        self._quit()

    # === Other callbacks ===

    def _finish_stroke(self, stroke):
        "Callback that gets run every time a stroke is finished."
        # Since this is a callback, stroke is a Future and is guaranteed to be finished.
        self.stroke_tool = None
        tool = stroke.result()
        if tool.rect:
            # If no rect is set, the tool is presumed to not have changed anything.
            self.drawing.change_layer(self.overlay, tool.rect)
            self.overlay.clear(tool.rect)
            self.get_layer_preview_texture.cache_clear()
        self.mouse_event_queue = None
        self.stroke = None

    # === Helper functions ===

    def _render_gui(self):

        w, h = self.get_size()

        drawing = self.drawing

        imgui.new_frame()
        with imgui.font(self._font):

            if imgui.begin_main_menu_bar():
                if imgui.begin_menu("File", True):

                    clicked_load, selected_load = imgui.menu_item("Load", "o", False, True)
                    if clicked_load:
                        self.load_drawing()

                    if imgui.begin_menu("Load recent...", self.recent_files):
                        for path in reversed(self.recent_files):
                            clicked, _ = imgui.menu_item(os.path.basename(path), None, False, True)
                            if clicked:
                                self.load_drawing(path)
                        imgui.end_menu()

                    imgui.separator()

                    clicked_save, selected_save = imgui.menu_item("Save", "s", False, self.drawing)
                    if clicked_save:
                        self.save_drawing()

                    clicked_save_as, selected_save = imgui.menu_item("Save as", "S", False, self.drawing)
                    if clicked_save_as:
                        self.save_drawing(ask_for_path=True)

                    imgui.separator()

                    clicked_quit, selected_quit = imgui.menu_item(
                        "Quit", 'Cmd+Q', False, True
                    )
                    if clicked_quit:
                        self._quit()

                    imgui.end_menu()

                if imgui.begin_menu("Drawing", True):
                    if imgui.menu_item("New", None, False, True)[0]:
                        self._create_drawing()

                    elif imgui.menu_item("Close", None, False, self.drawing)[0]:
                        self._close_drawing()

                    imgui.separator()

                    if imgui.menu_item("Flip horizontally", "H", False, self.drawing)[0]:
                        self.drawing.flip_horizontal()
                    if imgui.menu_item("Flip vertically", "V", False, self.drawing)[0]:
                        self.drawing.flip_vertical()

                    imgui.separator()

                    if imgui.menu_item("Undo", "z", False, self.drawing)[0]:
                        self.drawing.undo()
                    elif imgui.menu_item("Redo", "y", False, self.drawing)[0]:
                        self.drawing.redo()

                    imgui.separator()

                    for drawing in self.drawings.items:
                        if imgui.menu_item(f"{drawing.filename} {drawing.size}",
                                           None, drawing == self.drawing, True)[0]:
                            self.drawings.select(drawing)
                    imgui.end_menu()

                if imgui.begin_menu("Layer", bool(self.drawing)) :

                    layer = self.drawing.layers.current
                    index = self.drawing.layers.index(layer)
                    n_layers = len(self.drawing.layers)

                    if imgui.menu_item("Add", "L", False, True)[0]:
                        self.drawing.add_layer()
                    if imgui.menu_item("Remove", None, False, True)[0]:
                        self.drawing.remove_layer()
                    if imgui.menu_item("Merge down", None, False, index > 0)[0]:
                        self.drawing.merge_layer_down()

                    if imgui.menu_item("Toggle visibility", "v", False, True)[0]:
                        layer.visible = not layer.visible
                    if imgui.menu_item("Move up", "w", False, index < n_layers-1)[0]:
                        self.drawing.move_layer_up()
                    if imgui.menu_item("Move down", "s", False, index > 0)[0]:
                        self.drawing.move_layer_down()

                    imgui.separator()

                    if imgui.menu_item("Flip horizontally", "H", False, True)[0]:
                        self.drawing.flip_layer_horizontal()
                    if imgui.menu_item("Flip vertically", "V", False, True)[0]:
                        self.drawing.flip_layer_vertical()
                    if imgui.menu_item("Clear", "Delete", False, True)[0]:
                        self.drawing.clear()

                    imgui.separator()

                    hovered_layer = None
                    for i, layer in enumerate(reversed(self.drawing.layers)):
                        selected = self.drawing.layers.current == layer
                        index = n_layers - i - 1
                        if imgui.menu_item(f"{index} {'v' if layer.visible else ''}", str(index), selected, True)[1]:
                            self.drawing.layers.select(layer)
                        if imgui.is_item_hovered():
                            hovered_layer = layer

                            imgui.begin_tooltip()
                            texture = self.get_layer_preview_texture(layer,
                                                                     colors=self.drawing.palette.as_tuple())
                            lw, lh = texture.size
                            aspect = w / h
                            max_size = 256
                            if aspect > 1:
                                pw = max_size
                                ph = int(max_size / aspect)
                            else:
                                pw = int(max_size * aspect)
                                ph = max_size
                            imgui.image(texture.name, pw, ph, border_color=(.25, .25, .25, 1))
                            imgui.end_tooltip()

                    self.highlighted_layer = hovered_layer

                    imgui.end_menu()

                if imgui.begin_menu("Brush", bool(self.drawing)):
                    if imgui.menu_item("Save current", None, False, bool(self.drawing.brushes.current))[0]:
                        fut = self.executor.submit(show_save_dialog,
                                                   title="Select file",
                                                   filetypes=(#("ORA files", "*.ora"),
                                                       ("PNG files", "*.png"),
                                                       ("all files", "*.*")))

                        def save_brush(fut):
                            path = fut.result()
                            if path:
                                self.add_recent_file(path)
                                self.drawing.brushes.current.save_png(path, self.drawing.palette.colors)

                        fut.add_done_callback(save_brush)

                    elif imgui.menu_item("Remove", None, False, bool(self.drawing.brushes.current))[0]:
                        self.drawing.brushes.remove()

                    imgui.separator()

                    for i, brush in enumerate(reversed(self.drawing.brushes[-10:])):

                        is_selected = self.drawing.brushes.current == brush

                        bw, bh = brush.size
                        clicked, selected = imgui.menu_item(f"{bw}x{bh}", None, is_selected, True)

                        if selected:
                            self.drawing.brushes.select(brush)

                        if imgui.is_item_hovered():
                            imgui.begin_tooltip()
                            texture = self.get_brush_preview_texture(brush,
                                                                     colors=self.drawing.palette.as_tuple())
                            imgui.image(texture.name, *texture.size, border_color=(.25, .25, .25, 1))
                            imgui.end_tooltip()

                    imgui.end_menu()

                # Show some info in the right part of the menu bar

                imgui.set_cursor_screen_pos((w // 2, 0))
                drawing = self.drawing
                if drawing:
                    imgui.text(f"{drawing.filename} {drawing.size} {'*' if drawing.unsaved else ''}")

                    imgui.set_cursor_screen_pos((w - 200, 0))
                    imgui.text(f"Zoom: x{2**self.zoom}")

                    if self.mouse_position:
                        imgui.set_cursor_screen_pos((w - 100, 0))
                        x, y = self._to_image_coords(*self.mouse_position)
                        if self.stroke_tool:
                            txt = repr(self.stroke_tool)
                            if txt:
                                imgui.text(txt)
                            else:
                                imgui.text(f"{int(x)}, {int(y)}")
                        else:
                            imgui.text(f"{int(x)}, {int(y)}")

                imgui.end_main_menu_bar()

            # Tools & brushes

            if self.drawing:

                imgui.set_next_window_size(115, h - 20)
                imgui.set_next_window_position(w - 115, 20)

                imgui.begin("Tools", False, flags=(imgui.WINDOW_NO_TITLE_BAR
                                                   | imgui.WINDOW_NO_RESIZE
                                                   | imgui.WINDOW_NO_MOVE))

                ui.render_tools(self.tools, self.icons)
                imgui.core.separator()

                brush = ui.render_brushes(self.brushes,
                                          partial(self.get_brush_preview_texture,
                                                  colors=self.drawing.palette.as_tuple()),
                                          compact=True, size=(16, 16))
                if brush:
                    self.brushes.select(brush)
                    self.drawing.brushes.current = None

                imgui.core.separator()

                imgui.begin_child("Palette", height=0)
                ui.render_palette(self.drawing)
                imgui.end_child()

                # if imgui.collapsing_header("Edits", None, flags=imgui.TREE_NODE_DEFAULT_OPEN)[0]:
                #     imgui.begin_child("Edits list", height=0)
                #     self.highlighted_layer = ui.render_edits(self.drawing)
                #     imgui.end_child()

                imgui.end()

                # nh = 150
                # imgui.set_next_window_size(w - 135, nh)
                # imgui.set_next_window_position(0, h - nh)

                # imgui.begin("Layers", False, flags=(imgui.WINDOW_NO_TITLE_BAR
                #                                     | imgui.WINDOW_NO_RESIZE
                #                                     | imgui.WINDOW_NO_MOVE))
                # ui.render_layers(self.drawing)
                # imgui.end()

                # Exit with unsaved
                self._unsaved = ui.render_unsaved_exit(self._unsaved)

            # Create new drawing
            if self._new_drawing:
                imgui.open_popup("New drawing")
                imgui.set_next_window_size(200, 120)
                imgui.set_next_window_position(w // 2 - 100, h // 2 - 60)

            if imgui.begin_popup_modal("New drawing")[0]:
                imgui.text("Creating a new drawing.")
                imgui.separator()
                changed, new_size = imgui.drag_int2("Size",
                                                    *self._new_drawing["size"])
                if changed:
                    self._new_drawing["size"] = new_size
                if imgui.button("OK"):
                    drawing = Drawing(size=self._new_drawing["size"])
                    self.drawings.add(drawing)
                    self._new_drawing = None
                    imgui.close_current_popup()
                imgui.same_line()
                if imgui.button("Cancel"):
                    self._new_drawing = None
                    imgui.close_current_popup()
                imgui.end_popup()

            if self.show_ui:
                if self.show_ui == "tool_popup":
                    if ui.render_tool_menu(self.tools, self.icons):
                        self.show_ui = None

        imgui.render()
        imgui.end_frame()

        self.imgui_renderer.render(imgui.get_draw_data())

    def _create_drawing(self):
        size = self.drawing.size if self.drawing else (640, 480)
        self._new_drawing = dict(size=size)

    def save_drawing(self, ask_for_path=False):
        if not ask_for_path and self.drawing.path:
            self.drawing.save_ora()
        else:
            last_dir = self.get_latest_dir()
            # The point here is to not block the UI redraws while showing the
            # dialog. May be a horrible idea but it seems to work...
            fut = self.executor.submit(show_save_dialog,
                                       title="Select file",
                                       initialdir=last_dir,
                                       filetypes=(("ORA files", "*.ora"),
                                                  #("PNG files", "*.png"),
                                                  ("all files", "*.*")))
            fut.add_done_callback(
                lambda fut: self._really_save_drawing(fut.result()))

    def _really_save_drawing(self, path):
        if path:
            if path.endswith(".ora"):
                self.drawing.save_ora(path)
                self.add_recent_file(path)

    def load_drawing(self, path=None):
        if path:
            self._really_load_drawing(path)
        else:
            last_dir = self.get_latest_dir()
            fut = self.executor.submit(show_load_dialog,
                                       title="Select file",
                                       initialdir=last_dir,
                                       filetypes=(("ORA files", "*.ora"),
                                                  ("PNG files", "*.png"),
                                                  ("all files", "*.*")))
            fut.add_done_callback(
                lambda fut: self._really_load_drawing(fut.result()))

    def _really_load_drawing(self, path):
        if path:
            if path.endswith(".ora"):
                drawing = Drawing.from_ora(path)
            elif path.endswith(".png"):
                drawing = Drawing.from_png(path)
            self.drawings.add(drawing)
            self.drawings.select(drawing)
            self.add_recent_file(path)

    def _close_drawing(self):
        if self.drawing.unsaved:
            # TODO Pop up something helpful here!
            return
        self.drawings.remove(self.drawing)

    def _quit(self):
        unsaved = []
        for drawing in self.drawings:
            if drawing.unsaved:
                unsaved.append(drawing)
        if unsaved:
            self._unsaved = unsaved
        else:
            pyglet.app.exit()

    @lru_cache(1)
    def _get_offscreen_buffer(self, drawing):
        return FrameBuffer(drawing.size, textures=dict(color=Texture(drawing.size, unit=0)))

    @lru_cache(1)
    def _get_overlay_texture(self, overlay):
        texture = Texture(overlay.size, unit=1)
        texture.clear()
        return texture

    @lru_cache(1)
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
        if self.drawing:
            ix, iy = self._to_image_coords(x, y)
            w, h = self.drawing.size
            return 0 <= ix < w and 0 <= iy < h

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
        io = imgui.get_io()
        if io.want_capture_mouse:
            return
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
        color = None if isinstance(self.brush, PicBrush) else self.drawing.palette.foreground
        overlay.blit(brush.get_pic(color), rect)
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

        x -= ww / 2
        y -= wh / 2
        lx = x / iw / scale
        ly = y / ih / scale

        view = Matrix4().new_translate(lx, ly, 0)

        return frust * view

    @lru_cache(32)
    def get_brush_preview_texture(self, brush, colors, size=(8, 8)):
        bw, bh = brush.size
        w, h = size
        w, h = size = max(w, bw), max(h, bh)
        texture = Texture(size)
        texture.clear()
        data = brush.original.as_rgba(colors, True)
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)
        gl.glTextureSubImage2D(texture.name, 0,
                               max(0, w//2-bw//2), max(0, h//2-bh//2), bw, bh, # min(w, bw), min(w, bh),
                               gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, bytes(data))
        return texture

    @lru_cache(32)
    def get_layer_preview_texture(self, layer, colors, size=(32, 32)):
        w, h = layer.size
        size = w, h
        texture = Texture(size, params={gl.GL_TEXTURE_MIN_FILTER: gl.GL_LINEAR})
        texture.clear()
        data = layer.pic.as_rgba(colors, True)
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)
        gl.glTextureSubImage2D(texture.name, 0,
                               0, 0, w, h,  # min(w, bw), min(w, bh),
                               gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, bytes(data))
        return texture
