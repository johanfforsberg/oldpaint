from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import lru_cache
import logging
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

from .brush import PicBrush, RectangleBrush, EllipseBrush
from .drawing import Drawing
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


logger = logging.getLogger(__name__)


MIN_ZOOM = -2
MAX_ZOOM = 5

BG_COLOR = (gl.GLfloat * 4)(0.25, 0.25, 0.25, 1)
EYE4 = (gl.GLfloat*16)(1, 0, 0, 0,
                       0, 1, 0, 0,
                       0, 0, 1, 0,
                       0, 0, 0, 1)

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
 
        super().__init__(**kwargs, caption="Oldpaint", resizable=True, vsync=False)
        
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
            EllipseBrush((8, 8)),
            EllipseBrush((20, 35)),
        ])
        self.highlighted_layer = None
        # self.show_selection = False

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

        # Background texture
        #self.background_texture = ImageTexture(*load_png("icons/background.png"))
        
        # UI stuff
        self.icons = {
            name: ImageTexture(*load_png(f"icons/{name}.png"))
            for name in ["selection", "ellipse", "floodfill", "line", "spray",
                         "pencil", "picker", "points", "rectangle"]
        }

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
            "color_editor": False,
            "metrics": False
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
    def scale(self):
        return 2**self.zoom

    @property
    def offset(self):
        return self.drawings.current.offset

    @offset.setter
    def offset(self, offset):
        dx, dy = offset
        self.drawings.current.offset = round(dx), round(dy)

    @lru_cache(1)
    def get_background_texture(self, color, contrast=1):
        r, g, b, _ = color
        return ImageTexture((2, 2), [round(r*contrast), round(g*contrast), round(b*contrast), 255,
                                     r, g, b, 255,
                                     r, g, b, 255,
                                     round(r*contrast), round(g*contrast), round(b*contrast), 255])
        
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

    @property
    def selection(self):
        if self.drawing.selection and self.tools.current == SelectionTool:
            return self.drawing.selection
        
    @no_imgui_events
    def on_mouse_press(self, x, y, button, modifiers):
        if not self.drawing or self.drawing.locked or self.selection:
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
            self.stroke = self.executor.submit(make_stroke, self.overlay, self.mouse_event_queue, tool)
            self.stroke.add_done_callback(lambda s: self.executor.submit(self._finish_stroke, s))
            self.stroke_tool = tool
            self.autosave_drawing.cancel()  # No autosave while drawing

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

        if symbol == key.Q and modifiers & key.MOD_CTRL:
            self._quit()

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
                
            elif symbol == key.SPACE:
                self.tools.select(SelectionTool)

            elif symbol == key.B:
                if self.selection:
                    self.drawing.make_brush()
                    self.tools.restore()

            elif symbol == key.ESCAPE:
                if self.selection:
                    self.tools.restore()
                    
            # View
            elif symbol == key.PLUS and self.mouse_position:
                self.change_zoom(1, self.mouse_position)
            elif symbol == key.MINUS and self.mouse_position:
                self.change_zoom(-1, self.mouse_position)

            elif symbol == key.LEFT:
                w, h = self.get_pixel_aligned_size()
                self.change_offset(w // 2, 0)
            elif symbol == key.RIGHT:
                w, h = self.get_pixel_aligned_size()
                self.change_offset(-w // 2, 0)
            elif symbol == key.UP:
                w, h = self.get_pixel_aligned_size()
                self.change_offset(0, -h // 2)
            elif symbol == key.DOWN:
                w, h = self.get_pixel_aligned_size()
                self.change_offset(0, h // 2)

            # # Drawings
            # elif symbol == key.D and modifiers & key.MOD_SHIFT:
            #     self.new_drawing()
            
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
                    
            elif symbol == key.COMMA:
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
        
    def get_pixel_aligned_size(self):
        return self._get_pixel_aligned_size(self.get_size(), self.zoom)

    @staticmethod
    @lru_cache(1)
    def _get_pixel_aligned_size(window_size, zoom):
        # Force window dimensions down to nearest even multiple of the pixel size, to avoid alignment issues.
        # TODO This is kind of a hack; does it have negative consequences?
        s2 = 2 ** (zoom + 1)
        ww, wh = window_size
        ww2 = (ww // s2) * s2
        wh2 = (wh // s2) * s2
        return ww2, wh2

    @try_except_log
    def on_draw(self):

        gl.glClearBufferfv(gl.GL_COLOR, 0, BG_COLOR)

        if self.drawing:

            window_size = self.get_pixel_aligned_size()
            w, h = self.drawing.size

            vm = (gl.GLfloat*16)(*make_view_matrix(window_size, self.drawing.size, self.zoom, self.offset))
            offscreen_buffer = render_drawing(self.drawing, self.highlighted_layer)

            ww, wh = window_size
            gl.glViewport(0, 0, int(ww), int(wh))

            # Draw a background rectangle
            with self.vao, self.copy_program:
                gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE, (gl.GLfloat*16)(*vm))                
                if self.drawing and self.drawing.grid:
                    with self.get_background_texture(self.drawing.palette.colors[0], 0.9):
                        gw, gh = self.drawing.grid_size
                        gl.glUniform2f(1, w / (gw * 2), h / (gh * 2))
                        gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE_MINUS_SRC_ALPHA)
                        gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
                else:
                    #gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
                    # r, g, b, _ = self.drawing.palette.get_color_as_float(self.drawing.palette.colors[0])
                    # gl.glClearColor(r, g, b, 1)
                    # TODO should fill with color 0 here!
                    # gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
                    with self.get_background_texture(self.drawing.palette.colors[0], 1):
                        gw, gh = self.drawing.grid_size
                        gl.glUniform2f(1, w / (gw * 2), h / (gh * 2))
                        gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE_MINUS_SRC_ALPHA)
                        gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
                    

                with offscreen_buffer["color"]:
                    gl.glUniform2f(1, 1, 1)
                    gl.glEnable(gl.GL_BLEND)
                    gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE_MINUS_SRC_ALPHA)
                    gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE, vm)
                    gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
                    
            with self.line_program:
                with self.border_vao:
                    self.update_border(self.drawing.current.rect)
                    gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE, vm)
                    # r, g, b, _ = self.drawing.palette.get_color_as_float(self.drawing.palette.colors[0])
                    # gl.glUniform3f(1, r, g, b)
                    # gl.glDrawArrays(gl.GL_TRIANGLE_FAN, 0, 4)
                    gl.glUniform3f(1, 0., 0., 0.)
                    gl.glLineWidth(1)
                    gl.glDrawArrays(gl.GL_LINE_LOOP, 0, 4)

                # Selection rectangle
                tool = self.stroke_tool
                selection = ((tool and tool.show_rect and tool.rect) or self.selection)
                if selection:
                    self.set_selection(selection)
                    with self.selection_vao:
                        gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE, vm)
                        gl.glUniform3f(1, 1., 1., 0.)
                        gl.glLineWidth(1)
                        gl.glDrawArrays(gl.GL_LINE_LOOP, 0, 4)

        self._draw_mouse_cursor()                    

        ui.draw_ui(self)

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

    def new_drawing(self, default_size=(640, 480)):
        size = self.drawing.size if self.drawing else default_size
        self.ui_state = ui.update_state(self.ui_state, new_drawing_size=size)

    def create_drawing(self, size):
        drawing = Drawing(size=size)
        self.drawings.append(drawing)

    @try_except_log
    def save_drawing(self, drawing=None, ask_for_path=False, auto=False):
        """
        Save the drawing as ORA, asking for a file name if neccessary.
        This format preserves all the layers, frames and other metadata.
        """
        drawing = drawing or self.drawing
        if not ask_for_path and drawing.path:
            if drawing.path.endswith(".ora"):
                drawing.save_ora()
            else:
                raise RuntimeError("Sorry; can only save drawing as ORA!")
        else:
            last_dir = self.get_latest_dir()
            # The point here is to not block the UI redraws while showing the
            # dialog. May be a horrible idea but it seems to work...
            fut = self.executor.submit(show_save_dialog,
                                       title="Select file",
                                       initialdir=last_dir,
                                       filetypes=(("ORA files", "*.ora"),
                                                  # ("PNG files", "*.png"),
                                                  ("all files", "*.*")))

            def really_save_drawing(drawing, path):
                try:
                    if path:
                        if path.endswith(".ora"):
                            drawing.save_ora(path)
                            self.add_recent_file(path)
                        else:
                            self._error = f"Sorry, can only save drawing as ORA!"
                except OSError as e:
                    self._error = f"Could not save:\n {e}"

            fut.add_done_callback(
                lambda fut: really_save_drawing(drawing, fut.result()))

    def export_drawing(self, drawing=None, ask_for_path=False):
        """
        'Exporting' means saving as a flat image format - for now, only PNG is supported.
        What is saved is what is currently visible.
        *This does not preserve layers or other metadata and should not be used for persisting your work.*
        """
        drawing = drawing or self.drawing
        if not ask_for_path and drawing.export_path:
            if drawing.export_path.endswith(".png"):
                drawing.save_png(drawing.export_path)
            else:
                raise RuntimeError("Sorry; can only export as PNG!")
        else:
            last_dir = self.get_latest_dir()
            # The point here is to not block the UI redraws while showing the
            # dialog. May be a horrible idea but it seems to work...
            fut = self.executor.submit(show_save_dialog,
                                       title="Select file",
                                       initialdir=last_dir,
                                       filetypes=(("PNG files", "*.png"),))

            def really_export_drawing(drawing, path):
                try:
                    if path:
                        if path.endswith(".png"):
                            drawing.save_png(path)
                            self.add_recent_file(path)
                        else:
                            self._error = f"Sorry, can only export drawing as PNG!"
                except OSError as e:
                    self._error = f"Could not save:\n {e}"

            fut.add_done_callback(
                lambda fut: really_export_drawing(drawing, fut.result()))
    
    @debounce(cooldown=60, wait=3)
    def autosave_drawing(self):
        fut = self.executor.submit(self.drawing.autosave)
        fut.add_done_callback(lambda path: logger.info(f"Autosaved to '{path.result()}'"))

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

    def close_drawing(self, unsaved=False):
        if not unsaved and self.drawing.unsaved:
            raise RuntimeError("Trying to close an unsaved image by mistake!")
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
        ww, wh = self.get_pixel_aligned_size()
        scale = 2 ** self.zoom  # TODO this should be an argument!
        ox, oy = self.offset  # ... as should this
        ix = (x - (ww / 2 + ox)) / scale + w / 2
        iy = -(y - (wh / 2 + oy)) / scale + h / 2
        return ix, iy

    def _to_window_coords(self, x, y):
        "Convert image coordinates to window coordinates"
        w, h = self.drawing.size
        ww, wh = self.get_pixel_aligned_size()
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
            if io.want_capture_mouse or self.selection:
                self.mouse_position = None
                self.set_mouse_visible(True)
            else:
                self.mouse_position = x, y
                self.set_mouse_visible(False)
        else:
            self.mouse_position = None
            self.set_mouse_visible(True)

    def _draw_mouse_cursor(self):
        """ If the mouse is over the image, draw a cursor crosshair. """
        if self.mouse_position is None:
            return
        x, y = self.mouse_position
        tw, th = self.mouse_texture.size
        gl.glViewport(x - tw, y - th - 1, tw * 2 + 1, th * 2 + 1)
        with self.vao, self.copy_program:
            with self.mouse_texture:
                gl.glEnable(gl.GL_BLEND)
                gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE_MINUS_SRC_ALPHA)
                gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE, EYE4)
                gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
                gl.glBlendFunc(gl.GL_ONE, gl.GL_ZERO)
        ww, wh = self.get_pixel_aligned_size()
        gl.glViewport(0, 0, int(ww), int(wh))

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

