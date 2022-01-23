from functools import lru_cache
from itertools import chain
import logging

from pyglet import gl

from fogl.framebuffer import FrameBuffer
from fogl.shader import Program, VertexShader, FragmentShader
from fogl.texture import Texture
from fogl.vao import VertexArrayObject

from .texture import IntegerTexture, ByteIntegerTexture


EMPTY_COLOR = (gl.GLfloat * 4)(0.7, 0.7, 0.7, 1)

vao = VertexArrayObject()

draw_program = Program(VertexShader("glsl/palette_vert.glsl"),
                       FragmentShader("glsl/palette_frag.glsl"))


logger = logging.getLogger(__name__)


def render_drawing(drawing, stroke, highlighted_layer=None):

    """
    This function has the job of rendering a drawing to a framebuffer.
    """
    
    global layer_texture_cache
    
    offscreen_buffer = _get_offscreen_buffer(drawing.size)

    palette_tuple = drawing.palette.as_tuple()
    colors = _get_colors(palette_tuple)
    frame = drawing.frame
    current_layer = drawing.current
    bg_color = drawing.palette.get_color_as_float(drawing.palette.colors[0])
    # print(bg_color)

    with vao, offscreen_buffer, draw_program:
        w, h = offscreen_buffer.size
        gl.glViewport(0, 0, w, h)

        gl.glEnable(gl.GL_BLEND)
        gl.glBlendEquation(gl.GL_FUNC_ADD)
        gl.glClearColor(*bg_color[:3], 0)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        gl.glClearBufferfv(gl.GL_COLOR, 0, (gl.GLfloat * 4)(*bg_color[:3], 1))

        backup = drawing.backup
        
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

            # If the user is drawing, we'll draw the backup layer instead of the
            # current layer as that's where things are changing.
            if layer == current_layer and (backup.dirty or backup.touched):
                backup_rect = backup.dirty.pop(0, None)
                # Since we're drawing in a separate thread, we need to be very careful
                # when accessing the backup, otherwise we can get nasty problems.
                # While we have the lock, the thread won't draw, so we can safely copy data.

                # The acquire timeout is a compromise; on one hand, we don't wait
                # so long that the user feels stutter, on the other hand,
                # if we never wait, and the draw thread is very busy, we might
                # not get to update for a long time.
                backup_texture = _get_backup_texture(backup.size, id(current_layer), frame)
                if backup_texture.fresh:
                    backup_rect = backup.rect
                    backup_texture.fresh = False

                if backup_rect and backup.lock.acquire(timeout=0.01):
                    subimage = backup.get_subimage(backup_rect, 0)
                    data = subimage.tobytes("F")  # TODO Is this making another copy?
                    # Now update the texture with the changed part of the layer.
                    try:
                        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)  # Needed for writing 8bit data
                        gl.glTextureSubImage2D(backup_texture.name, 0, *backup_rect.points,
                                               gl.GL_RED_INTEGER, gl.GL_UNSIGNED_BYTE, data)

                    except gl.lib.GLException as e:
                        logging.error(str(e))
                    backup.lock.release()  # Allow backup to change again.

                with backup_texture:
                    gl.glUniform1f(1, layer.alpha)
                    gl.glUniform4fv(2, 256, colors)
                    gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
            else:
                needs_redraw, layer_texture = _get_layer_texture(layer, frame)
                if needs_redraw:
                    rect = layer.rect
                    logger.debug("redraw texture for layer %r, frame %d: %r", layer, frame, rect)
                else:
                    rect = layer.dirty.pop(frame, None)
                if rect and layer.lock.acquire(timeout=0.03):
                    # Guess layers don't usually change randomly but best to be sure.
                    subimage = layer.get_subimage(rect, frame)
                    data = subimage.tobytes("F")
                    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)  # Needed for writing 8bit data  
                    gl.glTextureSubImage2D(layer_texture.name, 0, *rect.points,
                                           gl.GL_RED_INTEGER, gl.GL_UNSIGNED_BYTE, data)
                    layer.lock.release()

                with layer_texture:
                    gl.glUniform1f(1, layer.alpha)
                    gl.glUniform4fv(2, 256, colors)
                    gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)

    if len(layer_texture_cache) > len(drawing.layers):
        new_layer_texture_cache = {}
        for layer in drawing.layers:
            key = make_layer_cache_key(layer, frame)
            texture = layer_texture_cache.get(key)
            if texture:
                new_layer_texture_cache[key] = texture
        logger.debug("Evicting %d textures from layer texture cache",
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
        logging.debug("Created new texture texture %r", layer_key)
        texture.clear()
        return True, texture


@lru_cache(1)
def _get_backup_texture(size, layer_id, frame):
    texture = ByteIntegerTexture(size)
    logging.debug("Created new backup texture")
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
