from .picture cimport LongPicture
from .rect cimport Rectangle


cdef unsigned int _rgba_to_32bit((int, int, int, int) color) nogil:
    cdef int r, g, b, a
    r, g, b, a = color
    cdef unsigned int result = r + g*2**8 + b*2**16 + a*2**24
    return result


cdef unsigned int _rgb_to_32bit((int, int, int) color) nogil:
    cdef int r, g, b
    r, g, b = color
    return _rgba_to_32bit((r, g, b, 255))


cpdef draw_line(LongPicture pic, (int, int) p0, (int, int) p1, LongPicture brush=None, unsigned int color=0, int step=1, bint set_dirty=True):

    "Draw a line from p0 to p1 using a brush."

    cdef int x, y, w, h, x0, y0, x1, y1, dx, sx, dy, sy, err, bw, bh, hw, hh
    x, y = p0
    x0, y0 = p0
    x1, y1 = p1
    dx = abs(x1 - x)
    sx = 1 if x < x1 else -1
    dy = -abs(y1 - y)
    sy = 1 if y < y1 else -1
    err = dx+dy
    bw = brush.size[0] if brush else 1
    bh = brush.size[1] if brush else 1
    hw = bw // 2
    hh = bh // 2
    w, h = pic.size

    cdef int i = 0

    # A slightly undocumented way of accessing the raw data in a PIL image
    # cdef int ptr_val = image.unsafe_ptrs['image32']
    # cdef int** img = <int**>ptr_val

    cdef (int, int) position
    cdef int e2

    # cdef int r, g, b, a
    # r,g,b,a = color
    # cdef int col = r + 2**24*a  # turning the color into a 32 bit integer
    cdef int xx, yy

    color = _rgb_to_32bit((color, 0, 0))

    with nogil:
        while True:
            if i % step == 0:
                if brush is not None:
                    # brush_image = brush.pic
                    position = (x-hw, y-hh)
                    pic.paste(brush, x-hw, y-hh, True)  # TODO: Slow!
                else:
                    xx = x - hw
                    yy = y - hh
                    if xx >= 0 and xx < w and yy >= 0 and yy < h:
                        pic.set_pixel(xx, yy, color)
                        i += 1
            if x == x1 and y == y1:
                break
            e2 = 2*err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    return Rectangle((min(x0, x1) - hw, min(y0, y1) - hh),
                     (dx + bw, -dy + bh)).intersect(pic.rect)
    # if rect is not None and set_dirty:
    #     layer.dirty = rect.unite(layer.dirty)
    # return rect


cpdef draw_rectangle(LongPicture pic, (int, int) pos, (int, int) size, brush=None, unsigned int color=0,
                          bint fill=False, int step=1):

    cdef int x0, y0, w0, h0, x, y, w, h, cols, rows, bw, bh, hw, hh
    x0, y0 = pos
    w0, h0 = size

    # ensure that the rectangle stays within the image borders
    x = max(0, x0)
    y = max(0, y0)
    w = w0 - (x - x0)
    h = h0 - (y - y0)

    cols, rows = pic.size
    w = min(cols - x, w)
    h = min(rows - y, h)

    if fill:
        for i in range(y, min(y+h, rows)):
            # TODO fixme
            draw_line(pic, (x0, i), (x0+w, i), None, color, step)
    else:
        draw_line(pic, pos, (x0+w0, y0), brush, color, step)
        draw_line(pic, (x0+w0, y0), (x0+w0, y0+h0), brush, color, step)
        draw_line(pic, (x0+w0, y0+h0), (x0, y0+h0), brush, color, step)
        draw_line(pic, (x0, y0+h0), pos, brush, color, step)

    bw = brush.width if brush else 0
    bh = brush.height if brush else 0
    hw = bw // 2 if brush else 1
    hh = bh // 2 if brush else 1

    return pic.rect.intersect(Rectangle((x-hw, y-hh), (w + bw, h + bh)))
    # layer.dirty = rect.unite(layer.dirty)
    # return rect


# cdef horizontal_line(int** image, int y, int xmin, int xmax, int color):
#     cdef int x
#     for x in range(xmin, xmax):
#         image[y][x] = color


# def vertical_line(image, x, ymin, ymax, color):
#     cols, rows = image.size
#     if 0 <= x <= cols:
#         ymin = max(0, ymin)
#         ymax = min(rows, ymax)
#         col = array("B", color * (ymax - ymin))
#         print ymax-ymin
#         image.data[4*(ymin*cols+x):4*(ymax*cols+x):4*cols] = col


