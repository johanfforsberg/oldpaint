from functools import lru_cache
from threading import RLock
from typing import Tuple, List

import numpy as np

from .rect import Rectangle
from .draw import draw_line, draw_rectangle, draw_ellipse, draw_fill, blit, paste
from .ora import load_png, save_png
from .util import DefaultList


class Layer:

    """
    An editable image.
    The image data is kept in one or more 2d numpy arrays, one per animation frame.
    Note that the frames are initialized whenever they are drawn to, so an
    empty frame is not allocated (it's represented by None).

    Layer generally should not be messed with directly. They should be modified via the
    containing Drawing instead, since that's where the undo system sits.
    """

    dtype = np.uint8

    def __init__(self, frames: List[np.ndarray]=None, size: Tuple[int, int]=None, visible:bool=True):
        if frames:
            assert all(isinstance(f, (np.ndarray, type(None))) for f in frames), "Frames must be ndarray instances."
            self.frames = DefaultList(list(frames))
            if size:
                self.size = size
            else:
                self.size = next(frame for frame in frames if frame is not None).shape[:2]
        else:
            assert size is not None, "Layer size must be specified."
            self.frames = DefaultList()
            self.size = size

        self.version = 0

        # This lock is important to hold while drawing, since otherwise the main thread might start
        # reading from it while we're writing.  It's reentrant so we don't have to worry about
        # collisions within the drawing thread.
        self.lock = RLock()

        # "dirty" is a rect that tells the visualisation that part of the picture has changed and
        # textures must be refreshed, after which it should set the dirty rect to None. From this
        # side, we should never shrink or remove the dirty rect, but growing it is fine.  Each frame
        # has its own dirty rect.
        # TODO Make sure that we only modify this while having the lock.
        self.dirty = {
            frame: self.rect
            for frame in range(len(self.frames))
        }

        self.visible = visible

    # def get_pic(self, frame=0):
    #     return self.frames[frame]

    def save_png(self, path:str, palette=None, frame=None):
        save_png(self.frames[frame], path, palette)

    def get_data(self, frame:int=0) -> np.ndarray:
        "Get the given frame, creating it if needed."
        data = self.frames[frame]
        if data is not None:
            return data
        data = np.zeros(self.size, dtype=self.dtype)
        self.frames[frame] = data
        return data

    def set_data(self, data: np.ndarray, frame:int=0):
        self.frames[frame] = data

    def get_dirty(self, frame: int=0):
        return self.dirty.get(frame)

    def set_dirty(self, rect: Rectangle, frame: int=0):
        if rect:
            self.dirty[frame] = dirty = rect.unite(self.dirty.get(frame))
            return dirty

    def clear_dirty(self, frame: int=0):
        self.dirty.pop(frame, None)
        
    def add_frame(self, index:int, data:np.ndarray):
        with self.lock:
            self.frames.insert(index, data)
            # TODO check this logic
            self.dirty = {
                (i if i <= index else i + 1): self.rect if i == index else rect
                for i, rect in self.dirty.items()
                if rect
            }
            self.dirty[index] = self.rect

    def remove_frame(self, index:int):
        with self.lock:
            self.frames.pop(index)
            # TODO check this logic
            self.dirty = {
                (i if i < index else i - 1): rect
                for i, rect in self.dirty.items()
                if i != index and rect
            }

    def swap_frames(self, index1, index2):
        frame1 = self.frames[index1]
        frame2 = self.frames[index2]
        self.frames[index1], self.frames[index2] = frame2, frame1
        self.dirty[index1] = self.dirty[index2] = self.rect
            
    @classmethod
    def load_png(cls, path:str):
        pic, info = load_png(path)
        return cls(pic), info["palette"]

    def draw_line(self, p0: Tuple[int, int], p1: Tuple[int, int], brush: np.ndarray,
                  offset: Tuple[int, int], set_dirty:bool=True, frame:int=0, **kwargs):
        ox, oy = offset
        x0, y0 = p0
        x1, y1 = p1
        p0 = (x0 - ox, y0 - oy)
        p1 = (x1 - ox, y1 - oy)
        data = self.get_data(frame)
        with self.lock:
            rect = draw_line(data, brush, p0, p1)
            if rect and set_dirty:
                self.set_dirty(rect, frame)
            self.version += 1
        return rect

    def draw_ellipse(self, pos:Tuple[int, int], size:Tuple[int, int], brush:np.ndarray,
                     offset:Tuple[int, int], set_dirty:bool=True, fill:bool=False, frame:int=0, **kwargs):
        if not fill:
            x0, y0 = pos
            ox, oy = offset
            pos = (x0 - ox, y0 - oy)
        data = self.get_data(frame)
        with self.lock:
            rect = draw_ellipse(data, brush, pos, size, fill=fill, **kwargs)
            if rect and set_dirty:
                self.set_dirty(rect, frame)
            self.version += 1
        return rect

    def draw_rectangle(self, pos:Tuple[int, int], size:Tuple[int, int], brush:np.ndarray,
                       offset:Tuple[int, int]=(0, 0), set_dirty:bool=True, color:int=0,
                       fill:bool=False, frame:int=0, **kwargs):
        if not fill:
            x0, y0 = pos
            ox, oy = offset
            pos = (x0 - ox, y0 - oy)
        data = self.get_data(frame)
        with self.lock:
            rect = draw_rectangle(data, brush, pos, size, color, fill=fill)
            if rect and set_dirty:
                self.set_dirty(rect, frame)
            self.version += 1
            return rect

    def draw_fill(self, source: np.ndarray, point:Tuple[int, int], color:int, set_dirty:bool=True, frame:int=0):
        pic = self.get_data(frame)
        with self.lock:
            rect = draw_fill(source, pic, point, color)
            if rect and set_dirty:
                # self.dirty[frame] = rect.unite(self.dirty.get(frame))
                self.set_dirty(rect, frame)
            self.version += 1
        return rect

    def flip(self, frame, axis):
        if frame is not None:
            with self.lock:
                data = self.get_data(frame)
                self.set_data(np.flip(data, axis=axis), frame)
                self.set_dirty(self.rect, frame)
                self.version += 1
        else:
            for i, data in enumerate(self.frames):
                if data is not None:
                    with self.lock:
                        self.set_data(np.flip(data, axis=axis), i)
                        self.set_dirty(self.rect, i)
                        self.version += 1
        return self.rect
        
    def flip_horizontal(self, frame:int=None):
        self.flip(frame, axis=0)
        return self.rect
   
    def flip_vertical(self, frame:int=None):
        self.flip(frame, axis=1)
        return self.rect

    def swap_colors(self, index1:int, index2:int, frame:int=None):
        frames = [self.get_data(frame)] if frame is not None else self.frames
        for i, data in enumerate(frames):
            if data is not None:
                with self.lock:
                    color1_pixels = data == index1
                    color2_pixels = data == index2
                    data[color1_pixels] = index2
                    data[color2_pixels] = index1
                    self.set_dirty(self.rect, i)
                    self.version += 1
                return self.rect

    # @property
    # def size(self):
    #     return self.frames[0].shape

    @property
    def rect(self):
        return self._get_rect(self.size)

    @lru_cache(1)
    def _get_rect(self, size:Tuple[int, int]):
        return Rectangle(size=size)

    def toggle_visibility(self):
        self.visible = not self.visible

    def clear(self, rect:Rectangle=None, value:int=0, set_dirty:bool=True, frame:int=0):
        rect = rect or self.rect
        rect = self.rect.intersect(rect)
        data = self.get_data(frame)
        if rect and data is not None:
            with self.lock:
                data[rect.as_slice()] = value
                if set_dirty and rect:
                    self.set_dirty(rect, frame)
                self.version += 1
            return rect

    def clone(self, dtype=dtype):
        with self.lock:
            return Layer([(f.astype(dtype=dtype, copy=True) if f is not None else None)
                          for f in self.frames])

    def get_subimage(self, rect:Rectangle, frame:int=0) -> np.ndarray:
        """
        Return a section of the layer.
        Note that this is a view, not a copy, so any changes to it happen in the original layer.
        """
        with self.lock:
            data = self.frames[frame]
            if data is not None:
                return data[rect.as_slice()]
            else:
                # Layer is not yet realized, return empty dummy data
                return np.zeros(rect.size, dtype=self.dtype)

    def crop(self, rect:Rectangle):
        return Layer([self.get_subimage(rect, i)
                      for i in range(len(self.frames))])
    
    def blit(self, new_data:np.ndarray, rect:Rectangle, set_dirty:bool=True, alpha:bool=True, frame:int=0):
        if not rect:
            return
        data = self.get_data(frame)
        from_rect = rect.intersect(self.rect)
        to_rect = self.rect.intersect(rect)
        if not from_rect:
            return
        with self.lock:
            from_slc = from_rect.as_slice()
            to_slc = to_rect.as_slice()
            dest = data[to_slc]            
            source = new_data[from_slc]
            if alpha:
                mask = source >> 24
                dest[:] = np.where(mask, source, dest).astype(self.dtype)
            else:
                dest[:] = source
            self.dirty[frame] = self.rect.intersect(rect.unite(self.dirty.get(frame)))
            
        self.version += 1
        return rect
    
    def make_diff(self, other:np.ndarray, rect:Rectangle, alpha:bool=True, frame:int=0):
        data = self.get_data(frame)
        data = data if data is not None else np.zeros(self.size, dtype=np.uint8)
        # TODO this assumes that "other" is an overlay, not good.
        new_data = other.get_data()
        with self.lock:
            slc = rect.as_slice()
            mask = new_data[slc].astype(np.bool)
            return np.subtract(new_data[slc], mask * data[slc], dtype=np.int16)

    def apply_diff(self, diff:np.ndarray, rect:Rectangle, invert:bool=False, frame:int=0):
        data = self.get_data(frame)
        slc = rect.as_slice()
        with self.lock:
            data[slc] = np.add(data[slc], diff, casting="unsafe")
            self.set_dirty(rect, frame)
        self.version += 1

    def __repr__(self):
        return f"Layer(id={id(self)}, size={self.size}, pic={self.pic})"
    
    def __hash__(self):
        "For caching purposes, a Layer is considered changed when it's underlying data has changed."
        return hash((id(self), self.size, self.version))


class TemporaryLayer(Layer):

    dtype = np.uint32
    
    def __hash__(self):
        return hash((id(self), self.size))
