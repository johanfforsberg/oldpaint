#cython: language_level=3
"""
Implementations of primitive drawing operations on numpy arrays.
"""

cimport cython

from libc.stdlib cimport abs as iabs

import numpy as np
cimport numpy as np

from .rect cimport Rectangle

cdef extern from "math.h":
    double floor(double x)
    double ceil(double x)

@cython.boundscheck(False)
@cython.wraparound(False)
cpdef void paste(unsigned int[:, :] pic, unsigned int[:, :] brush, int x, int y) nogil:
    "Copy image data without caring about transparency"
    cdef int w, h, bw, bh
    w, h = pic.shape[:2]
    bw, bh = brush.shape[:2]

    cdef int px0, px1, py0, py1, bx0, bx1, by0, by1
    px0 = max(0, x)
    px1 = min(w, x + bw)
    py0 = max(0, y)
    py1 = min(h, y + bh)
    if (px0 < px1) and (py0 < py1):
        bx0 = px0 - x
        bx1 = px1 - x
        by0 = py0 - y
        by1 = py1 - y
        pic[px0:px1, py0:py1] = brush[bx0:bx1, by0:by1]


@cython.boundscheck(False)
@cython.wraparound(False)
cpdef Rectangle blit(unsigned int[:, :] pic, unsigned char[:, :] brush, int x, int y):
    # TODO consider rewriting this to use numpy instead, see layer.blit.
    # Not sure if it would be faster but it's more general and it hurts a little
    # to have two ways of doing the same thing...
    "Draw a brush onto an image, skipping transparent pixels."
    cdef int w, h, bw, bh, y1, x1, x2, y2, xmin, ymin, xmax, ymax
    w, h = pic.shape[:2]
    bw, bh = brush.shape[:2]
    with nogil:
        xmin = w
        ymin = h
        xmax = 0
        ymax = 0
        for y1 in range(bh):
            y2 = y + y1
            if (y2 < 0):
                continue
            if (y2 >= h):
                break
            for x1 in range(bw):
                x2 = x + x1
                if (x2 < 0):
                    continue
                if (x2 >= w):
                    break
                if brush[x1, y1] >> 24:  # Ignore 100% transparent pixels
                    pic[x2, y2] = brush[x1, y1]
                    # TODO I think this can be done in a smarter way.
                    xmin = min(xmin, x2)
                    xmax = max(xmax, x2)
                    ymin = min(ymin, y2)
                    ymax = max(ymax, y2)
    return Rectangle((xmin, ymin), (xmax - xmin + 1, ymax - ymin + 1))


@cython.boundscheck(False)
@cython.wraparound(False)
cdef void _cblit(unsigned int[:, :] pic, unsigned int[:, :] brush, int x, int y) nogil:
    "Draw a brush onto an image, skipping transparent pixels."
    # Faster version for internal use in this module.
    cdef int w, h, bw, bh, y1, x1, x2, y2
    w, h = pic.shape[:2]
    bw, bh = brush.shape[:2]
    for y1 in range(bh):
        y2 = y + y1
        if (y2 < 0):
            continue
        if (y2 >= h):
            break
        for x1 in range(bw):
            x2 = x + x1
            if (x2 < 0):
                continue
            if (x2 >= w):
                break
            if brush[x1, y1] >> 24:  # Ignore 100% transparent pixels
                pic[x2, y2] = brush[x1, y1]


@cython.boundscheck(False)
@cython.wraparound(False)
cpdef draw_line(unsigned int[:, :] pic, unsigned int[:, :] brush,
                (int, int) p0, (int, int) p1, int step=1):

    "Draw a straight line from p0 to p1 using a brush."

    cdef int x, y, w, h, x0, y0, x1, y1, dx, sx, dy, sy, err, bw, bh
    x, y = p0
    x0, y0 = p0
    x1, y1 = p1
    dx = iabs(x1 - x)
    sx = 1 if x < x1 else -1
    dy = -iabs(y1 - y)
    sy = 1 if y < y1 else -1
    err = dx+dy
    bw = brush.shape[0]
    bh = brush.shape[1]
    w, h = pic.shape[:2]

    cdef int i = 0
    cdef int e2

    cdef int px0, px1, py0, py1, bx0, bx1, by0, by1
    cdef unsigned int[:, :] src, dst
    cdef Rectangle r

    with nogil:
        while True:
            if i % step == 0:
                _cblit(pic, brush, x, y)
            if x == x1 and y == y1:
                break
            e2 = 2*err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy
            i += 1

    cdef int x00 = max(0, min(x0, x1))
    cdef int y00 = max(0, min(y0, y1))
    cdef int x11 = min(w, max(x0, x1) + bw)
    cdef int y11 = min(h, max(y0, y1) + bh)

    return Rectangle((x00, y00), (x11 - x00, y11 - y00))


