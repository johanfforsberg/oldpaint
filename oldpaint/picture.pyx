#cython: language_level=3, boundscheck=False, wraparound=False, initializedcheck=False, cdivision=True

# TODO Clean up this mess.

from cpython cimport array
import ctypes
import cython
from cython cimport view
from itertools import chain

import png

from .rect import Rectangle
from .rect cimport Rectangle


cdef byte_array_template = array.array('B', [])   # Used for creating empty arrays quickly
cdef short_array_template = array.array('h', [])   # Used for creating empty arrays quickly
cdef long_array_template = array.array('I', [])


cpdef unsigned int _rgba_to_32bit((int, int, int, int) color) nogil:
    cdef int r, g, b, a
    r, g, b, a = color
    cdef unsigned int result = r + g*2**8 + b*2**16 + a*2**24
    return result


cpdef unsigned int _rgb_to_32bit((int, int, int) color) nogil:
    cdef int r, g, b
    r, g, b = color
    return _rgba_to_32bit((r, g, b, 255))


def rgba_to_32bit(r, g, b, a):
    return _rgba_to_32bit((r, g, b, a))


def load_png(dest):
    w, h, rows, info = png.Reader(dest).read()
    data = chain.from_iterable(rows)
    if info.get("palette"):
        return LongPicture((w, h), data), info["palette"]
    else:
        return LongPicture((w, h), data), None


def save_png(pic, dest, palette=None):
    w, h = pic.size
    writer = png.Writer(w, h, bitdepth=8, alpha=False, palette=palette)
    # TODO Kind of hacky, but we only care about the first byte of every four
    # since we're writing indexed images.
    rows = (bytearray(pic.data[offset:offset + w])[::4]
            for offset in range(0, pic.length, w))
    writer.write(dest, rows)


