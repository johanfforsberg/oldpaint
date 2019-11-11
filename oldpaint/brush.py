from functools import lru_cache

from .layer import Layer
from .picture import LongPicture, draw_ellipse


class Brush:

    pass


class EllipseBrush(Brush):

    def __init__(self, size):
        self.size = w, h = size
        self.center = (w // 2, h // 2)
        #super().__init__(pic)

    @lru_cache(1)
    def get_pic(self, color):
        pic = LongPicture(size=self.size)
        wx, wy = self.size
        rect = draw_ellipse(pic, (wx//2, wy//2), (wx//2, wy//2),
                            color=color + 255*2**24, fill=True)
        return pic