@cython.boundscheck(False)
@cython.wraparound(False)
cdef void cdraw_line(unsigned int[:, :] pic, unsigned int[:, :] brush,
                     (int, int) p0, (int, int) p1, int step=1) nogil:

    "Draw a straight line from p0 to p1 using a brush."

    cdef int x, y, w, h, x0, y0, x1, y1, dx, sx, dy, sy, err, bw, bh
    x, y = p0
    x0, y0 = p0
    x1, y1 = p1
    dx = iabs(x1 - x)
    sx = 1 if x < x1 else -1
    dy = -iabs(y1 - y)
    sy = 1 if y < y1 else -1
    err = dx+dy
    bw = brush.shape[0]
    bh = brush.shape[1]
    w, h = pic.shape[:2]

    cdef int i = 0
    cdef int e2

    cdef int px0, px1, py0, py1, bx0, bx1, by0, by1
    cdef unsigned int[:, :] src, dst

    while True:
        if i % step == 0:
            _cblit(pic, brush, x, y)
        if x == x1 and y == y1:
            break
        e2 = 2*err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy

    cdef int x00 = max(0, min(x0, x1))
    cdef int y00 = max(0, min(y0, y1))
    cdef int x11 = min(w, max(x0, x1) + bw)
    cdef int y11 = min(h, max(y0, y1) + bh)


@cython.boundscheck(False)
@cython.wraparound(False)
cpdef draw_quad(unsigned int[:, :] pic,
                (float, float) p0, (float, float) p1, (float, float) p2, (float, float) p3,
                unsigned int color):

    cdef int min_x, max_x, min_y, max_y;
    cdef float x0, y0, x1, y1, x2, y2, x3, y3
    x0, y0 = p0
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    min_x = floor(min(x0, min(x1, min(x2, x3))))
    max_x = ceil(max(x0, max(x1, max(x2, x3))))
    min_y = floor(min(y0, min(y1, min(y2, y3))))
    max_y = ceil(max(y0, max(y1, max(y2, y3))))

    cdef int x
    cdef int y = min_y
    cdef bint inside
    while y <= max_y:
        x = min_x
        while x <= max_x:
            inside = False
            if ((y0 > y) != (y3 > y)) and (x < ((x3 - x0) * (y - y0) / (y3 - y0) + x0)):
                inside = not inside
            if ((y1 > y) != (y0 > y)) and (x < ((x0 - x1) * (y - y1) / (y0 - y1) + x1)):
                inside = not inside
            if ((y2 > y) != (y1 > y)) and (x < ((x1 - x2) * (y - y2) / (y1 - y2) + x2)):
                inside = not inside
            if ((y3 > y) != (y2 > y)) and (x < ((x2 - x3) * (y - y3) / (y2 - y3) + x3)):
                inside = not inside
            if inside:
                pic[x, y] = color
            x += 1
        y += 1

    return Rectangle((min_x, min_y), (max_x - min_x, max_y - min_y))


@cython.boundscheck(False)
@cython.wraparound(False)
cpdef draw_rectangle(unsigned int[:, :] pic, unsigned int[:, :] brush,
                     (int, int) pos, (int, int) size,
                     unsigned int color, bint fill=False):
    cdef int x0, y0, w0, h0, x, y, w, h, cols, rows, bw, bh

    x0, y0 = pos
    w0, h0 = size

    # ensure that the rectangle stays within the image borders
    x = max(0, x0)
    y = max(0, y0)
    w = w0 - (x - x0)
    h = h0 - (y - y0)

    cols, rows = pic.shape[:2]
    w = min(cols - x, w)
    h = min(rows - y, h)

    with nogil:
        if fill:
            pic[x:x+w, y:y+h] = color
        else:
            cdraw_line(pic, brush, pos, (x0+w0, y0))
            cdraw_line(pic, brush, (x0+w0, y0), (x0+w0, y0+h0))
            cdraw_line(pic, brush, (x0+w0, y0+h0), (x0, y0+h0))
            cdraw_line(pic, brush, (x0, y0+h0), pos)   

    bw, bh = brush.shape[:2]

    cdef Rectangle pic_rect = Rectangle((0, 0), (cols, rows))
    return pic_rect.intersect(Rectangle((x, y), (min(cols, w + bw), min(rows, h + bh))))


