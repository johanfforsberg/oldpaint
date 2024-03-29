from functools import lru_cache
import inspect

import numpy as np

from .draw import draw_ellipse, rescale
from .ora import save_png
from .util import cache_clear


class Brush:

    def __init__(self, size=None, data=None):
        if size:
            assert len(size) == 2
            self.size = size
            self.data = np.ma.zeros(size, dtype=np.uint8)
        else:
            self.size = data.shape[:2]
            assert isinstance(data, np.ma.MaskedArray)
            assert isinstance(data.mask, np.ndarray)
            self.data = data
    
    @property
    def center(self):
        return self._get_center(self.size)

    @lru_cache(2)  
    def get_draw_data(self, color, colorize=None):
        filled_pixels = ~self.data.mask
        # Fill all non-transparent pixels with the same color
        # return (color + filled_pixels * 2**24).astype(np.uint32)
        return np.ma.masked_array(color * filled_pixels, dtype=np.uint8,
                                  mask=self.data.mask)
    
    @lru_cache(1)
    def _get_center(self, size):
        w, h = self.size
        return w // 2, h // 2

    @cache_clear(get_draw_data)
    def rotate(self, d):
        data = self.data
        self.data = np.rot90(data, d)
        self.size = self.data.shape[:2]
        self.get_draw_data.cache_clear()

    @cache_clear(get_draw_data)
    def flip(self, vertical=False):
        data = self.data
        self.data = np.flip(data, axis=vertical)
        self.size = self.data.shape[:2]

    def save_png(self, path, colors):
        save_png(self.data, path, colors)

    @cache_clear(get_draw_data)
    def resize(self, size):
        self.data = rescale(self.data, size)
        self.size = size

    def get_params(self):
        signature = inspect.signature(self.__init__)
        return signature.parameters

    def __hash__(self):
        return hash(id(self.data))

    def __repr__(self):
        return f"{self.size}"


class RectangleBrush(Brush):

    name = "rectangle"

    def __init__(self, width: int = 1, height: int = 1):
        self.width = width
        self.height = height
        data = np.ma.ones((width, height), dtype=np.uint8)
        data.mask = data.data == 0
        super().__init__(data=data)


class SquareBrush(RectangleBrush):

    name = "square"

    def __init__(self, side: int = 1):
        self.side = side
        return super().__init__(side, side)


class EllipseBrush(Brush):

    name = "ellipse"

    def __init__(self, r1: int = 1, r2: int = 1):
        self.r1 = r1
        self.r2 = r2
        d1 = 2 * r1
        d2 = 2 * r2
        data = np.ma.zeros((d1, d2), dtype=np.uint8)
        brush = np.ma.masked_array([[1]], dtype=np.uint8, mask=[False])
        draw_ellipse(data, brush, brush.mask,
                     center=(r1, r2),
                     size=(r1-1, r2-1),
                     color=1, fill=True)
        data.mask = data.data == 0
        super().__init__(data=data)


class CircleBrush(EllipseBrush):

    name = "circle"

    def __init__(self, radius: int = 1):
        self.radius = radius
        super().__init__(radius, radius)


BUILTIN_BRUSH_TYPES = [
    RectangleBrush,
    SquareBrush,
    EllipseBrush,
    CircleBrush,
]


class PicBrush(Brush):

    @lru_cache(2)  
    def get_draw_data(self, color, colorize=False):
        filled_pixels = self.data > 0
        if colorize:
            # Fill all non-transparent pixels with the same color
            return np.ma.masked_array(color * filled_pixels,
                                      mask=self.data.mask,
                                      dtype=np.uint8)
        else:
            # Otiginal brush data
            return (self.data * filled_pixels).astype(np.uint8)

