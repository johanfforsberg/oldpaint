from functools import lru_cache

from .layer import Layer
from .picture import LongPicture, draw_ellipse, draw_rectangle


class Brush:

    pass


class PicBrush(Brush):

    def __init__(self, pic):
        self.original = pic
        #LongPicture(size=pic.size)
        #self.original.paste_byte(pic, 0, 0, None)
        self.size = pic.size

    def get_pic(self, color=None):
        return self.original


class RectangleBrush(Brush):

    def __init__(self, size):
        self.size = w, h = size
        self.center = (w // 2, h // 2)
        self.original = self.get_pic(color=1)

    @lru_cache(1)
    def get_pic(self, color):
        pic = LongPicture(size=self.size)
        rect = draw_rectangle(pic, (0, 0), self.size, color=color + 255*2**24, fill=True)
        return pic


class EllipseBrush(Brush):

    def __init__(self, size):
        self.size = w, h = size
        self.center = (w // 2, h // 2)
        #super().__init__(pic)
        self.original = self.get_pic(color=1)

    @lru_cache(1)
    def get_pic(self, color):
        pic = LongPicture(size=self.size)
        wx, wy = self.size
        rect = draw_ellipse(pic, (wx//2, wy//2), (wx//2, wy//2),
                            color=color + 255*2**24, fill=True)
        return pic