cpdef draw_ellipse(LongPicture pic, (int, int) center, (int, int) size, brush=None,
                   unsigned int color=0, bint fill=False):

    # TODO this does not handle small radii (<5) well

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
    bw = brush.width if brush else 0
    bh = brush.height if brush else 0
    hw = bw//2 if brush else 1
    hh = bh//2 if brush else 1

    w, h = pic.size

    if not (0 <= x0 < w) or not (0 <= y0 < h):
        # TODO This should be allowed, but right now would crash
        return None

    # cdef int cr, cg, cb, ca
    # cr,cg,cb,ca = color
    # cdef int col = cr + 16777216*ca  # turning the color into a 32 bit integer
    cdef int xx, yy
    cdef int topy, boty, lx, rx

    if b == 0:
        if fill:
            lx = min(w-1, max(0, x0 - a))
            rx = max(0, min(w, x0 + a + 1))
            draw_line(pic, (lx, y0), (rx, y0), color)
            rect = Rectangle((x0-a, y0), (2*a+1, 1))
            # image.dirty = rect
        else:
            rect = draw_line(pic, (x0-a, y0), (x0+a+1, y0), brush, color)
        return pic.rect.intersect(rect)
        # layer.dirty = rect.unite(layer.dirty)
        # return rect

    if a == 0:
        if fill and color:
            rect = draw_rectangle(pic, (x0, y0-b), (1, 2*b+1), color=color, fill=True)
        else:
            rect = draw_line(pic, (x0, y0-b), (x0, y0+b+1), brush, color)
        return pic.rect.intersect(rect)
        # layer.dirty = rect.unite(layer.dirty)
        # return rect

    while stopy <= stopx:
        topy = y0 - y
        boty = y0 + y
        if fill:
            lx = min(w-1, max(0, x0 - x))
            rx = max(0, min(w, x0 + x + 1))
            if topy >= 0:
                draw_line(pic, (lx, topy), (rx, topy), None, color)
            if boty < h:
                draw_line(pic, (lx, boty), (rx, boty), None, color)
        else:
            xx = x0 + x
            yy = y0 + y
            if xx >= 0 and xx < w and yy >= 0 and yy < h:
                pic.paste(brush, xx - hw, yy - hh, True)
            xx = x0 - x
            yy = y0 + y
            if xx >= 0 and xx < w and yy >= 0 and yy < h:
                pic.paste(brush, xx - hw, yy - hh, True)
            xx = x0 - x
            yy = y0 - y
            if xx >= 0 and xx < w and yy >= 0 and yy < h:
                pic.paste(brush, xx - hw, yy - hh, True)
            xx = x0 + x
            yy = y0 - y
            if xx >= 0 and xx < w and yy >= 0 and yy < h:
                pic.paste(brush, xx - hw, yy - hh, True)
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
                draw_line(pic, (lx, topy), (rx, topy), None, color)
            if boty < h:
                draw_line(pic, (lx, boty), (rx, boty), None, color)
        else:
            xx = x0 + x
            yy = y0 + y
            if xx >= 0 and xx < w and yy >= 0 and yy < h:
                pic.paste(brush, xx - hw, yy - hh, True)
            xx = x0 - x
            yy = y0 + y
            if xx >= 0 and xx < w and yy >= 0 and yy < h:
                pic.paste(brush, xx - hw, yy - hh, True)
            xx = x0 - x
            yy = y0 - y
            if xx >= 0 and xx < w and yy >= 0 and yy < h:
                pic.paste(brush, xx - hw, yy - hh, True)
            xx = x0 + x
            yy = y0 - y
            if xx >= 0 and xx < w and yy >= 0 and yy < h:
                pic.paste(brush, xx - hw, yy - hh, True)

        y += 1
        error -= a2 * (y - 1)
        stopx += a2
        if error < 0:
            error += b2 * (x - 1)
            x -= 1
            stopy -= b2

    return pic.rect.intersect(Rectangle((x0-a-hw-1, y0-b-hh-1), (2*a+bw+2, 2*b+bh+2)))


cpdef draw_fill(LongPicture pic, (int, int) point, unsigned int color):

    # TODO kind of slow, and requires the GIL.

    cdef int startx, starty, w, h
    startx, starty = point
    cdef list stack = [point]  # TODO maybe find some more C friendly way of keeping a stack
    w, h = pic.size
    cdef unsigned int start_col = pic[startx, starty] & 0xFF

    if start_col == color:
        return

    cdef int x, y, xmin, xmax, ymin, ymax, xstart
    cdef bint reach_top, reach_bottom
    xmin, xmax = w, 0
    ymin, ymax = h, 0

    while stack:
        x, y = stack.pop()
        # search left
        while x >= 0 and start_col == pic[x, y]:
            x -= 1
        x += 1
        reach_top = reach_bottom = False

        # search right
        while x < w and pic[x, y] == start_col:
            pic[x, y] = color  # color this pixel
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
