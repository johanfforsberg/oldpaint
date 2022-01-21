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


logger = logging.getLogger(__name__)


def render_drawing(drawing, highlighted_layer=None):

    """
    This function has the job of rendering a drawing to a framebuffer.
    """
    
    global layer_texture_cache
    
    offscreen_buffer = _get_offscreen_buffer(drawing.size)

    palette_tuple = drawing.palette.as_tuple()
    colors = _get_colors(palette_tuple)
    frame = drawing.frame

    with vao, offscreen_buffer, draw_program:
        w, h = offscreen_buffer.size
        gl.glViewport(0, 0, w, h)

        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE_MINUS_SRC_ALPHA)        
        gl.glClearBufferfv(gl.GL_COLOR, 0, EMPTY_COLOR)

        for layer in drawing.layers:

            if highlighted_layer and highlighted_layer != layer:
                continue

            # TODO might be a good optimization to draw the layers above and
            # above into two separate textures, so we don't have
            # to iterate over them all every frame. Also cuts down on the
            # number of textures in GPU memory.
            # Assumes the non-current textures don't change though.

            if not layer.visible and highlighted_layer != layer:
                continue
            
            needs_redraw, layer_texture = _get_layer_texture(layer, frame)
            if needs_redraw:
                rect = layer.rect
                logger.debug("redraw texture for layer %r, frame %d: %r", layer, frame, rect)
            else:
                rect = layer.dirty.pop(frame, None)
            if rect and layer.lock.acquire(timeout=0.03):
                subimage = layer.get_subimage(rect, frame)
                data = subimage.tobytes("F")
                gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)  # Needed for writing 8bit data  
                gl.glTextureSubImage2D(layer_texture.name, 0, *rect.points,
                                       gl.GL_RED_INTEGER, gl.GL_UNSIGNED_BYTE, data)
                gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)
                layer.lock.release()

            with layer_texture:
                gl.glUniform1f(1, layer.alpha)
                gl.glUniform4fv(2, 256, colors)
                gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)

        gl.glDisable(gl.GL_BLEND)
    if len(layer_texture_cache) > len(drawing.layers):
        new_layer_texture_cache = {}
        for layer in drawing.layers:
            key = make_layer_cache_key(layer, frame)
            texture = layer_texture_cache.get(key)
            if texture:
                new_layer_texture_cache[key] = texture
        logger.debug("evicting %d textures from layer texture cache",
                     len(layer_texture_cache) - len(drawing.layers))
        layer_texture_cache = new_layer_texture_cache
    return offscreen_buffer


layer_texture_cache = {}


def make_layer_cache_key(layer, frame):
    return id(layer), layer.size, id(layer.frames[frame])


def _get_layer_texture(layer, frame):
    # TODO This key is pretty ugly... we're using ids so that adding/removing
    # frames does not confuse the cache. But it's not pretty.
    layer_key = make_layer_cache_key(layer, frame)
    texture = layer_texture_cache.get(layer_key)
    if texture:
        return False, texture
    if not texture:
        layer_texture_cache[layer_key] = texture = ByteIntegerTexture(layer.size)
        texture.clear()
        return True, texture


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
