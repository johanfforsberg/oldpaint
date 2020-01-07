from threading import RLock

from .rect import Rectangle
from .picture import LongPicture, save_png, load_png
from .draw import draw_line, draw_rectangle, draw_ellipse, draw_fill
from .util import Selectable


class Layer:

    """
    An editable image.
    The image data is kept in a Picture instance.
    """

    def __init__(self, pic=None):
        assert isinstance(pic, LongPicture), "Layer expects a LongPicture instance."
        # Here lies the image data for the layer.
        self.pic = pic

        # This lock is important to hold while drawing, since otherwise
        # the main thread might start reading from it while we're writing.
        # It's reentrant so we don't have to worry about collisions within
        # the drawing thread.
        self.lock = RLock()

        # "dirty" is a rect that tells the visualisation that part of the
        # picture has changed and must be refreshed, after which it should
        # set the dirty rect to None. From this side, we should never shrink
        # or remove the dirty rect, but growing it is fine.
        self.dirty = self.rect

        self.visible = True

    def save_png(self, path, palette=None):
        save_png(self.pic, path, palette)

    @classmethod
    def load_png(cls, path):
        pic, colors = load_png(path)
        return cls(pic), colors

    def draw_line(self, p0, p1, brush, offset, set_dirty=True, **kwargs):
        ox, oy = offset
        x0, y0 = p0
        x1, y1 = p1
        p0 = (x0 - ox, y0 - oy)
        p1 = (x1 - ox, y1 - oy)
        with self.lock:
            rect = draw_line(self.pic, p0, p1, brush, **kwargs)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        return rect

    def draw_ellipse(self, pos, size, brush, offset, set_dirty=True, fill=False, **kwargs):
        if not fill:
            x0, y0 = pos
            ox, oy = offset
            pos = (x0 - ox, y0 - oy)
        with self.lock:
            rect = draw_ellipse(self.pic, pos, size, brush, fill=fill, **kwargs)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        return rect

    def draw_rectangle(self, pos, size, brush, offset, set_dirty=True, fill=False, **kwargs):
        if not fill:
            x0, y0 = pos
            ox, oy = offset
            pos = (x0 - ox, y0 - oy)
        with self.lock:
            rect = draw_rectangle(self.pic, pos, size, brush, fill=fill, **kwargs)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        return rect

    def draw_fill(self, *args, set_dirty=True, **kwargs):
        with self.lock:
            rect = draw_fill(self.pic, *args, **kwargs)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        return rect

    def flip_vertical(self):
        self.pic = self.pic.flip_vertical()
        self.dirty = self.rect

    def flip_horizontal(self):
        self.pic = self.pic.flip_horizontal()
        self.dirty = self.rect

    @property
    def size(self):
        return self.pic.size

    @property
    def rect(self):
        return self.pic.rect

    def toggle_visibility(self):
        self.visible = not self.visible

    def clear(self, rect: Rectangle=None, value=0, set_dirty=True):
        rect = rect or self.rect
        self.pic.clear(rect.box(), value)
        rect = self.rect.intersect(rect)
        if set_dirty and rect:
            self.dirty = rect.unite(self.dirty)
        return rect

    def clone(self):
        return Layer(self.pic.crop(*self.rect.points))

    def get_subimage(self, rect: Rectangle):
        return self.pic.crop(*rect.points)

    def blit(self, pic, rect, set_dirty=True, alpha=True):
        with self.lock:
            self.pic.paste(pic, rect.x, rect.y, alpha)
            self.dirty = self.rect.intersect(rect.unite(self.dirty))
        return self.rect.intersect(rect)

    def blit_part(self, pic, rect, dest, set_dirty=True, alpha=True):
        with self.lock:
            self.pic.paste_part(pic, rect.x, rect.y, rect.width, rect.height, *dest, alpha)
            self.dirty = self.rect.intersect(rect.unite(self.dirty))
        return self.rect.intersect(rect)

    def make_diff(self, layer, rect, alpha=True):
        with self.lock:
            return self.pic.make_diff(layer.pic, *rect, alpha=alpha)

    def apply_diff(self, diff, rect, invert=False):
        with self.lock:
            self.pic.apply_diff(diff, *rect, invert=invert)
            self.dirty = self.rect.intersect(rect.unite(self.dirty))
        return self.rect.intersect(rect)

    def __hash__(self):
        return hash((id(self), self.size))
