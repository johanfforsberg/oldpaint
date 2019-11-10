from collections import deque

from .picture import LongPicture


def make_stroke(layer, event_queue, brush=LongPicture(size=(3, 3)), color=None):

    """
    This function will consume events on the given queue until it receives
    a mouse_up event. It's expected to be running in a thread.

    It returns all the points it received and the smallest rectangle that covers
    all the changes it has made to the layer.
    """

    points = deque()
    total_rect = None
    if color is not None:
        brush.clear((0, 0, *brush.size), color + 255*2**24)

    last_pos = None

    while True:
        event_type, args = event_queue.get()
        if event_type == "mouse_up":
            break
        elif event_type == "mouse_drag":
            pos, button, modifiers = args

            # If the point has not actually moved to another pixel,
            # we don't need to do anything.
            if pos == last_pos:
                continue

            if not points:
                rect = layer.draw_line(pos, pos, brush=brush)
            else:
                prev_pos = points[-1]
                rect = layer.draw_line(prev_pos, pos, brush=brush)

            if rect:
                total_rect = rect.unite(total_rect)
            points.append(pos)
            last_pos = pos

    return points, total_rect
