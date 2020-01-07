from functools import lru_cache
from math import floor

from .picture import LongPicture, save_png
from .draw import draw_ellipse, draw_rectangle


class Brush:

    """
    A brush is essentially a picture that is intended to be drawn with.
    It's sort of a layer but with fewer operations.
    """

    # TODO subclass layer?

    pass


class PicBrush(Brush):

    def __init__(self, pic):
        self.original = pic
        self.size = w, h = pic.size
        self.center = w // 2, h // 2

    @lru_cache(2)
    def get_pic(self, color=None):
        if color is None:
            return self.original
        else:
            colorized = LongPicture(self.size)
            colorized.paste(self.original, 0, 0, mask=True, colorize=True, color=color)
            return colorized

    def save_png(self, path, colors):
        with open(path, "wb") as f:
            save_png(self.original, f, colors)

    def flip_vertical(self):
        self.original = self.original.flip_vertical()
        self.get_pic.cache_clear()

    def flip_horizontal(self):
        self.original = self.original.flip_horizontal()
        self.get_pic.cache_clear()

    def rotate_clockwise(self):
        self.original = self.original.rotate(False)
        w, h = self.size
        self.size = h, w
        self.get_pic.cache_clear()

    def rotate_counter_clockwise(self):
        self.original = self.original.rotate(True)
        w, h = self.size
        self.size = h, w
        self.get_pic.cache_clear()

    def __hash__(self):
        return id(self.original)


class RectangleBrush(Brush):

    def __init__(self, size):
        self.size = w, h = size
        self.center = (w // 2, h // 2)
        self.original = self.get_pic(color=1)

    @lru_cache(1)
    def get_pic(self, color):
        pic = LongPicture(size=self.size)
        draw_rectangle(pic, (0, 0), self.size,
                       color=color + 255*2**24, fill=True)
        return pic


class EllipseBrush(Brush):

    def __init__(self, size):
        self.size = w, h = size
        self.center = int((w-1) / 2), int((h-1) / 2)
        self.original = self.get_pic(color=1)

    @lru_cache(1)
    def get_pic(self, color):
        pic = LongPicture(size=self.size)
        w, h = self.size
        draw_ellipse(pic, self.center, self.center,
                     color=color + 255*2**24, fill=True)
        return pic
