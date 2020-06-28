from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import lru_cache
import os
from queue import Queue

from euclid3 import Matrix4
import imgui
import pyglet
from pyglet import gl
from pyglet.window import key
# from IPython import start_ipython

from fogl.framebuffer import FrameBuffer
from fogl.util import load_png
from fogl.shader import Program, VertexShader, FragmentShader
from fogl.texture import Texture, ImageTexture
from fogl.util import try_except_log
from fogl.vao import VertexArrayObject
from fogl.vertex import SimpleVertices

from .brush import PicBrush, RectangleBrush  #, EllipseBrush
from .config import get_autosave_filename
from .drawing import Drawing
from .imgui_pyglet import PygletRenderer
from .layer import Layer
from .plugin import init_plugins, render_plugins_ui
from .rect import Rectangle
from .render import render_drawing
from .stroke import make_stroke
from .tool import (PencilTool, PointsTool, SprayTool,
                   LineTool, RectangleTool, EllipseTool,
                   SelectionTool, PickerTool, FillTool)
from .util import (Selectable, Selectable2, make_view_matrix, show_load_dialog, show_save_dialog,
                   cache_clear, debounce, as_rgba)
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

        self.drawings = Drawings([Drawing.from_spec(s) for s in drawing_specs or []])

        self.tools = Selectable2({
            tool: tool
            for tool in [
                PencilTool, PointsTool, SprayTool,
                LineTool, RectangleTool, EllipseTool,
                FillTool,
                SelectionTool, PickerTool
            ]
        })
        self.brushes = Selectable([
            RectangleBrush((1, 1)),
            RectangleBrush((2, 2)),
            RectangleBrush((3, 3)),
            # EllipseBrush((8, 8)),
            # EllipseBrush((10, 20)),
        ])
        self.highlighted_layer = None
        self.show_selection = True

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
        self.imgui_renderer = PygletRenderer(self)
        self.icons = {
            name: ImageTexture(*load_png(f"icons/{name}.png"))
            for name in ["brush", "ellipse", "floodfill", "line", "spray",
                         "pencil", "picker", "points", "rectangle"]
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

        self.ui_state = ui.UIState()
        
        self.selection = None  # Rectangle e.g. for selecting brush region

        self.border_vao = VertexArrayObject(vertices_class=SimpleVertices)
        self.border_vertices = self.border_vao.create_vertices(
            [((0, 0, 0),),
             ((0, 0, 0),),
             ((0, 0, 0),),
             ((0, 0, 0),)])

        self.selection_vao = VertexArrayObject(vertices_class=SimpleVertices)
        self.selection_vertices = self.selection_vao.create_vertices(
            [((0, 0, 0),),
             ((0, 0, 0),),
             ((0, 0, 0),),
             ((0, 0, 0),)])

        self._new_drawing = None  # Set when configuring a new drawing
        self.unsaved_drawings = None
        self._error = None
        self.recent_files = OrderedDict((k, None) for k in recent_files)

        self.window_visibility = {
            "edits": False,
            "colors": False,
            "color_editor": False
        }

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
            self.overlay.clear(rect, frame=0)

        # TODO this works, but figure out a way to exit automatically when the application closes.
        # Thread(target=start_ipython,
        #        kwargs=dict(colors="neutral", user_ns={"drawing": self.drawing, "blah": blah})).start()

        self.plugins = {}
        init_plugins(self)

        self.keys = key.KeyStateHandler()
        self.push_handlers(self.keys)
        
    @property
    def overlay(self):
        return self.drawings.current.overlay

    @property
    def drawing(self) -> Drawing:
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
        if not self.drawing or self.drawing.locked:
            return
        if self.mouse_event_queue:
            return
        if button in (pyglet.window.mouse.LEFT,
                      pyglet.window.mouse.RIGHT):

            if self.brush_preview_dirty:
                self.overlay.clear(self.brush_preview_dirty, frame=0)
                self.brush_preview_dirty = None

            self.mouse_event_queue = Queue()
            x, y = self._to_image_coords(x, y)
            initial_point = int(x), int(y)
            self.mouse_event_queue.put(("mouse_down", initial_point, button, modifiers))
            if button == pyglet.window.mouse.LEFT:
                color = self.drawing.palette.foreground
                if isinstance(self.brush, PicBrush):
                    # Use original brush colors when drawing with a custom brush
                    brush_color = None
                else:
                    brush_color = self.drawing.palette.foreground
            else:
                # Erasing always uses background color
                color = brush_color = self.drawing.palette.background
            tool = self.tools.current(self.drawing, self.brush, color, brush_color)
            self.autosave_drawing.cancel()
            self.stroke = self.executor.submit(make_stroke, self.overlay, self.mouse_event_queue, tool)
            self.stroke.add_done_callback(lambda s: self.executor.submit(self._finish_stroke, s))
            self.stroke_tool = tool

    def on_mouse_release(self, x, y, button, modifiers):
        if self.mouse_event_queue:
            x, y = self._to_image_coords(x, y)
            pos = int(x), int(y)
            self.mouse_event_queue.put(("mouse_up", pos, button, modifiers))

    @no_imgui_events
    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        if self.keys[key.LSHIFT]:
            if scroll_y > 0:
                self.drawing.next_layer()
            else:
                self.drawing.prev_layer()
        else:
            self.change_zoom(scroll_y, (x, y))

    def on_mouse_motion(self, x, y, dx, dy):
        "Callback for mouse motion without buttons held"
        if (x, y) == self.mouse_position:
            return
        if not self.drawing:
            return
        self._update_cursor(x, y)
        if self.tools.current.brush_preview:
            self._draw_brush_preview(x - dx, y - dy, x, y)

    @no_imgui_events
    def on_mouse_drag(self, x, y, dx, dy, button, modifiers):
        "Callback for mouse movement with buttons held"
        if (x, y) == self.mouse_position:
            # The mouse hasn't actually moved; do nothing
            return
        self._update_cursor(x, y)
        if self.stroke:
            # Add to ongoing stroke
            x, y = self._to_image_coords(x, y)
            ipos = int(x), int(y)
            self.mouse_event_queue.put(("mouse_drag", ipos, button, modifiers))
        elif button == pyglet.window.mouse.MIDDLE:
            # Pan image
            self.change_offset(dx, dy)

    def on_mouse_leave(self, x, y):
        self.mouse_position = None
        if self.brush_preview_dirty:
            self.overlay.clear(self.brush_preview_dirty, frame=0)

    @no_imgui_events
    def on_key_press(self, symbol, modifiers):

        if self.stroke:
            if symbol == key.ESCAPE:
                self.mouse_event_queue.put(("abort",))
            return

        if self.drawing:

            if symbol == key.O:
                if modifiers & key.MOD_CTRL:
                    self.load_drawing()

            elif symbol == key.Z:
                self.drawing.undo()
                self.get_layer_preview_texture.cache_clear()
            elif symbol == key.Y:
                self.drawing.redo()
                self.get_layer_preview_texture.cache_clear()

            # Tools
            elif symbol == key.F:
                self.tools.select(FillTool)
            elif symbol == key.T:
                self.tools.select(PencilTool)
            elif symbol == key.I:
                self.tools.select(LineTool)
            elif symbol == key.R:
                self.tools.select(RectangleTool)
            elif symbol == key.C:
                self.tools.select(PickerTool)
            elif symbol == key.B:
                self.tools.select(SelectionTool)

            # View
            elif symbol == key.PLUS and self.mouse_position:
                self.change_zoom(1, self.mouse_position)
            elif symbol == key.MINUS and self.mouse_position:
                self.change_zoom(-1, self.mouse_position)

            elif symbol == key.LEFT:
                w, h = self.get_size()
                self.change_offset(w // 2, 0)
            elif symbol == key.RIGHT:
                w, h = self.get_size()
                self.change_offset(-w // 2, 0)
            elif symbol == key.UP:
                w, h = self.get_size()
                self.change_offset(0, -h // 2)
            elif symbol == key.DOWN:
                w, h = self.get_size()
                self.change_offset(0, h // 2)

            # Drawings
            elif symbol == key.TAB and modifiers & key.MOD_ALT:
                # TODO make this toggle to most-recently-used instead
                self.overlay.clear()
                self.drawings.cycle_forward(cyclic=True)
            elif symbol in range(48, 58):
                if symbol == 48:
                    index = 9
                else:
                    index = symbol - 49
                if len(self.drawings) > index:
                    self.drawings.select(self.drawings[index])                
                
            # Layers
            elif symbol == key.L:
                self.drawing.add_layer()
                
            elif symbol == key.V:
                if modifiers & key.MOD_SHIFT:
                    self.drawing.current.toggle_visibility()
                else:
                    self.highlighted_layer = self.drawing.layers.current
                    
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

            elif symbol == key.DELETE:
                self.drawing.clear_layer(color=self.drawing.palette.background)
                self.get_layer_preview_texture.cache_clear()
                    
            # Animation
            elif symbol == key.D:
                if modifiers & key.MOD_SHIFT:
                    self.drawing.last_frame()
                else:
                    self.drawing.next_frame()
            elif symbol == key.A:
                if modifiers & key.MOD_SHIFT:
                    self.drawing.first_frame()
                else:
                    self.drawing.prev_frame()
                    
            elif symbol == key.SPACE:
                if self.drawing.playing_animation:
                    self.drawing.stop_animation()
                else:
                    self.drawing.start_animation()

            # Misc
            elif symbol == key.C:
                self.window_visibility["colors"] = not self.window_visibility["colors"]
                
            elif symbol == key.F4:
                init_plugins(self)

            elif symbol == key.ESCAPE:
                self.drawing.brushes.current = None
                self.overlay.clear()

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

            # Draw a background rectangle
            self.update_border(self.drawing.current.rect)
            with self.border_vao, self.line_program:
                gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE, (gl.GLfloat*16)(*vm))
                r, g, b, _ = self.drawing.palette.get_color_as_float(self.drawing.palette.colors[0])
                gl.glUniform3f(1, r, g, b)
                gl.glDrawArrays(gl.GL_TRIANGLE_FAN, 0, 4)
                gl.glUniform3f(1, 0., 0., 0.)
                gl.glLineWidth(1)
                gl.glDrawArrays(gl.GL_LINE_LOOP, 0, 4)

            with self.vao, self.copy_program:
                # Draw the actual drawing
                with offscreen_buffer["color"]:
                    gl.glEnable(gl.GL_BLEND)
                    gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE, (gl.GLfloat*16)(*vm))
                    gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)

                self._draw_mouse_cursor()

            # Selection rectangle
            tool = self.stroke_tool
            selection = ((self.show_selection and self.drawing.selection)
                         or (tool and tool.show_rect and tool.rect))
            if selection:
                self.set_selection(selection)
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

    def change_zoom(self, delta, pos):
        x, y = pos
        ix, iy = self._to_image_coords(x, y)
        self.zoom = max(min(self.zoom + delta, MAX_ZOOM), MIN_ZOOM)
        x2, y2 = self._to_window_coords(ix, iy)
        self.change_offset(x - x2, y - y2)

    def change_offset(self, dx, dy):
        ox, oy = self.offset
        self.offset = ox + dx, oy + dy
        self._to_image_coords.cache_clear()

    # TODO just caching one texture here because it won't be accessed that much
    # and performance probably does not matter.
    @lru_cache(1)
    def get_layer_preview_texture(self, layer, colors, size=(32, 32)):
        w, h = layer.size
        size = w, h
        texture = Texture(size, params={gl.GL_TEXTURE_MIN_FILTER: gl.GL_LINEAR})
        texture.clear()
        data = as_rgba(layer.get_data(self.drawing.frame), colors)
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)
        gl.glTextureSubImage2D(texture.name, 0,
                               0, 0, w, h,  # min(w, bw), min(w, bh),
                               gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, data.tobytes("F"))
        return texture

    @cache_clear(get_layer_preview_texture)
    def _finish_stroke(self, stroke):
        "Callback that gets run every time a stroke is finished."
        # Since this is a callback, stroke is a Future and is guaranteed to be finished.
        self.stroke_tool = None
        tool = stroke.result()
        if tool:
            if tool.rect:
                # If no rect is set, the tool is presumed to not have changed anything.
                self.drawing.change_layer(self.overlay, tool.rect, tool.tool)
                self.overlay.clear(tool.rect, frame=0)
            else:
                self.overlay.clear(frame=0)
            if tool.restore_last:
                self.tools.restore()
        else:
            # The stroke was aborted
            self.overlay.clear()       
        self.mouse_event_queue = None
        self.stroke = None
        self.autosave_drawing()

    # === Helper functions ===

    def _render_gui(self):

        w, h = self.get_size()

        drawing = self.drawing

        imgui.new_frame()
        with imgui.font(self._font):

            self.ui_state = ui.render_main_menu(self.ui_state, self)

            # Tools & brushes

            if self.drawing:

                imgui.set_next_window_size(115, h - 20)
                imgui.set_next_window_position(w - 115, 20)

                imgui.begin("Tools", False, flags=(imgui.WINDOW_NO_TITLE_BAR
                                                   | imgui.WINDOW_NO_RESIZE
                                                   | imgui.WINDOW_NO_MOVE))

                self.ui_state = ui.render_tools(self.ui_state, self.tools, self.icons)
                imgui.core.separator()

                self.ui_state, brush = ui.render_brushes(self.ui_state, self.brushes,
                                                         self.get_brush_preview_texture,
                                                         compact=True, size=(16, 16))
                if brush:
                    self.brushes.select(brush)
                    self.drawing.brushes.current = None

                imgui.core.separator()

                imgui.begin_child("Palette", height=460)
                self.ui_state = ui.render_palette(self.ui_state, self.drawing)
                imgui.end_child()

                if drawing:
                    self.ui_state = ui.render_layers(self.ui_state, drawing)
                
                imgui.end()

                if self.window_visibility["edits"]:
                    self.ui_state = ui.render_edits(self.ui_state, self.drawing)

                # if self.window_visibility["colors"]:
                #     self.window_visibility["colors"], open_color_editor = ui.render_palette_popup(self.drawing)
                #     self.window_visibility["color_editor"] |= open_color_editor

                # nh = 150
                # imgui.set_next_window_size(w - 135, nh)
                # imgui.set_next_window_position(0, h - nh)

                # imgui.begin("Layers", False, flags=(imgui.WINDOW_NO_TITLE_BAR
                #                                     | imgui.WINDOW_NO_RESIZE
                #                                     | imgui.WINDOW_NO_MOVE))
                # ui.render_layers(self.drawing)
                # imgui.end()

                if self.ui_state.animation_settings_open:
                    self.ui_state = ui.render_animation_settings(self.ui_state, self)

                # Exit with unsaved
                ui.render_unsaved_exit(self)

            # Create new drawing
            self.ui_state = ui.render_new_drawing_popup(self.ui_state, self)
                
            if self._error:
                imgui.open_popup("Error")
                if imgui.begin_popup_modal("Error")[0]:
                    imgui.text(self._error)
                    if imgui.button("Doh!"):
                        self._error = None
                        imgui.close_current_popup()
                    imgui.end_popup()

            render_plugins_ui(self)

        imgui.render()

        imgui.end_frame()

        self.imgui_renderer.render(imgui.get_draw_data())

    def create_drawing(self, size):
        drawing = Drawing(size=size)
        self.drawings.append(drawing)

    @try_except_log
    def save_drawing(self, drawing=None, ask_for_path=False, auto=False):
        "Save the drawing, asking for a file name if neccessary."
        drawing = drawing or self.drawing
        if not ask_for_path and drawing.path:
            if drawing.path.endswith(".ora"):
                drawing.save_ora()
            elif drawing.path.endswith(".png") and len(drawing.layers) == 1:
                drawing.save_png()
            else:
                # TODO Hopefully this can't happen
                raise RuntimeError("Unknown file ending: {drawing.path}")
        else:
            last_dir = self.get_latest_dir()
            # The point here is to not block the UI redraws while showing the
            # dialog. May be a horrible idea but it seems to work...
            fut = self.executor.submit(show_save_dialog,
                                       title="Select file",
                                       initialdir=last_dir,
                                       filetypes=(("ORA files", "*.ora"),
                                                  ("PNG files", "*.png"),
                                                  ("all files", "*.*")))

            def really_save_drawing(drawing, path):
                try:
                    if path:
                        if path.endswith(".ora"):
                            drawing.save_ora(path)
                            self.add_recent_file(path)
                        elif path.endswith(".png"):
                            drawing.save_png(path)
                            self.add_recent_file(path)
                        else:
                            _, ext = os.path.splitext(path)
                            self._error = f"Could not save:\n Unsupported file format '{ext}'"
                except OSError as e:
                    self._error = f"Could not save:\n {e}"

            fut.add_done_callback(
                lambda fut: really_save_drawing(drawing, fut.result()))

    @debounce(cooldown=300, wait=3)
    def autosave_drawing(self):

        @try_except_log
        def really_autosave():
            path = self.drawing.path or self.drawing.uuid
            auto_filename = get_autosave_filename(path)
            print(f"Autosaving to {auto_filename}...")
            self.drawing.save_ora(str(auto_filename), auto=True)

        fut = self.executor.submit(really_autosave)
        fut.add_done_callback(lambda fut: print("Autosave done!"))

    def load_drawing(self, path=None):

        def really_load_drawing(path):
            if path:
                if path.endswith(".ora"):
                    drawing = Drawing.from_ora(path)
                elif path.endswith(".png"):
                    drawing = Drawing.from_png(path)
                self.drawings.append(drawing)
                self.drawings.select(drawing)
                self.add_recent_file(path)

        if path:
            really_load_drawing(path)
        else:
            last_dir = self.get_latest_dir()
            fut = self.executor.submit(show_load_dialog,
                                       title="Select file",
                                       initialdir=last_dir,
                                       filetypes=(("All image files", "*.ora"),
                                                  ("All image files", "*.png"),
                                                  ("ORA files", "*.ora"),
                                                  ("PNG files", "*.png"),
                                                  ))
            fut.add_done_callback(
                lambda fut: really_load_drawing(fut.result()))

    def _close_drawing(self):
        if self.drawing.unsaved:
            # TODO Pop up something helpful here!
            return
        self.drawing.stop_animation()
        self.drawings.remove(self.drawing)

    def _quit(self):
        unsaved = [d for d in self.drawings if d.unsaved]
        if unsaved:
            self.unsaved_drawings = unsaved
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

    @lru_cache(1)
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

    @lru_cache(1)
    def update_border(self, rect):
        x0, y0 = rect.topleft
        x1, y1 = rect.bottomright
        w, h = rect.size
        w2 = w / 2
        h2 = h / 2
        xw0 = (x0 - w2) / w
        yw0 = (h2 - y0) / h
        xw1 = (x1 - w2) / w
        yw1 = (h2 - y1) / h
        self.border_vertices.vertex_buffer.write([
            ((xw0, yw0, 0),),
            ((xw1, yw0, 0),),
            ((xw1, yw1, 0),),
            ((xw0, yw1, 0),)
        ])

    @try_except_log
    def _draw_brush_preview(self, x0, y0, x, y):
        if self.brush_preview_dirty:
            self.overlay.clear(self.brush_preview_dirty, frame=0)
        if self.drawing.locked:
            return    
        self.brush_preview_dirty = None
        io = imgui.get_io()
        if io.want_capture_mouse:
            return
        if self.stroke:
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
        overlay.clear(old_rect, frame=0)
        rect = Rectangle((ix - cx, iy - cy), brush.size)
        color = None if isinstance(self.brush, PicBrush) else self.drawing.palette.foreground
        data = brush.get_draw_data(color)
        rect = overlay.blit(data, rect, frame=0)
        
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
    def get_brush_preview_texture(self, brush, colors=None, size=(8, 8)):
        colors = colors or self.drawing.palette.as_tuple()
        bw, bh = brush.size
        w, h = size
        w, h = size = max(w, bw), max(h, bh)
        texture = Texture(size)
        texture.clear()
        data = as_rgba(brush.data, colors).tobytes("F")
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)
        gl.glTextureSubImage2D(texture.name, 0,
                               max(0, w//2-bw//2), max(0, h//2-bh//2), bw, bh, # min(w, bw), min(w, bh),
                               gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, data)
        return texture

