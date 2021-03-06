import abc
from random import gauss

from pyglet import window

from .constants import ToolName
from .drawing import Drawing
from .rect import from_points
from .util import try_except_log


class Tool(metaclass=abc.ABCMeta):

    """
    Tools are various ways of mouse interaction.
    They can draw to the image, but also inspect it or change other aspects.
    """

    tool = None  # Name of the tool (should correspond to an icon)
    ephemeral = False  # Ephemeral means we'll clear the layer before each draw call
    brush_preview = True  # Whether to show the current brush on top of the image while not drawing
    show_rect = False
    period = None
    restore_last = False

    def __init__(self, drawing: Drawing, brush, color, brush_color):
        self.drawing = drawing
        self.brush = brush
        self.color = color        # Color used for fills
        self.brush_color = brush_color  # Color used for drawing the brush, but see start()
        self.points = []          # Store the coordinates used when drawing
        self.rect = None          # The smallest rectangle covering the edit

    # The following methods are optional, but without any of them, the tool won't
    # actually *do* anything.
    # They all run on a thread separate from the main UI thread. Make sure
    # to not do anything to the drawing without acquiring the proper locks.

    def start(self, overlay, point, buttons, modifiers):
        "Run once at the beginning of the stroke."
        self.points.append(point)

    def draw(self, overlay, point, buttons, modifiers):
        "Runs once per mouse move event."
        # layer: overlay layer (that can safely be drawn to),
        # point: the latest mouse coord,
        # buttons: mouse buttons currently held
        # modifiers: keyboard modifiers held

    def finish(self, overlay, point, buttons, modifiers):
        "Runs once right before the stroke is finished."

    def __repr__(self):
        "If this returns a non-empty string it will be displayed while the tool is used."
        return ""


class PencilTool(Tool):

    "One continuous line along the mouse movement"

    tool = ToolName.pencil
    ephemeral = False

    def draw(self, overlay, point, buttons, modifiers):
        if self.points[-1] == point:
            return
        p0 = tuple(self.points[-1])
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        rect = overlay.draw_line(p0, point, brush, self.brush.center)
        if rect:
            self.rect = rect.unite(self.rect)
        self.points.append(point)

    def finish(self, overlay, point, buttons, modifiers):
        # Make sure we draw a point even if the mouse was never moved
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        rect = overlay.draw_line(self.points[-1], point, brush, self.brush.center)
        if rect:
            self.rect = rect.unite(self.rect)


class PointsTool(Tool):

    "A series of dots along the mouse movement."

    tool = ToolName.points
    ephemeral = False
    step = 5

    def draw(self, overlay, point, buttons, modifiers):
        if self.points[-1] == point:
            return
        self.points.append(point)
        if len(self.points) % self.step == 0:
            brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
            rect = overlay.draw_line(point, point, brush, offset=self.brush.center)
            if rect:
                self.rect = rect.unite(self.rect)

    def finish(self, overlay, point, buttons, modifiers):
        # Make sure we draw a point even if the mouse was never moved
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        rect = overlay.draw_line(point, point, brush, offset=self.brush.center)
        if rect:
            self.rect = rect.unite(self.rect)


class SprayTool(Tool):

    tool = ToolName.spray
    ephemeral = False
    size = 10
    intensity = 1.0
    period = 0.002

    def start(self, overlay, point, buttons, modifiers):
        super().start(overlay, point, buttons, modifiers)
        self.draw(overlay, point, buttons, modifiers)

    def draw(self, overlay, point, buttons, modifiers):
        self.points.append(point)
        x, y = point
        xg = gauss(x, self.size)
        yg = gauss(y, self.size)
        p = (xg, yg)
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        rect = overlay.draw_line(p, p, brush=brush, offset=self.brush.center)
        if rect:
            self.rect = rect.unite(self.rect)


