from threading import Lock

from .rect import Rectangle
from .picture import Picture, LongPicture, save_png, load_png, draw_line, draw_rectangle, draw_ellipse, draw_fill
# from . import draw


class Layer:

    """
    An editable image.
    The image data is kept in a Picture instance.
    """

    def __init__(self, pic=None):
        self.pic = pic
        # "dirty" is a rect that tells the visualisation that part of the
        # picture has changed and must be refreshed, after which it should
        # set the dirty rect to None. From this side, we should never shrink
        # the dirty rect, but growing it is fine.
        self.dirty = self.rect

        self._visible = True
        self.lock = Lock()

    def save_png(self, path, palette=None):
        save_png(self.pic, path, palette)

    @classmethod
    def load_png(cls, path):
        return cls(load_png(path))

    def draw_line(self, *args, set_dirty=True, **kwargs):
        with self.lock:
            rect = draw_line(self.pic, *args, **kwargs)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        return rect

    def draw_ellipse(self, *args, set_dirty=True, **kwargs):
        with self.lock:
            rect = draw_ellipse(self.pic, *args, **kwargs)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        return rect

    def draw_rectangle(self, *args, set_dirty=True, **kwargs):
        with self.lock:
            rect = draw_rectangle(self.pic, *args, **kwargs)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        return rect

    def draw_fill(self, *args, set_dirty=True, **kwargs):
        with self.lock:
            rect = draw_fill(self.pic, *args, **kwargs)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        return rect

    @property
    def size(self):
        return self.pic.size

    @property
    def rect(self):
        return self.pic.rect

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self._visible = value
        self.dirty = self.rect  # TODO should not be needed

    def clear(self, rect=None, value=0, set_dirty=True):
        rect = rect or self.rect
        print("*** clear ***", rect)
        self.pic.clear(rect.box(), value)
        rect = rect.unite(self.dirty)
        if set_dirty:
            self.dirty = rect
        return rect

    def get_subimage(self, rect):
        return self.pic.crop(*rect.points)

    def blit(self, pic, rect, set_dirty=True, mask=True):
        with self.lock:
            if isinstance(pic, LongPicture):
                if isinstance(self.pic, LongPicture):
                    self.pic.paste(pic, rect.x, rect.y, mask)
                else:
                    self.pic.paste_long(pic, rect.x, rect.y, mask)
            else:
                self.pic.paste(pic, rect.x, rect.y, mask)
            self.dirty = rect.unite(self.dirty)
            self.dirty_data = pic

    def __hash__(self):
        return hash((id(self), self.size))
