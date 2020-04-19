from functools import lru_cache
from itertools import chain
import logging

from pyglet import gl

from fogl.framebuffer import FrameBuffer
from fogl.shader import Program, VertexShader, FragmentShader
from fogl.texture import Texture
from fogl.vao import VertexArrayObject

from .texture import IntegerTexture, ByteIntegerTexture


EMPTY_COLOR = (gl.GLfloat * 4)(0, 0, 0, 0)

vao = VertexArrayObject()

draw_program = Program(VertexShader("glsl/palette_vert.glsl"),
                       FragmentShader("glsl/palette_frag.glsl"))


def render_drawing(drawing, highlighted_layer=None):

    "This function has the job of rendering a drawing to a framebuffer."

    offscreen_buffer = _get_offscreen_buffer(drawing.size)

    colors = _get_colors(drawing.palette.as_tuple())

    with vao, offscreen_buffer, draw_program:
        w, h = offscreen_buffer.size
        gl.glViewport(0, 0, w, h)

        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        gl.glClearBufferfv(gl.GL_COLOR, 0, EMPTY_COLOR)

        overlay = drawing.overlay
        overlay_texture = _get_overlay_texture(overlay.size)

        if overlay.dirty and overlay.lock.acquire(timeout=0.01):
            # Since we're drawing in a separate thread, we need to be very careful
            # when accessing the overlay, otherwise we can get nasty problems.
            # While we have the lock, the thread won't draw, so we can safely copy data.
            # The acquire timeout is a compromise; on one hand, we don't wait
            # so long that the user feels stutter, on the other hand,
            # if we never wait, and the draw thread is very busy, we might
            # not get to update for a long time.
            rect = overlay.dirty
            subimage = overlay.get_subimage(rect)
            data = subimage.tobytes("F")  # TODO Is this making another copy?

            # Now update the texture with the changed part of the layer.
            try:
                gl.glTextureSubImage2D(overlay_texture.name, 0, *rect.points,
                                       gl.GL_RGBA_INTEGER, gl.GL_UNSIGNED_BYTE, data)

                overlay.dirty = None
                overlay.lock.release()  # Allow layer to change again.
            except gl.lib.GLException as e:
                logging.error(str(e))

        for layer in drawing.layers:

            if highlighted_layer and highlighted_layer != layer:
                continue

            # TODO might be a good optimization to draw the layers above and
            # above into two separate textures, so we don't have
            # to iterate over them all every frame. Also cuts down on the
            # number of textures in GPU memory.
            # Assumes the non-current textures don't change though.

            layer_texture = _get_layer_texture(layer)
            if layer.dirty and layer.lock.acquire(timeout=0.03):
                rect = layer.dirty
                subimage = layer.get_subimage(rect)
                data = subimage.tobytes("F")
                gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)  # Needed for writing 8bit data  
                gl.glTextureSubImage2D(layer_texture.name, 0, *rect.points,
                                       gl.GL_RED_INTEGER, gl.GL_UNSIGNED_BYTE, data)
                gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)
                layer.dirty = None
                layer.lock.release()

            if not layer.visible and highlighted_layer != layer:
                continue

            with layer_texture:
                if layer == drawing.current:
                    # The overlay is combined with the layer
                    with overlay_texture:
                        # TODO is it possible to send the palette without converting
                        # to float first?
                        gl.glUniform1f(1, 1)
                        gl.glUniform4fv(2, 256, colors)
                        gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
                else:
                    with _get_empty_texture(drawing.size):
                        gl.glUniform1f(1, 1)
                        gl.glUniform4fv(2, 256, colors)
                        gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)

        gl.glDisable(gl.GL_BLEND)
    return offscreen_buffer


# TODO this needs to be limited
layer_texture_cache = {}

def _get_layer_texture(layer):
    layer_hash = hash((id(layer), layer.size))
    texture = layer_texture_cache.get(layer_hash)
    if not texture:
        layer_texture_cache[layer_hash] = texture = ByteIntegerTexture(layer.size)
        texture.clear()
    return texture


@lru_cache(1)
def _get_overlay_texture(shape):
    texture = IntegerTexture(shape, unit=1)
    texture.clear()
    return texture


@lru_cache(1)
def _get_empty_texture(size):
    texture = IntegerTexture(size, unit=1)
    texture.clear()
    return texture


@lru_cache(1)
def _get_offscreen_buffer(size):
    return FrameBuffer(size, textures=dict(color=Texture(size, unit=0)))


@lru_cache(1)
def _get_colors(colors):
    float_colors = chain.from_iterable((r / 255, g / 255, b / 255, a / 255)
                                       for r, g, b, a in colors)
    return (gl.GLfloat*(4*256))(*float_colors)


@lru_cache(1)
def _get_background_color(colors):
    r, g, b, a = colors[0]
    return (gl.GLfloat*4)(r / 255, g / 255, b / 255, a / 255)
