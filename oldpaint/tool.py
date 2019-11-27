import abc
from random import gauss

from pyglet import window

from .rect import from_points, cover
from .util import try_except_log


class Tool(metaclass=abc.ABCMeta):

    """
    Tools are various ways of mouse interaction.
    They can draw to the image, but also inspect it or change other aspects.
    """

    tool = None  # Name of the tool (should correspond to an icon)
    ephemeral = False  # Ephemeral means we'll clear the layer before each draw call
    brush_preview = True  # Whether to show the current brush on top of the image while not drawing
    period = None

    def __init__(self, drawing, brush, color, initial):
        self.drawing = drawing
        self.brush = brush
        self.color = color
        self.points = []  # Store the coordinates used when drawing
        self.rect = None         # The smallest rectangle covering the edit

    # The following methods are optional, but without any of them, the tool won't
    # actually *do* anything.
    # They all run on a thread separate from the main UI thread. Make sure
    # to not do anything to the drawing without acquiring the proper locks.

    def start(self, layer, point, buttons, modifiers):
        "Run once at the beginning of the stroke."
        self.points.append(point)
    
    def draw(self, layer, point, buttons, modifiers):
        "Runs once per mouse move event."
        # layer: overlay layer (that can safely be drawn to),
        # point: the latest mouse coord,
        # buttons: mouse buttons currently held
        # modifiers: keyboard modifiers held

    def finish(self, layer, point, buttons, modifiers):
        "Runs once right before the stroke is finished."

    def __repr__(self):
        "If this returns a non-empty string it will be displayed while the tool is used."
        return ""


class PencilTool(Tool):

    "One continuous line along the mouse movement"

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


class PointsTool(Tool):

    "A series of dots along the mouse movement."

    tool = "points"
    ephemeral = False
    step = 5

    def draw(self, layer, point, buttons, modifiers):
        if self.points[-1] == point:
            return
        self.points.append(point)
        if len(self.points) % self.step == 0:
            rect = layer.draw_line(point, point, brush=self.brush.get_pic(self.color))
            if rect:
                self.rect = rect.unite(self.rect)

    def finish(self, layer, point, buttons, modifiers):
        # Make sure we draw a point even if the mouse was never moved
        rect = layer.draw_line(point, point, brush=self.brush.get_pic(self.color))
        if rect:
            self.rect = rect.unite(self.rect)


class SprayTool(Tool):

    tool = "spray"
    ephemeral = False
    size = 10
    intensity = 1.0
    period = 0.002

    def start(self, layer, point, buttons, modifiers):
        super().start(layer, point, buttons, modifiers)
        self.draw(layer, point, buttons, modifiers)

    def draw(self, layer, point, buttons, modifiers):
        self.points.append(point)
        x, y = point
        xg = gauss(x, self.size)
        yg = gauss(y, self.size)
        p = (xg, yg)
        rect = layer.draw_line(p, p, brush=self.brush.get_pic(self.color))
        if rect:
            self.rect = rect.unite(self.rect)


class LineTool(Tool):

    "A straight line from the starting point to the end point."

    tool = "line"
    ephemeral = True

    def draw(self, layer, point, buttons, modifiers):
        p0 = tuple(self.points[0][:2])
        p1 = point
        self.rect = layer.draw_line(p0, p1, brush=self.brush.get_pic(self.color))
        self.points.append(p1)

    def finish(self, layer, point, buttons, modifiers):
        rect = layer.draw_line(point, point, brush=self.brush.get_pic(self.color))
        if rect:
            self.rect = rect.unite(self.rect)

    def __repr__(self):
        x0, y0 = self.points[0]
        x1, y1 = self.points[-1]
        return f"{x1-x0}, {y1-y0}"


class RectangleTool(Tool):

    "A rectangle with opposing corners at the start and end points."

    tool = "rectangle"
    ephemeral = True

    def draw(self, layer, point, buttons, modifiers):
        p0 = self.points[0]
        r = from_points([p0, point])
        self.rect = layer.draw_rectangle(r.position, r.size, brush=self.brush.get_pic(self.color),
                                         fill=modifiers & window.key.MOD_SHIFT)
        self.points.append(point)

    def __repr__(self):
        x0, y0 = self.points[0]
        x1, y1 = self.points[-1]
        return f"{abs(x1 - x0) + 1}, {abs(y1 - y0) + 1}"


class EllipseTool(Tool):

    "An ellipse centered at the start point and with radii described by the end point."

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
        self.points.append(point)

    def __repr__(self):
        x0, y0 = self.points[0]
        x1, y1 = self.points[-1]
        return f"{abs(x1-x0)}, {abs(y1-y0)}"


class FillTool(Tool):

    "Fill all adjacent pixels of the same color as the start point."

    tool = "floodfill"
    brush_preview = False

    def finish(self, layer, point, buttons, modifiers):
        if point in layer.rect:
            clone = self.drawing.current.clone()
            rect = clone.draw_fill(point, color=self.color + 255*2**24)
            if rect:
                # Here we don't use the overlay, and therefore handle the updating directly
                self.drawing.change_layer(clone, rect)


class SelectionTool(Tool):

    "Create a brush from a rectangular region of the current layer."

    tool = "brush"
    brush_preview = False

    def draw(self, layer, point, buttons, modifiers):
        rect = from_points([self.points[0], point])
        self.drawing.selection = rect

    def finish(self, layer, point, buttons, modifiers):
        self.drawing.make_brush(clear=buttons & window.mouse.RIGHT)
        self.drawing.selection = None

    def __repr__(self):
        rect = self.drawing.selection
        if rect:
            return f"{rect.width}, {rect.height}"
        return ""


class PickerTool(Tool):

    "Set the current color to the one under the mouse when clicked."

    tool = "picker"
    brush_preview = False

    def __init__(self, drawing, brush, color, initial):
        super().__init__(drawing, brush, color, initial)
        self.color = None

    def finish(self, layer, point, buttons, modifiers):
        index = self.drawing.current.pic.get_pixel(*point)
        if buttons == window.mouse.LEFT:
            self.drawing.palette.foreground = index
        elif buttons == window.mouse.RIGHT:
            self.drawing.palette.background = index
