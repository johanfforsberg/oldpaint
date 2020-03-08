from itertools import chain, product
from functools import lru_cache
import math
from time import time
from traceback import print_exc

from pyglet import gl
from euclid3 import Matrix4

from fogl.framebuffer import FrameBuffer
from fogl.glutil import gl_matrix
from fogl.mesh import ObjMesh, Mesh
from fogl.shader import Program, VertexShader, FragmentShader
from fogl.texture import ImageTexture, Texture, NormalTexture
from fogl.util import try_except_log, load_png
from fogl.vao import VertexArrayObject
from fogl.vertex import Vertices
from fogl.util import enabled, disabled
import oldpaint


VERTEX_SHADER = b"""
#version 450 core

layout (location = 0) in vec4 position;
layout (location = 1) in vec4 color;
layout (location = 2) in vec4 normal;

layout (location = 0) uniform mat4 proj_matrix;

out VS_OUT {
  vec4 color;
  vec4 normal;
} vs_out;


void main() {
  gl_Position = proj_matrix * position;
  vs_out.color = color;
  vs_out.normal = normal;
}
"""

FRAGMENT_SHADER = b"""
#version 450 core

layout (location = 1) uniform vec4 color = vec4(1, 1, 1, 1);

in VS_OUT {
  vec4 color;
  vec4 normal;
} fs_in;


layout (location = 0) out vec4 color_out;
layout (location = 1) out vec4 normal_out;


void main(void) {
  float z = gl_FragCoord.z;
  float light = 0.5 + z / 2;
  color_out = fs_in.color * vec4(light, light, light, 1);
  normal_out = fs_in.normal;
}
"""


class VoxelVertices(Vertices):
    _fields = [
        ('position', gl.GL_FLOAT, 4),
        ('color', gl.GL_FLOAT, 4),
        ('normal', gl.GL_FLOAT, 4),
    ]    


class Plugin:

    """
    Show the current selection of the drawing as a three dimensional object.
    """
    
    period = 0.1
    last_run = 0

    def __init__(self):
        self.program = Program(
            VertexShader(source=VERTEX_SHADER),
            FragmentShader(source=FRAGMENT_SHADER)
        )
        self.mesh = None
        # self.vao = VertexArrayObject()
        self.framebuffer = None

        self.texture = None

    @lru_cache(1)
    def _get_buffer(self, size):
        if self.framebuffer:
            self.framebuffer.delete()
        render_textures = dict(
            # These will represent the different channels of the framebuffer,
            # that the shader can render to.
            color=Texture(size, unit=0, params={gl.GL_TEXTURE_MIN_FILTER: gl.GL_LINEAR}),
            normal=NormalTexture(size, unit=1, params={gl.GL_TEXTURE_MIN_FILTER: gl.GL_LINEAR}),
            position=NormalTexture(size, unit=2, params={gl.GL_TEXTURE_MIN_FILTER: gl.GL_LINEAR}),
        )
        self.framebuffer = FrameBuffer(size, render_textures, autoclear=True)
        return self.framebuffer

    @lru_cache(2)
    def _get_texture(self, size):
        return Texture(size)
    
    @lru_cache(256)
    def _get_float_color(self, r, g, b, a):
        return r/255, g/255, b/255, a/255

    @lru_cache(100)
    def _get_layer_vertices(self, layer, rect, colors, z):
        if not layer.visible:
            return []
        subimage = layer.get_subimage(rect)
        w, h = rect.size
        vertices = [((x, y, z, 1), self._get_float_color(*colors[subimage[x, y]]), (0, 0, 1, 0))
                    for x, y in product(range(w), range(h))
                    if subimage[x, y] > 0]
        return vertices

    @lru_cache(1)
    def _get_vertices(self, layers, rect, colors):
        return list(chain.from_iterable(self._get_layer_vertices(layer, rect, colors, i)
                                        for i, layer in enumerate(layers)
                                        if layer.visible))
        
    def __call__(self, drawing, brush,
                 altitude: float=math.pi/3, azimuth: float=0, spin: bool=False):
        selection = drawing.selection
        if selection:
            size = selection.size
            depth = len(drawing.layers)
            colors = drawing.palette.as_tuple()
            # vertices = list(chain.from_iterable(self._get_layer_vertices(layer, selection, colors, i)
            #                                     for i, layer in enumerate(drawing.layers)
            #                                     if layer.visible))
            vertices = self._get_vertices(tuple(drawing.layers), selection, colors)
            if not vertices:
                # TODO hacky
                self.texture and self.texture[0].clear()
                return
            offscreen_buffer = self._get_buffer(size)
            mesh = Mesh(data=vertices, vertices_class=VoxelVertices)

            with offscreen_buffer, self.program, \
                    disabled(gl.GL_DEPTH_TEST), disabled(gl.GL_CULL_FACE):

                # near = -10
                # far = 15
                # width = 0.05
                # height = 0.05 * 1
                # frustum = (Matrix4.new(
                #     near / width, 0, 0, 0,
                #     0, near / height, 0, 0,
                #     0, 0, -(far + near)/(far - near), -1,
                #     0, 0, -2 * far * near/(far - near), 0
                # ))
                w, h = size
                model_matrix = Matrix4.new_translate(-w/2, -h/2, -depth/2).scale(1, 1, 1/math.sin(math.pi/3))
                azimuth = time() if spin else azimuth
                view_matrix = (Matrix4
                               .new_scale(2/w, 2/h, 1/max(w, h))
                               .translate(0, 0, -10)
                               .rotatex(altitude)
                               .rotatez(azimuth)  # Rotate over time
                               )
                gl.glUniformMatrix4fv(0, 1, gl.GL_FALSE,
                                      gl_matrix(view_matrix * model_matrix))

                # gl.glClearColor(1, 0, 0, 1)
                # gl.glClear(gl.GL_COLOR_BUFFER_BIT)
                
                gl.glUniform4f(1, 0.3, 1, 0.3, 1)
                gl.glViewport(0, 0, *size)
                #gl.glDepthRange(-100, 100)
                gl.glPointSize(1.0)

                mesh.draw(mode=gl.GL_POINTS)

            # TODO must be careful here so that the texture is always valid
            # (since imgui may read it at any time) Find a way to ensure this.
            texture = self._get_texture(size)
            gl.glCopyImageSubData(self.framebuffer["color"].name, gl.GL_TEXTURE_2D, 0, 0, 0, 0,
                                  texture.name, gl.GL_TEXTURE_2D, 0, 0, 0, 0,
                                  w, h, 1)
            self.texture = texture, size
