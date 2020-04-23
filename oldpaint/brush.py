from functools import lru_cache

import numpy as np


class Brush:

    def __init__(self, size=None, data=None):
        if size:
            assert len(size) == 2
            self.size = size
            self.data = np.ones(size, dtype=np.uint32)
        else:
            self.data = data
            self.size = data.shape[:2]

        w, h = self.size
        self.center = (w // 2, h // 2)
            
    @lru_cache(2)
    def get_draw_data(self, color, colorize=False):
        return np.clip(self.data, 0, 1) * color + 255 * 2**24

    # def as_rgba(self, colors):
    #     colors32 = [rgba_to_32bit(c) for c in colors]
    #     return (np.array(colors32, dtype=np.uint32)[self.data])

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
        

class RectangleBrush(Brush):

    def __init__(self, size):
        data = np.ones(size, dtype=np.uint32)
        super().__init__(data=data)

        
class PicBrush(Brush):

    @lru_cache(2)    
    def get_draw_data(self, color, colorize=False):
        filled_pixels = self.data > 0
        if colorize:
            # Fill all non-transparent pixels with the same color
            return (color + filled_pixels * 2**24).astype(np.uint32)
        else:
            # Otiginal brush data
            return (self.data + filled_pixels * 2**24).astype(np.uint32)
