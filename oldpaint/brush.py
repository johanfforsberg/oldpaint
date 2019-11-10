from functools import lru_cache

from .layer import Layer
from .picture import LongPicture


class Brush(Layer):

    pass


class EllipseBrush(Brush):

    def __init__(self, size):
        pic = LongPicture(size=size)
        super().__init__(pic)

    @lru_cache(1)
    def get_pic(self, color):
        wx, wy = self.size
        self.draw_ellipse((wx//2, wy//2), (wx//2, wy//2),
                          color=color + 255*2**24, fill=True)
