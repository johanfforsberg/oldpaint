import abc
from time import time

from pyglet import window

from .rect import from_points, cover
from .util import try_except_log


class Tool(metaclass=abc.ABCMeta):

    """
    Tools are various ways of mouse interaction.
    They can draw to the image, but also inspect it or change other aspects.
    """

    tool = None  # Name of the tool (should correspond to an icon)
    ephemeral = False  # Ephemeral means clear the layer before each draw call

    def __init__(self, stack, brush, color, initial):
        self.stack = stack  # Note: normally don't draw directly to the stack, as that
                            # will bypass the undo system.
        self.brush = brush
        self.color = color
        self.points = [initial]  # Store the coordinates used when drawing, e.g. for repeating
        self.rect = None         # The dirty rectangle covering the edit

    def draw(self, layer, point, buttons, modifiers):
        "Runs once per mouse move event, *on a separate thread*. Be careful!"

    def finish(self, layer, point, buttons, modifiers):
        "Runs once at the end, also on the thread."

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


class PencilTool(Tool):

    tool = "pencil"
    ephemeral = False

    def draw(self, layer, point, buttons, modifiers):
        if self.points[-1] == point:
            return
        p0 = tuple(self.points[-1])
        rect = layer.draw_line(p0, point, brush=self.brush.get_pic(self.color))
        if rect:
            self.rect = rect.unite(self.rect)
        self.points.append(point)

    def finish(self, layer, point, buttons, modifiers):
        # Make sure we draw a point even if the mouse was never moved
        rect = layer.draw_line(self.points[-1], point, brush=self.brush.get_pic(self.color))
        if rect:
            self.rect = rect.unite(self.rect)
        self.stack.update(layer.get_subimage(self.rect), self.rect)
        layer.clear(self.rect)


class PointsTool(Tool):

    tool = "points"
    ephemeral = False

    def draw(self, layer, point, buttons, modifiers):
        if self.points[-1] == point:
            return
        self.points.append(point)
        if len(self.points) % 5 == 0:
            rect = layer.draw_line(point, point, brush=self.brush.get_pic(self.color))
            if rect:
                self.rect = rect.unite(self.rect)

    def finish(self, layer, point, buttons, modifiers):
        # Make sure we draw a point even if the mouse was never moved
        rect = layer.draw_line(point, point, brush=self.brush.get_pic(self.color))
        if rect:
            self.rect = rect.unite(self.rect)
        self.stack.update(layer.get_subimage(self.rect), self.rect)
        layer.clear(self.rect)


class LineTool(Tool):

    tool = "line"
    ephemeral = True

    def draw(self, layer, point, buttons, modifiers):
        p0 = tuple(self.points[0][:2])
        p1 = point
        self.rect = layer.draw_line(p0, p1, brush=self.brush.get_pic(self.color))

    def finish(self, layer, point, buttons, modifiers):
        rect = layer.draw_line(point, point, brush=self.brush.get_pic(self.color))
        if rect:
            self.rect = rect.unite(self.rect)
        self.stack.update(layer.get_subimage(self.rect), self.rect)
        layer.clear(self.rect)


class RectangleTool(Tool):

    tool = "rectangle"
    ephemeral = True

    def draw(self, layer, point, buttons, modifiers):
        p0 = self.points[0]
        r = from_points([p0, point])
        self.rect = layer.draw_rectangle(r.position, r.size, brush=self.brush.get_pic(self.color),
                                         fill=modifiers & window.key.MOD_SHIFT)

    def finish(self, layer, point, buttons, modifiers):
        # rect = layer.draw_line(point, point, brush=self.brush.get_pic(self.color))
        # if rect:
        #     self.rect = rect.unite(self.rect)
        self.stack.update(layer.get_subimage(self.rect), self.rect)
        layer.clear(self.rect)


class EllipseTool(Tool):

    tool = "ellipse"
    ephemeral = True

    @try_except_log
    def draw(self, layer, point, buttons, modifiers):
        x0, y0 = self.points[0]
        x, y = point
        size = (int(abs(x - x0)), int(abs(y - y0)))
        self.rect = layer.draw_ellipse((x0, y0), size, brush=self.brush.get_pic(self.color),
                                       color=self.color + 255*2**24,
                                       fill=modifiers & window.key.MOD_SHIFT)

    def finish(self, layer, point, buttons, modifiers):
        # rect = layer.draw_line(point, point, brush=self.brush.get_pic(self.color))
        # if rect:
        #     self.rect = rect.unite(self.rect)
        self.stack.update(layer.get_subimage(self.rect), self.rect)
        layer.clear(self.rect)


class FillTool(Tool):

    tool = "floodfill"

    def finish(self, layer, point, buttons, modifiers):
        clone = self.stack.current.clone()
        self.rect = clone.draw_fill(point, color=self.color)
        self.stack.update(clone.get_subimage(self.rect), self.rect)


class Selection(Tool):

    tool = "brush"

    def __init__(self, stack, brush, initial):
        super().__init__(stack, brush, initial)
        self.start = tuple(initial[:2])

    def draw(self, x, y, buttons, modifiers):
        self.rect = from_points([self.start, (x, y)])
        self.stack.selection = self.rect

    def finish(self, x, y, buttons, modifiers):
        self.stack.make_brush()
        self.stack.selection = None


class PickerTool(Tool):

    tool = "picker"

    def __init__(self, stack, brush, color, initial):
        super().__init__(stack, brush, color, initial)
        self.start = initial
        self.color = None

    def finish(self, layer, point, buttons, modifiers):
        index = self.stack.current.pic.get_pixel(*point)
        if buttons == window.mouse.LEFT:
            self.stack.palette.foreground = index
        elif buttons == window.mouse.RIGHT:
            self.stack.palette.background = index
