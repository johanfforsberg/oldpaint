from cpython cimport array

cpdef unsigned int _rgba_to_32bit((int, int, int, int) color)
cpdef unsigned int _rgb_to_32bit((int, int, int) color)


cdef class Picture:

    cdef readonly (int, int) size
    cdef readonly int width, height, stride, length
    # cdef public unsigned char[:] data
    cdef public array.array data
    cdef public rect

    cdef int _get_offset(self, int x, int y)
    cdef void set_pixel(self, int x, int y, unsigned int value)
    cpdef unsigned int get_pixel(self, int x, int y)
    cpdef Picture crop(self, int x, int y, int w, int h)
    cpdef void paste(self, Picture pic, int x, int y, bint mask)
    cpdef void paste_long(self, LongPicture pic, int x, int y, bint mask)
    cpdef void clear(self, (int, int, int, int) box, unsigned int value)
    cpdef Picture flip_vertical(self)
    cpdef Picture flip_horizontal(self)
    cpdef LongPicture as_rgba(self, palette, bint alpha)


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
    cpdef void paste(self, LongPicture pic, int x, int y, bint mask) nogil
    cpdef void clear(self, (int, int, int, int) box, unsigned int value)
    cpdef LongPicture flip_vertical(self)
    cpdef LongPicture flip_horizontal(self)
    cpdef LongPicture as_rgba(self, palette, bint alpha)
