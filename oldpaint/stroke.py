from collections import deque

from .rect import Rectangle
from .picture import LongPicture
from .util import try_except_log


@try_except_log
def make_stroke(layer, event_queue, brush, color=None):

    """
    This function will consume events on the given queue until it receives
    a mouse_up event. It's expected to be running in a thread.

    It returns all the points it received and the smallest rectangle that covers
    all the changes it has made to the layer.
    """

    points = deque()
    total_rect = None
    # if color is not None:
    #     brush.clear((0, 0, *brush.size), color + 255*2**24)

    last_pos = None

    if layer.dirty:
        layer.clear(layer.dirty)

    while True:
        event_type, args = event_queue.get()

        if event_type == "mouse_drag":
            pos, button, modifiers = args

            # If the point has not actually moved to another pixel,
            # we don't need to do anything.
            if pos == last_pos:
                continue

            if not points:
                prev_pos = pos
            else:
                prev_pos = points[-1]
            brush_pic = brush.get_pic(color)
            rect = layer.draw_line(prev_pos, pos, brush=brush_pic)

            if rect:
                total_rect = rect.unite(total_rect)
            points.append(pos)
            last_pos = pos

        elif event_type == "mouse_up":
            if not points:
                # Looks like the user just clicked w/o moving the mouse.
                # Let's just draw the brush once.
                pos, button, modifiers = args
                x, y = pos
                cx, cy = brush.center
                rect = Rectangle((x - cx, y - cy), brush.size)
                brush_pic = brush.get_pic(color)
                layer.blit(brush_pic, rect)
                total_rect = rect.unite(total_rect)
            break


    return points, total_rect