class LineTool(Tool):

    "A straight line from the starting point to the end point."

    tool = ToolName.line
    ephemeral = True

    def draw(self, overlay, point, buttons, modifiers):
        p0 = tuple(self.points[0][:2])
        p1 = point
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        self.rect = overlay.draw_line(p0, p1, brush=brush, offset=self.brush.center)

    def finish(self, overlay, point, buttons, modifiers):
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        rect = overlay.draw_line(point, point, brush=brush, offset=self.brush.center)
        if rect:
            self.rect = rect.unite(self.rect)
        self.points.append(point)
            
    def __repr__(self):
        x0, y0 = self.points[0]
        x1, y1 = self.points[-1]
        return f"{abs(x1 - x0) + 1}, {abs(y1 - y0) + 1}"


class RectangleTool(Tool):

    "A rectangle with opposing corners at the start and end points."

    tool = ToolName.rectangle
    ephemeral = True

    def draw(self, overlay, point, buttons, modifiers):
        p0 = self.points[0]
        r = from_points([p0, point])
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        self.rect = overlay.draw_rectangle(r.position, r.size, brush=brush,
                                           offset=self.brush.center, fill=modifiers & window.key.MOD_SHIFT,
                                           color=self.color + 255*2**24)

    def finish(self, overlay, point, buttons, modifiers):
        self.points.append(point)
        
    def __repr__(self):
        x0, y0 = self.points[0]
        x1, y1 = self.points[-1]
        return f"{abs(x1 - x0) + 1}, {abs(y1 - y0) + 1}"


class EllipseTool(Tool):

    "An ellipse centered at the start point and with radii described by the end point."

    tool = ToolName.ellipse
    ephemeral = True

    @try_except_log
    def draw(self, overlay, point, buttons, modifiers):
        x0, y0 = self.points[0]
        x, y = point
        size = (int(abs(x - x0)), int(abs(y - y0)))
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        self.rect = overlay.draw_ellipse((x0, y0), size, brush=brush,
                                         offset=self.brush.center, color=self.color + 255*2**24,
                                         fill=modifiers & window.key.MOD_SHIFT)

    def finish(self, overlay, point, buttons, modifiers):
        self.points.append(point)

    def __repr__(self):
        x0, y0 = self.points[0]
        x1, y1 = self.points[-1]
        return f"{abs(x1-x0)}, {abs(y1-y0)}"


class FillTool(Tool):

    "Fill all adjacent pixels of the same color as the start point."

    tool = ToolName.floodfill
    brush_preview = False

    def finish(self, overlay, point, buttons, modifiers):
        if point in overlay.rect:
            source = self.drawing.current.get_data(self.drawing.frame)
            self.rect = overlay.draw_fill(source, point, color=self.color + 255*2**24)
            self.points = [point]


class SelectionTool(Tool):

    "Set the current selection rectangle."

    tool = ToolName.selection
    brush_preview = False
    show_rect = True
    # restore_last = True

    def start(self, overlay, point, buttons, modifiers):
        super().start(overlay, point, buttons, modifiers)
    
    def draw(self, overlay, point, buttons, modifiers):
        self.rect = overlay.rect.intersect(from_points([self.points[0], point]))

    def finish(self, overlay, point, buttons, modifiers):
        # self.drawing.make_brush(self.drawing.frame, self.rect, clear=buttons & window.mouse.RIGHT)
        self.drawing.selection = self.rect
        self.rect = None

    def __repr__(self):
        if self.rect:
            return f"{self.rect.width}, {self.rect.height}"
        return ""


class PickerTool(Tool):

    "Set the current color to the one under the mouse when clicked."

    tool = ToolName.picker
    brush_preview = False

    def __init__(self, drawing, brush, color, initial):
        super().__init__(drawing, brush, color, initial)
        self.color = None

    def finish(self, overlay, point, buttons, modifiers):
        # Find the pixel that is visible at the given point.
        frame = self.drawing.frame
        for layer in reversed(self.drawing.visible_layers):
            data = layer.get_data(frame)
            index = data[point]
            if index != 0:
                break
        if buttons == window.mouse.LEFT:
            self.drawing.palette.foreground = index
        elif buttons == window.mouse.RIGHT:
            self.drawing.palette.background = index
