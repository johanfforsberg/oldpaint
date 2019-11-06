from collections import deque

from .picture import LongPicture
from .rect import Rectangle


def make_stroke(overlay, event_queue, brush=LongPicture(size=(1, 1))):

    points = deque()
    brush.clear((0, 0, *brush.size), 6 + 255*2**24)
    total_rect = Rectangle()

    while True:
        event_type, args = event_queue.get()
        if event_type == "mouse_up":
            break
        elif event_type == "mouse_drag":
            pos, button, modifiers = args
            if not points:
                rect = overlay.draw_line(pos, pos, brush=brush)
            else:
                prev_pos = points[-1]
                rect = overlay.draw_line(prev_pos, pos, brush=brush)
            total_rect = total_rect.unite(rect)
            points.append(pos)

    return points, total_rect
