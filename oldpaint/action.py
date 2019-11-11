import abc
#from queue import SimpleQueue, Empty

#from .picture import rgba_to_32bit
from .rect import from_points, cover
#from .util import LoggerMixin
from .util import try_except_log


class Action(metaclass=abc.ABCMeta):

    """
    A "stroke" is whatever happens between pressing a mouse button
    and releasing it, with a drawing tool.
    """

    tool = None  # Name of the associated tool (e.g. icon)
    ephemeral = False  # Ephemeral means redraw the whole thing each time the mouse moves.

    def __init__(self, overlay, brush, color, initial):

        self.overlay = overlay
        self.brush = brush
        self.color = color
        self.points = [initial]  # Stores the coordinates used when drawing, e.g. for repeating
        self.rect = None         # The dirty rectangle covering the edit

    def draw(self, point, buttons, modifiers):
        "Runs once per mouse move event, *on a separate thread*. Be careful!"

    def finish(self, point, buttons, modifiers):
        "Runs once at the end, on main thread."

    # def redraw(self, cls):
    #     points = self.points[1:]
    #     initial = self.points[0]
    #     stroke = cls(self.image, self.overlay, self.window, initial)
    #     if not stroke.ephemeral:
    #         for point in points:
    #             stroke.on_mouse_drag_imgcoord(*point)
    #     else:
    #         stroke.on_mouse_drag_imgcoord(*points[-1])
    #     stroke.on_mouse_release_imgcoord(*points[-1], pop_handler=False)

    # def undo(self):
    #     backup = self.image.get_subimage(self.rect)
    #     self.image.blit(self.backup, rect=self.rect, mask=False)
    #     self.backup = backup

    def __repr__(self):
        return self.tool


class Stroke:
    pass


class Pencil(Stroke, Action):

    tool = "pencil"
    ephemeral = False

    def draw(self, point, buttons, modifiers):
        p0 = tuple(self.points[-1][:2])
        p1 = point
        self.points.append(point)
        rect = self.overlay.draw_line(p0, p1, brush=self.brush.get_pic(self.color))
        if rect:
            self.rect = rect.unite(self.rect)

    def finish(self, point, buttons, modifiers):
        self.draw(point, buttons, modifiers)


class PointsStroke(Stroke, Action):

    tool = "points"
    ephemeral = False

    def draw(self, x, y, buttons, modifiers):
        p1 = (x, y)
        if len(self.points) % 2 == 1:
            index = self.palette.get_index(buttons)
            rect = self.overlay.draw_line(p1, p1, color=rgba_to_32bit(index, 0, 0, 255), brush=self.brush.pic)
            if rect:
                self.rect = rect.unite(self.rect)
        return True

    def finish(self, x, y, buttons, modifiers):
        p1 = x, y
        index = self.palette.get_index(buttons)
        rect = self.overlay.draw_line(p1, p1, color=rgba_to_32bit(index, 0, 0, 255), brush=self.brush.pic)
        self.rect = rect.unite(self.rect)


class Line(Stroke, Action):

    tool = "line"
    ephemeral = True

    def draw(self, point, buttons, modifiers):
        rect1 = self.overlay.clear(self.rect, set_dirty=False)
        p0 = tuple(self.points[0][:2])
        p1 = point
        rect2 = self.overlay.draw_line(p0, p1, brush=self.brush.get_pic(self.color), set_dirty=False)
        self.rect = rect2
        self.overlay.dirty = cover([rect1, rect2])

    # def finish(self, x, y, buttons, modifiers):
    #     self.draw(x, y, buttons, modifiers)


class RectangleTool(Stroke, Action):

    tool = "rectangle"
    ephemeral = True

    def draw(self, point, buttons, modifiers):
        rect1 = self.rect
        self.overlay.clear(self.rect, set_dirty=False)
        p0 = self.points[0]
        r = from_points([p0, point])
        rect2 = self.overlay.draw_rectangle(r.position, r.size, brush=self.brush.get_pic(self.color))
                                            #fill=modifiers & window.key.MOD_SHIFT)
        self.rect = rect2
        self.overlay.dirty = cover([rect1, rect2])


class EllipseTool(Stroke, Action):

    tool = "ellipse"
    ephemeral = True

    @try_except_log
    def draw(self, point, buttons, modifiers):
        rect1 = self.rect
        self.overlay.clear(self.rect, set_dirty=False)
        x0, y0 = self.points[0]
        x, y = point
        size = (int(abs(x - x0)), int(abs(y - y0)))
        print(size)
        self.rect = self.overlay.draw_ellipse((x0, y0), size, brush=self.brush.get_pic(self.color),
                                              color=self.color + 255*2**24,
                                              fill=False)
        print(self.rect)
        self.overlay.dirty = cover([rect1, self.rect])


class FillStroke(Stroke, Action):

    tool = "floodfill"

    def finish(self, x, y, buttons, modifiers):
        # TODO clean up
        data = self.image.data.getdata()
        rgba_data = [0, 0, 0, 0] * len(data)
        rgba_data[0::4] = data
        rgba_data[3::4] = (255 if x else 0 for x in data)
        self.overlay.blit(Image.frombuffer("RGBA", self.image.size, bytearray(rgba_data))
                          .transpose(Image.FLIP_TOP_BOTTOM), rect=self.overlay.rect)
        index = self.palette.get_index(buttons)
        self.rect = self.image.draw_fill(self.overlay, self.overlay, (x, y), color=rgba_to_32bit(index, 0, 0, 255))
        return True


class Selection(Action):

    tool = "brush"
    stroke = False

    def __init__(self, stack, brush, initial):
        super().__init__(stack, brush, initial)
        self.start = tuple(initial[:2])

    def draw(self, x, y, buttons, modifiers):
        self.rect = from_points([self.start, (x, y)])
        self.stack.selection = self.rect

    def finish(self, x, y, buttons, modifiers):
        self.stack.make_brush()
        self.stack.selection = None


class Picker(Action):

    tool = "picker"
    stroke = False

    def __init__(self, stack, brush, initial):
        super().__init__(stack, brush, initial)
        self.start = tuple(initial[:2])
        self.color = None

    def finish(self, x, y, buttons, modifiers):
        index = self.stack.current.pixel[x, y]
        if buttons == window.mouse.LEFT:
            self.stack.palette.foreground = index
        elif buttons == window.mouse.RIGHT:
            self.stack.palette.background = index
