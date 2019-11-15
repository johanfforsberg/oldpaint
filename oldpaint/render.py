from functools import lru_cache
from itertools import chain

from pyglet import gl

from ugly.framebuffer import FrameBuffer
from ugly.shader import Program, VertexShader, FragmentShader
from ugly.texture import Texture, ByteTexture, ImageTexture
from ugly.vao import VertexArrayObject


ZERO_COLOR = (gl.GLfloat * 4)(0, 0, 0, 0)

vao = VertexArrayObject()

draw_program = Program(VertexShader("glsl/palette_vert.glsl"),
                       FragmentShader("glsl/palette_frag.glsl"))


def render_drawing(drawing):
    "This function has the job of rendering a drawing to a framebuffer."

    offscreen_buffer = _get_offscreen_buffer(drawing)

    with vao, offscreen_buffer, draw_program:
        w, h = offscreen_buffer.size
        gl.glViewport(0, 0, w, h)
        gl.glDisable(gl.GL_BLEND)
        gl.glClearBufferfv(gl.GL_COLOR, 0, ZERO_COLOR)

        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)

        overlay = drawing.overlay
        overlay_texture = _get_overlay_texture(overlay)

        if overlay.dirty and overlay.lock.acquire(timeout=0.03):
            # Since we're drawing in a separate thread, we need to be very careful
            # when accessing the overlay, otherwise we can get nasty problems.
            # While we have the lock, the thread won't draw, so we can safely copy data.
            rect = overlay.dirty
            subimage = overlay.get_subimage(rect)
            data = bytes(subimage.data)  # TODO Is this making a copy?

            # Now update the texture with the changed part of the layer.
            try:
                gl.glTextureSubImage2D(overlay_texture.name, 0, *rect.points,
                                       gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, data)

                overlay.dirty = None
                overlay.lock.release()  # Allow layer to change again.
            except gl.lib.GLException:
                print(rect, data)
                pass

        for layer in drawing:

            #if not self.highlighted_layer or self.highlighted_layer == layer:

            layer_texture = _get_layer_texture(layer)
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
                if layer == drawing.current:
                    # The overlay is combined with the layer
                    with overlay_texture:
                        gl.glUniform4fv(1, 256, _get_colors(drawing.palette.get_rgba()))
                        gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
                else:
                    with _get_empty_texture(drawing):
                        gl.glUniform4fv(1, 256, _get_colors(drawing.palette.get_rgba()))
                        gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)

    return offscreen_buffer


@lru_cache(32)
def _get_layer_texture(layer):
    texture = ByteTexture(layer.size)
    texture.clear()
    return texture


@lru_cache(1)
def _get_overlay_texture(overlay):
    texture = Texture(overlay.size, unit=1)
    texture.clear()
    return texture


@lru_cache(1)
def _get_empty_texture(drawing):
    texture = Texture(drawing.size, unit=1)
    texture.clear()
    return texture


@lru_cache(1)
def _get_offscreen_buffer(drawing):
    return FrameBuffer(drawing.size, textures=dict(color=Texture(drawing.size, unit=0)))


@lru_cache(1)
def _get_colors(colors):
    colors = chain.from_iterable(colors)
    return (gl.GLfloat*(4*256))(*colors)