#cython: language_level=3, boundscheck=False, wraparound=False, initializedcheck=False, cdivision=True

from cpython cimport array

cpdef unsigned int _rgba_to_32bit((int, int, int, int) color) nogil
cpdef unsigned int _rgb_to_32bit((int, int, int) color) nogil


# cdef class Picture:

#     cdef readonly (int, int) size
#     cdef readonly int width, height, stride, length
#     cdef public unsigned char[:] data
#     # cdef public array.array data
#     cdef public rect

#     cdef int _get_offset(self, int x, int y) nogil
#     cpdef get_ptr(self)
#     cdef void set_pixel(self, int x, int y, unsigned int value)
#     cpdef unsigned int get_pixel(self, int x, int y)
#     cpdef Picture crop(self, int x, int y, int w, int h)
#     cpdef void paste(self, Picture pic, int x, int y, bint mask) nogil
#     cpdef void paste_long(self, LongPicture pic, int x, int y, bint mask)
#     cpdef void clear(self, (int, int, int, int) box, unsigned int value) nogil
#     cpdef Picture flip_vertical(self)
#     cpdef Picture flip_horizontal(self)
#     cpdef LongPicture as_rgba(self, palette, bint alpha)


cdef class LongPicture:

    # TODO inheritance

    cdef readonly (int, int) size
    cdef readonly int width, height, stride, length
    cdef public unsigned int[:] data
    cdef public rect

    cdef int _get_offset(self, int x, int y) nogil
    cdef void set_pixel(self, int x, int y, unsigned int value) nogil
    cpdef unsigned int get_pixel(self, int x, int y)
    cpdef LongPicture crop(self, int x, int y, int w, int h)
    cpdef void fix_alpha(self, list colors)
    cpdef void paste(self, LongPicture pic, int x, int y, bint mask, bint colorize=*, unsigned char color=*) nogil
    cpdef void paste_part(self, LongPicture pic, int xo, int yo, int w, int h, int xd, int yd, bint mask) nogil
    # cpdef void paste_byte(self, Picture pic, int x, int y, bint mask)
    cpdef void clear(self, (int, int, int, int) box, unsigned int value) nogil
    cpdef LongPicture flip_vertical(self)
    cpdef LongPicture flip_horizontal(self)
    cpdef unsigned int[:] as_rgba(self, palette, bint alpha)
    cpdef short[:] make_diff(self, LongPicture pic, int x, int y, int w, int h)
    cpdef void apply_diff(self, const short[:] difference, int x, int y, int w, int h, bint invert)
