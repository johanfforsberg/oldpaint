from functools import lru_cache
from math import floor, ceil

import numpy as np

from .draw import draw_ellipse
from .ora import save_png


class Brush:

    def __init__(self, size=None, data=None):
        if size:
            assert len(size) == 2
            self.size = size
            self.data = np.ones(size, dtype=np.uint32)
        else:
            self.data = data
            self.size = data.shape[:2]

    @lru_cache(2)  
    def get_draw_data(self, color, colorize=False):
        filled_pixels = self.data > 0
        if colorize:
            # Fill all non-transparent pixels with the same color
            return (color + filled_pixels * 2**24).astype(np.uint32)
        else:
            # Otiginal brush data
            return (self.data + filled_pixels * 2**24).astype(np.uint32)
    
    @property
    def center(self):
        return self._get_center(self.size)

    @lru_cache(1)
    def _get_center(self, size):
        w, h = self.size
        return w // 2, h // 2

    def rotate(self, d):
        data = self.data
        self.data = np.rot90(data, d)
        self.size = self.data.shape[:2]
        self.get_draw_data.cache_clear()

    def flip(self, vertical=False):
        data = self.data
        self.data = np.flip(data, axis=vertical)
        self.size = self.data.shape[:2]
        self.get_draw_data.cache_clear()

    def save_png(self, path, colors):
        with open(path, "wb") as f:
            save_png(self.data, f, colors)


class RectangleBrush(Brush):

    def __init__(self, size):
        data = np.ones(size, dtype=np.uint32)
        super().__init__(data=data)


class EllipseBrush(Brush):

    def __init__(self, size):
        data = np.zeros(size, dtype=np.uint32)
        brush = np.array([[1]], dtype=np.uint32)
        w, h = size
        draw_ellipse(data, brush,
                     center=(ceil(w//2), ceil(h//2)),
                     size=(ceil(w/2-1), ceil(h/2-1)),
                     color=1, fill=True)
        super().__init__(data=data)

        
class PicBrush(Brush):

    pass
