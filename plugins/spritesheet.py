from functools import lru_cache

from fogl.texture import Texture
import imgui
from pyglet import gl
from pyglet.window import key

from oldpaint.rect import Rectangle
from oldpaint.util import as_rgba


class Plugin:

    def __init__(self, size=(32, 32), row0=0, col0=0, rows=8, cols=8, col=0, row=0):
        self.size = size
        self.row0 = row0
        self.col0 = col0
        self.rows = rows
        self.cols = cols
        self.col = col
        self.row = row
        self._layer_version = None
        self._refresh = False

    def to_json(self):
        return dict(
            size=self.size,
            row0=self.row0,
            col0=self.col0,
            rows=self.rows,
            cols=self.cols,
            col=self.col,
            row=self.row,
        )
    
    def __call__(self, drawing):
        w, h = self.size
        if imgui.collapsing_header("Settings", True)[0]:
            _, w = imgui.input_int("Width", self.size[0])
            w = max(1, min(w, 128))
            _, h = imgui.input_int("Height", self.size[1])
            h = max(1, min(h, 128))
            _, rows = imgui.input_int("Rows", self.rows)
            self.rows = max(1, rows)
            _, cols = imgui.input_int("Cols", self.cols)
            self.cols = max(1, cols)
            _, row0 = imgui.input_int("Row 0", self.row0)
            self.row0 = max(0, row0)
            _, col0 = imgui.input_int("Col 0", self.col0)
            self.col0 = max(0, col0)
            
        self.size = (w, h)
        col_changed, self.col = imgui.slider_int("Col", self.col,
                                                 min_value=0, max_value=self.cols - 1)
        row_changed, self.row = imgui.slider_int("Row", self.row,
                                                 min_value=0, max_value=self.rows - 1)
        layer = drawing.current
        texture = self._get_frame_texture(self.size)
        if col_changed or row_changed or layer.version != self._layer_version or self._refresh:
            offset = ((self.col0 + self.col) * w,
                      (self.row0 + self.row) * h)
            self._update_texture(drawing, offset, texture)
            self._layer_version = drawing.current.version
            self._refresh = False
        palette = drawing.palette
        r, g, b, _ = palette.get_color_as_float(palette[0])
        imgui.push_style_color(imgui.COLOR_BUTTON, r, g, b)
        imgui.image_button(texture.name, w * 3, h * 3)
        imgui.pop_style_color()
        
    def _update_texture(self, drawing, offset, texture):
        layer = drawing.current
        rect = Rectangle(offset, self.size)
        subimage = layer.get_subimage(rect, 0)
        data = as_rgba(subimage, drawing.palette.as_tuple()).tobytes("F")
        texture.clear()
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)            
        gl.glTextureSubImage2D(texture.name, 0,
                               0, 0, *self.size,
                               gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, data)
        self._layer_version = layer.version
            
    @lru_cache(1)
    def _get_frame_texture(self, size):
        texture = Texture(size)
        texture.clear()
        return texture

    def on_key_press(self, symbol, modifiers):
        # if not modifiers.MOD_CAPSLOCK:
        #     return
        if symbol == key.A:
            self.col = (self.col - 1) % self.cols
            self._refresh = True
            return True
        if symbol == key.D:
            self.col = (self.col + 1) % self.cols
            self._refresh = True            
            return True
        if symbol == key.W:
            self.row = (self.row - 1) % self.rows
            self._refresh = True
            return True
        if symbol == key.S:
            self.row = (self.row + 1) % self.rows
            self._refresh = True            
            return True
            
