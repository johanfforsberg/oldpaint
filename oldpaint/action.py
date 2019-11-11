import abc
#from queue import SimpleQueue, Empty

from pyglet import window

#from .picture import rgba_to_32bit
from .rect import from_points, cover
#from .util import LoggerMixin
from .util import try_except_log


class Action(metaclass=abc.ABCMeta):

    """
    A "stroke" is whatever happens between pressing a mouse button
    and releasing it, with a drawing tool.
    """

    tool = None  # Name of the tool (should correspond to an icon)
    ephemeral = False  # Ephemeral means clear the layer before each draw call

    def __init__(self, brush, color, initial):
        self.brush = brush
        self.color = color
        self.points = [initial]  # Stores the coordinates used when drawing, e.g. for repeating
        self.rect = None         # The dirty rectangle covering the edit

    def draw(self, layer, point, buttons, modifiers):
        "Runs once per mouse move event, *on a separate thread*. Be careful!"

    def finish(self, layer, point, buttons, modifiers):
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

    def __repr__(self):
        return self.tool


class Stroke:
    pass


class PencilTool(Stroke, Action):

    tool = "pencil"
    ephemeral = False

    def draw(self, layer, point, buttons, modifiers):
        p0 = tuple(self.points[-1][:2])
        p1 = point
        self.points.append(point)
        rect = layer.draw_line(p0, p1, brush=self.brush.get_pic(self.color))
        if rect:
            self.rect = rect.unite(self.rect)

    def finish(self, layer, point, buttons, modifiers):
        self.draw(layer, point, buttons, modifiers)


class PointsTool(Stroke, Action):

    tool = "points"
    ephemeral = False

    def draw(self, layer, point, buttons, modifiers):
        self.points.append(point)
        if len(self.points) % 5 == 0:
            rect = layer.draw_line(point, point, brush=self.brush.get_pic(self.color))
            if rect:
                self.rect = rect.unite(self.rect)

    def finish(self, layer, point, buttons, modifiers):
        self.draw(layer, point, buttons, modifiers)


class LineTool(Stroke, Action):

    tool = "line"
    ephemeral = True

    def draw(self, layer, point, buttons, modifiers):
        p0 = tuple(self.points[0][:2])
        p1 = point
        self.rect = layer.draw_line(p0, p1, brush=self.brush.get_pic(self.color))


class RectangleTool(Stroke, Action):

    tool = "rectangle"
    ephemeral = True

    def draw(self, layer, point, buttons, modifiers):
        p0 = self.points[0]
        r = from_points([p0, point])
        self.rect = layer.draw_rectangle(r.position, r.size, brush=self.brush.get_pic(self.color),
                                         fill=modifiers & window.key.MOD_SHIFT)


class EllipseTool(Stroke, Action):

    tool = "ellipse"
    ephemeral = True

    @try_except_log
    def draw(self, layer, point, buttons, modifiers):
        x0, y0 = self.points[0]
        x, y = point
        size = (int(abs(x - x0)), int(abs(y - y0)))
        self.rect = layer.draw_ellipse((x0, y0), size, brush=self.brush.get_pic(self.color),
                                       color=self.color + 255*2**24,
                                       fill=True)


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