@cython.final
cdef class LongPicture:

    """
    A low level, bare bones but reasonably fast, image implementation.
    Supports 8 bit RGBA images.
    """

    pixel_format = "I"  # unsigned int (should be 32bit)

    def __init__(self, (int, int) size, data=None):
        self.width, self.height = self.size = size
        self.length = self.width * self.height
        if data is not None:
            self.data = array.array(self.pixel_format, data)
            assert len(self.data) == self.length, f"Data must have correct size {self.length}, has {len(self.data)}."
        else:
            self.data = array.clone(long_array_template, self.length, zero=True)
        self.rect = Rectangle((0, 0), (self.width, self.height))

    cdef int _get_offset(self, int x, int y) nogil:
        return self.width * y + x

    cdef void set_pixel(self, int x, int y, unsigned int value) nogil:
        cdef int offset
        if (0 <= x < self.width) & (0 <= y < self.height):
            offset = self._get_offset(x, y)
            self.data[offset] = value

    cpdef unsigned int get_pixel(self, int x, int y):
        cdef int offset
        if (0 <= x < self.width) & (0 <= y < self.height):
            offset = self._get_offset(x, y)
            return self.data[offset] & 0xFF
        raise ValueError(f"The given coordinates {x}, {y} lie outside of the picture!")

    def __getitem__(self, (int, int) pos):
        cdef int x, y
        x, y = pos
        return self.get_pixel(x, y)

    def __setitem__(self, (int, int) pos, unsigned int value):
        cdef int x, y
        x, y = pos
        self.set_pixel(x, y, value)

    cpdef LongPicture crop(self, int x, int y, int w, int h):
        "Return a new picture, contaning a copy of the given part of the picture."
        cdef LongPicture cropped = LongPicture((w, h))
        cdef int i, j, offset, start, x1, y1
        offset = self._get_offset(x, y)
        start = 0
        for y1 in range(h):
            for x1 in range(w):
                cropped.data[start+x1] = self.data[offset+x1]
            offset += self.width
            start += w
        return cropped

    cpdef void fix_alpha(self, list colors):
        """
        Ensure that the given transparent colors really have 0 alpha.
        This is important for brushes.
        """
        cdef int x, y, w, h
        cdef unsigned char c
        w, h = self.size
        for x in range(w):
            for y in range(h):
                c = self.get_pixel(x, y)
                if self.get_pixel(x, y) % 255 in colors:
                    self.set_pixel(x, y, c % 255)

    cpdef void paste(self, LongPicture pic, int x, int y, bint mask,
                     bint colorize=False, unsigned char color=0) nogil:
        "Modify the current picture by overlaying the given picture at the x, y position"
        cdef int w, h, y1, x1, x2, y2, offset1, offset2
        w, h = pic.size
        offset1 = 0
        offset2 = self._get_offset(x, y)
        cdef unsigned int[:] data = pic.data
        for y1 in range(h):
            y2 = y + y1
            if (y2 < 0):
                offset1 += w
                offset2 += self.width
                continue
            if (y2 >= self.height):
                break
            for x1 in range(w):
                x2 = x + x1
                if (x2 < 0):
                    continue
                if (x2 >= self.width):
                    break
                if not mask or pic.data[offset1+x1] >> 24:  # Ignore 100% transparent pixels
                    if colorize:
                        self.set_pixel(x2, y2, _rgba_to_32bit((color, 0, 0, 255)))
                    else:
                        self.set_pixel(x2, y2, pic.data[offset1+x1])
            offset1 += w
            offset2 += self.width

    cpdef void paste_part(self, LongPicture pic, int xo, int yo, int w, int h, int xd, int yd, bint mask) nogil:
        "Modify the current picture by overlaying the given region of the picture at the xd, yd position"
        cdef int y1, x1, x2, y2, offset1, offset2
        offset1 = pic._get_offset(xo, yo)
        offset2 = self._get_offset(xd, yd)
        cdef unsigned int[:] data = pic.data
        for y1 in range(h):
            y2 = yd + y1
            if (y2 < 0):
                offset1 += pic.width
                offset2 += self.width
                continue
            if (y2 >= self.height):
                break
            for x1 in range(w):
                x2 = xd + x1
                if (x2 < 0):
                    continue
                if (x2 >= self.width):
                    break
                if not mask or pic.data[offset1+x1] >> 24:  # Ignore 100% transparent pixels
                    self.set_pixel(x2, y2, data[offset1+x1])
            offset1 += pic.width
            offset2 += self.width

    cpdef short[:] make_diff(self, LongPicture pic, int x, int y, int w, int h):
        cdef short[:] difference = array.clone(short_array_template, w * h, zero=True)
        cdef int i, j, offset, start, x1, y1
        offset = self._get_offset(x, y)
        start = 0
        for y1 in range(h):
            for x1 in range(w):
                if pic.data[offset+x1] >> 24:
                    difference[start+x1] = (pic.data[offset+x1] & 255) - (self.data[offset+x1] & 255)
            offset += self.width
            start += w
        return difference

    cpdef void apply_diff(self, const short[:] difference, int x, int y, int w, int h, bint invert):
        cdef int i, j, offset, start, x1, y1
        cdef unsigned int value
        cdef short diff

        offset = self._get_offset(x, y)
        start = 0
        if invert:
            for y1 in range(h):
                for x1 in range(w):
                    value = self.data[offset+x1]
                    diff = difference[start+x1]
                    self.set_pixel(x + x1, y + y1, value - diff)
                offset += self.width
                start += w
        else:
            for y1 in range(h):
                for x1 in range(w):
                    value = self.data[offset+x1]
                    diff = difference[start+x1]
                    self.set_pixel(x + x1, y + y1, value + diff)
                offset += self.width
                start += w

    # cpdef void paste_byte(self, Picture pic, int x, int y, bint mask):
    #     cdef int w, h, y1, x1, x2, y2, offset1, offset2
    #     cdef unsigned int p
    #     w, h = pic.size
    #     offset1 = 0
    #     offset2 = self._get_offset(x, y)
    #     for y2 in range(y, y+h):
    #         if (y2 < 0):
    #             offset1 += w
    #             offset2 += self.width
    #             continue
    #         if (y2 >= self.height):

    #             break
    #         for x1 in range(w):
    #             x2 = x + x1
    #             if (x2 < 0):
    #                 continue
    #             if (x2 >= self.width):
    #                 break
    #             p = pic.data[offset1+x1]
    #             # TODO here we hardcode color 0 as transparent.
    #             self.data[offset2+x1] = p + bool(p) * 255*2**24
    #         offset1 += w
    #         offset2 += self.width

    cpdef void clear(self, (int, int, int, int) box, unsigned int value) nogil:
        cdef int x, y
        cdef int w = self.width, h = self.height
        cdef int x0, y0, x1, y1
        x0, y0, x1, y1 = box
        x0 = max(0, x0)
        x1 = min(w, x1)
        y0 = max(0, y0)
        y1 = min(h, y1)
        for x in range(x0, x1):
            for y in range(y0, y1):
                self.data[y * w + x] = value

    cpdef LongPicture flip_vertical(self):
        # TODO this is probably not the fastest way, but this shouldn't be a time critical op
        cdef LongPicture flipped = LongPicture(self.size)
        cdef x, y, y2
        for y in range(self.height):
            y2 = self.height - y - 1
            for x in range(self.width):
                flipped[x, y] = self.get_pixel(x, y2)
        return flipped

    cpdef LongPicture flip_horizontal(self):
        cdef LongPicture flipped = LongPicture(self.size)
        cdef x, y
        for y in range(self.height):
            for x in range(self.width):
                flipped[x, y] = self.get_pixel(self.width-x-1, y)
        return flipped

    cpdef unsigned int[:] as_rgba(self, palette, bint alpha):
        cdef unsigned int[:] data
        if alpha:
            data = array.array(LongPicture.pixel_format,
                               [_rgba_to_32bit(palette[p & 0x000000FF]) for p in self.data])
        else:
            data = array.array(LongPicture.pixel_format,
                               [_rgb_to_32bit(palette[p & 0x000000FF][:3]) for p in self.data])
        return data

    def __repr__(self):
        return f"LongPicture({self.size})"
