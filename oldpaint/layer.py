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

    def __init__(self, frames=None, size=None, visible=True):
        if not frames and size:
            frames = [np.zeros(size, dtype=self.dtype)]
        assert all(isinstance(f, np.ndarray) for f in frames), "Frames must be ndarray instances."
        # Here lies the image data for the layer.
        self.frames = frames
        self.version = 0

        self.animated = False

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

        self.visible = visible

    # def get_pic(self, frame=0):
    #     return self.frames[frame]

    def save_png(self, path, palette=None, frame=0):
        save_png(self.frames[frame], path, palette)

    @classmethod
    def load_png(cls, path):
        pic, info = load_png(path)
        return cls(pic), info["palette"]

    def draw_line(self, p0, p1, brush, offset, set_dirty=True, frame=0, **kwargs):
        ox, oy = offset
        x0, y0 = p0
        x1, y1 = p1
        p0 = (x0 - ox, y0 - oy)
        p1 = (x1 - ox, y1 - oy)
        pic = self.frames[frame]
        with self.lock:
            rect = draw_line(pic, brush, p0, p1)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        self.version += 1
        return rect

    def draw_ellipse(self, pos, size, brush, offset, set_dirty=True, fill=False, frame=0, **kwargs):
        if not fill:
            x0, y0 = pos
            ox, oy = offset
            pos = (x0 - ox, y0 - oy)
        pic = self.frames[frame]
        with self.lock:
            rect = draw_ellipse(pic, pos, size, brush, fill=fill, **kwargs)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        self.version += 1
        return rect

    def draw_rectangle(self, pos, size, brush, offset=(0, 0), set_dirty=True, color=0, fill=False, frame=0, **kwargs):
        if not fill:
            x0, y0 = pos
            ox, oy = offset
            pos = (x0 - ox, y0 - oy)
        pic = self.frames[frame]
        with self.lock:
            rect = draw_rectangle(pic, brush, pos, size, color, fill=fill)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        self.version += 1
        return rect

    def draw_fill(self, point, color, set_dirty=True, frame=0):
        pic = self.frames[frame]
        with self.lock:
            rect = draw_fill(pic, point, color)
            if rect and set_dirty:
                self.dirty = rect.unite(self.dirty)
        self.version += 1
        return rect

    def flip_vertical(self, frame=None):
        frames = [frame] if frame is not None else self.frames
        for i, frame in enumerate(frames):
            pic = self.frames[i]
            self.frames[i] = np.flip(pic, axis=1)
        self.dirty = self.rect
        self.version += 1

    def flip_horizontal(self, frame=None):
        frames = [frame] if frame is not None else self.frames
        for i, frame in enumerate(frames):
            pic = self.frames[i]
            self.frames[i] = np.flip(pic, axis=0)
        self.dirty = self.rect
        self.version += 1

    def swap_colors(self, index1, index2):
        #self.pic.swap_colors(index1, index2)
        color1_pixels = self.pic == index1
        color2_pixels = self.pic == index2
        self.pic[color1_pixels] = index2
        self.pic[color2_pixels] = index1
        self.dirty = self.rect
        self.version += 1

    @property
    def size(self):
        return self.frames[0].shape

    @property
    def rect(self):
        return self._get_rect(self.size)

    @lru_cache(1)
    def _get_rect(self, size):
        return Rectangle(size=size)

    def toggle_visibility(self):
        self.visible = not self.visible

    def clear(self, rect: Rectangle=None, value=0, set_dirty=True, frame=0):
        rect = rect or self.rect
        rect = self.rect.intersect(rect)
        if not rect:
            return
        pic = self.frames[frame]
        pic[rect.as_slice()] = value
        if set_dirty and rect:
            self.dirty = rect.unite(self.dirty)
        self.version += 1
        return rect

    def clone(self, dtype=dtype):
        with self.lock:
            return Layer([f.astype(dtype=dtype) for f in self.frames])

    def get_subimage(self, rect: Rectangle, frame=0):
        with self.lock:
            pic = self.frames[frame]
            return pic[rect.as_slice()].copy()

    def crop(self, rect: Rectangle):
        return Layer([self.get_subimage(i, rect)
                      for i in range(len(self.frames))])
        
    def blit(self, data, rect, set_dirty=True, alpha=True, frame=0):
        if not rect:
            return
        pic = self.frames[frame]
        with self.lock:
            if alpha:
                blit(pic, data, *rect.position)
            else:
                paste(pic, data, *rect.position)
            self.dirty = self.rect.intersect(rect.unite(self.dirty))
            
        self.version += 1
        return self.rect.intersect(rect)

    def blit_part(self, data, rect, dest, set_dirty=True, alpha=True, frame=0):
        pic = self.frames[frame]
        # TODO ...
        with self.lock:
            self.dirty = self.rect.intersect(rect.unite(self.dirty))
        self.version += 1
        return self.rect.intersect(rect)

    def make_diff(self, other, rect: Rectangle, alpha: bool=True, frame: int=0):
        pic = self.frames[frame]
        data = other.frames[frame]
        with self.lock:
            slc = rect.as_slice()
            mask = data[slc].astype(np.bool)
            return np.subtract(data[slc], mask * pic[slc], dtype=np.int16)

    def apply_diff(self, diff, rect, invert=False, frame=0):
        pic = self.frames[frame]
        slc = rect.as_slice()
        with self.lock:
            pic[slc] = np.add(pic[slc], diff, casting="unsafe")
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
