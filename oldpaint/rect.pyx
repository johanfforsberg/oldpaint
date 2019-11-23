cdef class Rectangle:

    """
    A Rectangle describes a rectangular, axis aligned 2D area.
    It's immutable, but can be combined with other rectangles in useful ways.
    """

    def __init__(self, (int, int) position=(0, 0), (int, int) size=(0, 0)):
        self.position = position
        self.size = size
        self.x = self.left = position[0]
        self.y = self.top = position[1]
        self.width = self.size[0]
        self.height = self.size[1]
        self.right = self.x + self.width
        self.bottom = self.y + self.height
        self.topleft = (self.left, self.top)
        self.bottomright = (self.right, self.bottom)

    def __bool__(self):
        return self.width > 0 and self.height > 0

    def __repr__(self):
        return "Rect(pos=(%d, %d), size=(%d, %d))" % (self.x, self.y,
                                                      self.width, self.height)

    def __hash__(self):
        self.x + self.y*2**8 + self.width*2**16 + self.height*2**24

    cpdef Rectangle copy(self):
        return Rectangle(self.position, self.size)

    cpdef Rectangle intersect(self, Rectangle other):
        "Return the rectangle that covers the intersection of self and other."
        if not other:
            return None

        # check if the rects overlap at all
        if ((self.right <= other.left) | (self.left >= other.right) |
                (self.bottom <= other.top) | (self.top >= other.bottom)):
            return None

        cdef int x = max(self.left, other.left)
        cdef int y = max(self.top, other.top)
        return Rectangle((x, y), (min(self.right, other.right) - x,
                                  min(self.bottom, other.bottom) - y))

    cpdef Rectangle unite(self, Rectangle other):
        "Return the smallest rectangle that covers both self and other."
        if other is None:
            return self
        cdef int x = min(self.left, other.left)
        cdef int y = min(self.top, other.top)
        cdef int w = max(self.right, other.right) - x
        cdef int h = max(self.bottom, other.bottom) - y
        return Rectangle((x, y), (w, h))

    def __contains__(self, (int, int) point):
        cdef int x, y
        x, y = point
        return (self.left <= x < self.right) & (self.top <= y < self.bottom)

    cdef (int, int, int, int) get_points(self):
        return self.x, self.y, self.width, self.height

    def __iter__(self):
        return iter(self.get_points())

    @property
    def points(self):
        return self.get_points()

    def box(self):
        # Pillow compatible box
        return self.left, self.top, self.right, self.bottom

    cpdef Rectangle expanded(self, (int, int) point):
        "Return the smallest rectangle that contains self and also the given point."
        if point in self:
            return self
        cdef int x, y
        x, y = point
        cdef int left, top
        left, top = min(x, self.left), min(y, self.top)
        return Rectangle((left, top), (max(self.right, x) - left, max(self.bottom, y) - top))

    cpdef int area(self):
        return self.width * self.height


cpdef Rectangle from_points(list pts):
    """ Create the smallest rectangle that contains the given points (any number of (x, y) tuples). """
    cdef tuple xs, ys
    xs, ys = zip(*pts)
    cdef int minx, miny, maxx, maxy
    minx, miny = min(xs), min(ys)
    maxx, maxy = max(xs), max(ys)
    cdef int w, h
    w, h = maxx - minx, maxy - miny
    return Rectangle((minx, miny), (w, h))


cpdef Rectangle cover(list rects):
    "Return a rect that covers all the given rects."
    cdef Rectangle rect, result = None
    for rect in rects:
        if not rect:
            continue
        result = rect.unite(result)
    return result