@cython.boundscheck(False)
@cython.wraparound(False)
cpdef draw_ellipse(unsigned int[:, :] pic, unsigned int[:, :] brush,
                   (int, int) center, (int, int) size,
                   unsigned int color, bint fill=False):

    cdef int w, h, a, b, x0, y0, a2, b2, error, x, y, stopx, stopy, hw, hh

    a, b = size
    if a <= 0 or b <= 0:
        return None
    x0, y0 = center

    a2 = 2*a*a
    b2 = 2*b*b
    error = a*a*b

    x = 0
    y = b
    stopy = 0
    stopx = a2 * b
    hw = brush.shape[0] // 2
    hh = brush.shape[1] // 2

    w, h = pic.shape[:2]

    cdef int xx, yy
    cdef int topy, boty, lx, rx

    if b == 0:
        if fill:
            lx = min(w-1, max(0, x0 - a))
            rx = max(0, min(w, x0 + a + 1))
            cdraw_line(pic, brush, (lx, y0), (rx, y0), color)
            rect = Rectangle((x0-a, y0), (2*a+1, 1))
        else:
            rect = draw_line(pic, brush, (x0-a, y0), (x0+a+1, y0))
        return pic.rect.intersect(rect)

    if a == 0:
        if fill and color:
            rect = draw_rectangle(pic, brush, (x0, y0-b), (1, 2*b+1), color=color, fill=True)
        else:
            rect = draw_line(pic, brush, (x0, y0-b), (x0, y0+b+1))
        return pic.rect.intersect(rect)

    with nogil:
        while stopy <= stopx:
            topy = y0 - y
            boty = y0 + y
            if fill:
                lx = min(w-1, max(0, x0 - x))
                rx = max(0, min(w, x0 + x + 1))
                if topy >= 0:
                    pic[lx:rx, topy] = color
                if boty < h:
                    pic[lx:rx, boty] = color
            else:
                _cblit(pic, brush, x0 + x - hw, y0 + y - hh)
                _cblit(pic, brush, x0 - x - hw, y0 + y - hh)
                _cblit(pic, brush, x0 - x - hw, y0 - y - hh)
                _cblit(pic, brush, x0 + x - hw, y0 - y - hh)

            x += 1
            error -= b2 * (x - 1)
            stopy += b2
            if error <= 0:
                error += a2 * (y - 1)
                y -= 1
                stopx -= a2

        error = b*b*a
        x = a
        y = 0
        stopy = b2 * a
        stopx = 0

        while stopy >= stopx:
            topy = y0 - y
            boty = y0 + y
            if fill:
                lx = min(w-1, max(0, x0 - x))
                rx = max(0, min(w, x0 + x + 1))
                if topy >= 0:
                    pic[lx:rx, topy] = color
                if boty < h:
                    pic[lx:rx, boty] = color
            else:
                _cblit(pic, brush, x0 + x - hw, y0 + y - hh)
                _cblit(pic, brush, x0 - x - hw, y0 + y - hh)
                _cblit(pic, brush, x0 - x - hw, y0 - y - hh)
                _cblit(pic, brush, x0 + x - hw, y0 - y - hh)           

            y += 1
            error -= a2 * (y - 1)
            stopx += a2
            if error < 0:
                error += b2 * (x - 1)
                x -= 1
                stopy -= b2

    cdef Rectangle pic_rect = Rectangle((0, 0), (w, h))            
    return pic_rect.intersect(Rectangle((x0-a-hw-1, y0-b-hh-1), (2*a+2*hw+2, 2*b+2*hh+2)))


@cython.boundscheck(False)
@cython.wraparound(False)
cpdef draw_fill(unsigned char[:, :] pic, unsigned int[:, :] dest,
                (int, int) point, unsigned int color):

    # TODO kind of slow, and requires the GIL.

    cdef int startx, starty, w, h
    startx, starty = point
    cdef list stack = [point]  # TODO maybe find some more C friendly way of keeping a stack
    w, h = pic.shape[:2]
    cdef unsigned char start_col = pic[startx, starty]

    if start_col == color & 0xFF:
        return

    cdef int x, y, xmin, xmax, ymin, ymax, xstart
    cdef bint reach_top, reach_bottom
    xmin, xmax = w, 0
    ymin, ymax = h, 0

    while stack:
        x, y = stack.pop()
        # search left
        while x >= 0 and start_col == pic[x, y] and dest[x, y] != color:
            x -= 1
        x += 1
        reach_top = reach_bottom = False

        # search right
        while x < w and pic[x, y] == start_col and dest[x, y] != color:
            dest[x, y] = color  # color this pixel
            xmin, xmax = min(xmin, x), max(xmax, x)
            ymin, ymax = min(ymin, y), max(ymax, y)
            if 0 < y < h - 1:

                # check pixel above
                if start_col == pic[x, y-1]:
                    if not reach_top:
                        stack.append((x, y-1))  # add previous line
                        reach_top = True
                elif reach_top:
                    reach_top = False

                # check pixel below
                if start_col == pic[x, y+1]:
                    if not reach_bottom:
                        stack.append((x, y+1))  # add next line
                        reach_bottom = True
                elif reach_bottom:
                    reach_bottom = False
            x += 1

    return Rectangle((xmin, ymin), (xmax-xmin+1, ymax-ymin+1))


@cython.boundscheck(False)
@cython.wraparound(False)
cpdef np.ndarray[np.uint8_t, ndim=2] rescale(unsigned char[:, :] pic, (int, int) size):
    "Scale an image to the given size, by 'nearest neighbor' interpolation."
    cdef int w, h, w0, h0, x, y, i, j
    cdef np.ndarray[np.uint8_t, ndim=2] result
    w, h = size
    w0, h0 = pic.shape[:2]
    result = np.zeros(size, dtype=np.uint8)
    for x in range(w):
        for y in range(h):
            i = round(w0 * x / w)
            j = round(h0 * y / h)
            result[x, y] = pic[i, j]
    return result
