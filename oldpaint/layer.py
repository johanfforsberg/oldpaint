from functools import lru_cache
from threading import RLock

import numpy as np

from .rect import Rectangle
from .draw import draw_line, draw_rectangle, draw_fill, blit, paste
from .ora import load_png, save_png


class Layer:

    """
    An editable image.
    The image data is kept in a Picture instance.
    """

    dtype = np.uint8

    def __init__(self, pic=None, size=None):
        if size:
            pic = np.zeros(size, dtype=self.dtype)
        assert isinstance(pic, np.ndarray), "Layer expects a ndarray instance."
        # Here lies the image data for the layer.
        self.pic = pic
        self.version = 0

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
        pic, info = load_png(path)
        return cls(pic), info["palette"]

    def draw_line(self, p0, p1, brush, offset, set_dirty=True, **kwargs):
        ox, oy = offset
        x0, y0 = p0
        x1, y1 = p1
        p0 = (x0 - ox, y0 - oy)
        p1 = (x1 - ox, y1 - oy)
        with self.lock:
            rect = draw_line(self.pic, brush, p0, p1)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        self.version += 1
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
        self.version += 1
        return rect

    def draw_rectangle(self, pos, size, brush, offset=(0, 0), set_dirty=True, color=0, fill=False, **kwargs):
        if not fill:
            x0, y0 = pos
            ox, oy = offset
            pos = (x0 - ox, y0 - oy)
        with self.lock:
            rect = draw_rectangle(self.pic, brush, pos, size, color, fill=fill)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        self.version += 1
        return rect

    def draw_fill(self, point, color, set_dirty=True):
        with self.lock:
            rect = draw_fill(self.pic, point, color)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        self.version += 1
        return rect

    def flip_vertical(self):
        self.pic = np.flip(self.pic, axis=1)
        self.dirty = self.rect
        self.version += 1

    def flip_horizontal(self):
        self.pic = np.flip(self.pic, axis=0)
        self.dirty = self.rect
        self.version += 1

    def swap_colors(self, index1, index2):
        self.pic.swap_colors(index1, index2)
        self.dirty = self.rect
        self.version += 1

    @property
    def size(self):
        return self.pic.shape

    @property
    def rect(self):
        return self._get_rect(self.pic.shape)

    @lru_cache(1)
    def _get_rect(self, shape):
        return Rectangle(size=shape)

    def toggle_visibility(self):
        self.visible = not self.visible

    def clear(self, rect: Rectangle=None, value=0, set_dirty=True):
        rect = rect or self.rect
        rect = self.rect.intersect(rect)
        if not rect:
            return
        self.pic[rect.as_slice()] = value
        if set_dirty and rect:
            self.dirty = rect.unite(self.dirty)
        self.version += 1
        return rect

    def clone(self, dtype=dtype):
        with self.lock:
            return Layer(self.pic.astype(dtype=dtype))

    def get_subimage(self, rect: Rectangle):
        with self.lock:
            return self.pic[rect.as_slice()]

    def crop(self, rect: Rectangle):
        return Layer(pic=self.get_subimage(rect))
        
    def blit(self, pic, rect, set_dirty=True, alpha=True):
        if not rect:
            return
        with self.lock:
            if alpha:
                blit(self.pic, pic, *rect.position)
            else:
                paste(self.pic, pic, *rect.position)
            self.dirty = self.rect.intersect(rect.unite(self.dirty))
            
        self.version += 1
        return self.rect.intersect(rect)

    def blit_part(self, pic, rect, dest, set_dirty=True, alpha=True):
        with self.lock:
            self.dirty = self.rect.intersect(rect.unite(self.dirty))
        self.version += 1
        return self.rect.intersect(rect)

    def make_diff(self, layer, rect, alpha=True):
        with self.lock:
            slc = rect.as_slice()
            mask = layer.pic[slc].astype(np.bool)
            return np.subtract(layer.pic[slc], mask * self.pic[slc], dtype=np.int16)

    def apply_diff(self, diff, rect, invert=False):
        with self.lock:
            slc = rect.as_slice()
            self.pic[slc] = np.add(self.pic[slc], diff, casting="unsafe")
            self.dirty = self.rect.intersect(rect.unite(self.dirty))
        self.version += 1
        return self.rect.intersect(rect)

    def __repr__(self):
        return f"Layer(id={id(self)}, size={self.size}, pic={self.pic})"
    
    def __hash__(self):
        "For caching purposes, a Layer is considered changed when it's underlying Picture has changed."
        return hash((id(self), self.size, self.version))


class TemporaryLayer(Layer):

    dtype = np.uint32
    
    def __hash__(self):
        return hash((id(self), self.size))
