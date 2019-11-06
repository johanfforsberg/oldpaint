from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from itertools import chain
from queue import Queue

from euclid3 import Matrix4, Vector3
import pyglet
from pyglet import gl

from ugly.framebuffer import FrameBuffer
from ugly.shader import Program, VertexShader, FragmentShader
from ugly.texture import Texture, ByteTexture
from ugly.util import try_except_log
from ugly.vao import VertexArrayObject

from .stack import Stack
from .stroke import make_stroke
from .layer import Layer
from .picture import Picture, LongPicture


BG_COLOR = (gl.GLfloat * 4)(0.5, 0.5, 0.5, 1)
ZERO_COLOR = (gl.GLfloat * 4)(0, 0, 0, 0)


class OldpaintWindow(pyglet.window.Window):

    def __init__(self, **kwargs):

        super().__init__(**kwargs, resizable=True, vsync=False)

        size = (640, 480)
        self.stack = Stack(size, layers=[Layer(Picture(size))])

        self.overlay = Layer(LongPicture(size))
        self.offscreen_buffer = FrameBuffer(size, textures=dict(color=Texture(size, unit=0)))
        self.vao = VertexArrayObject()

        self.draw_program = Program(VertexShader("glsl/palette_vert.glsl"),
                                    FragmentShader("glsl/palette_frag.glsl"))
        self.copy_program = Program(VertexShader("glsl/copy_vert.glsl"),
                                    FragmentShader("glsl/copy_frag.glsl"))

        self.executor = ThreadPoolExecutor(max_workers=1)
        self.mouse_event_queue = None

        self.stroke = None
        self.pan = None
        self.offset = (0, 0)
        self.zoom = 0

    def on_mouse_press(self, x, y, button, modifiers):
        if button in (pyglet.window.mouse.LEFT,
                      pyglet.window.mouse.RIGHT):
            self.mouse_event_queue = Queue()
            self.stroke = self.executor.submit(make_stroke, self.overlay, self.mouse_event_queue)
        else:
            self.pan = (x, y)

    def on_mouse_release(self, x, y, button, modifiers):
        if self.stroke:
            self.mouse_event_queue.put(("mouse_up", (self._to_image_coords(x, y), button, modifiers)))
            points, rect = self.stroke.result()
            self.stroke = None
        elif self.pan:
            self.pan = None

    def on_mouse_drag(self, x, y, dx, dy, button, modifiers):
        if self.stroke:
            self.mouse_event_queue.put(("mouse_drag", (self._to_image_coords(x, y), button, modifiers)))
        elif self.pan:
            ox, oy = self.offset
            self.offset = ox + dx, oy + dy

    def on_mouse_motion(self, x, y, dx, dy):
        pass

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        ox, oy = self.offset
        oxi, oyi = self._to_image_coords(self.offset)
        scale = 2 ** self.zoom
        x, y = self._to_image_coords((x, y))

        # self.offset = ox -

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

            if overlay.dirty and overlay.lock.acquire(timeout=0.05):
                # While we have the lock, the layer won't be changed, so we can safely copy part of it.
                rect = overlay.dirty
                subimage = overlay.get_subimage(rect)
                data = (gl.GLuint * rect.area())(*subimage.data)

                # Now update the texture with the changed part of the layer.
                gl.glTextureSubImage2D(overlay_texture.name, 0, *rect.points,
                                       gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, data)

                overlay.dirty = None
                overlay.lock.release()  # Allow layer to change again.

            for layer in self.stack:
                layer_texture = self._get_layer_texture(layer)
                if layer.dirty and layer.lock.acquire(timeout=0.03):
                    rect = layer.dirty
                    subimage = layer.get_subimage(rect)
                    data = (gl.GLubyte * rect.area())(*subimage.data)
                    gl.glTextureSubImage2D(layer_texture.name, 0, *rect.points,
                                           gl.GL_RED, gl.GL_UNSIGNED_BYTE, data)

                    layer.dirty = None
                    layer.lock.release()  # Allow layer to change again.

                with layer_texture:
                    if layer == stack.current:
                        with overlay_texture:  # overlay_texture:
                            gl.glUniform4fv(1, 256, (gl.GLfloat*(4*256))(*chain.from_iterable(stack.palette)))
                            gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
                    else:
                        with self._get_empty_texture(stack):
                            gl.glUniform4fv(1, 256, (gl.GLfloat*(4*256))(*chain.from_iterable(stack.palette)))
                            gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)

        window_size = self.get_size()
        gl.glViewport(0, 0, *window_size)
        gl.glClearBufferfv(gl.GL_COLOR, 0, BG_COLOR)

        vm = make_view_matrix(window_size, stack.size, self.zoom, self.offset)

        with self.vao, self.copy_program, self.offscreen_buffer["color"]:
            gl.glEnable(gl.GL_BLEND)
            gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE, (gl.GLfloat*16)(*vm))
            gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)

        gl.glFinish()  # No double buffering, to minimize latency

    def on_resize(self, w, h):
        return pyglet.event.EVENT_HANDLED  # Work around pyglet internals

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
        stack_size = self.stack.size
        window_size = self.get_size()
        zoom = self.zoom
        offset = self.offset
        ivm = make_view_matrix_inverse(window_size, stack_size, zoom, offset)
        w, h = window_size
        w2, h2 = w / 2, h / 2
        ox, oy = offset
        # TODO why do we need to put in the offset here?
        ix, iy, _ = ivm * Vector3((x - w2 - ox) / w2, (y - h2 - oy) / h2, 0)
        iw, ih = stack_size
        ix = int(ix * iw + iw / 2)
        iy = int(ih - (iy * ih + ih / 2))
        return ix, iy


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
