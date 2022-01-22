import abc
from functools import lru_cache
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

    def start(self, layer, point, buttons, modifiers):
        "Run once at the beginning of the stroke."
        self.points.append(point)

    def draw(self, layer, point, buttons, modifiers, pressure):
        "Runs once per mouse move event."
        # layer: layer layer (that can safely be drawn to),
        # point: the latest mouse coord,
        # buttons: mouse buttons currently held
        # modifiers: keyboard modifiers held

    def finish(self, layer, point, buttons, modifiers):
        "Runs once right before the stroke is finished."

    @classmethod
    def get_config_params(cls):
        members = cls.__dict__.items()
        config_params = [m for m in members
                         if not hasattr(Tool, m[0])
                         and not callable(m[1])
                         and not m[0].startswith("_")]
        return [(name, cls.__annotations__[name], value)
                for name, value in config_params]

    def __repr__(self):
        "If this returns a non-empty string it will be displayed while the tool is used."
        return ""


class PencilTool(Tool):

    "One continuous line along the mouse movement"

    tool = ToolName.pencil

    def draw(self, layer, point, buttons, modifiers, pressure):
        if self.points[-1] == point:
            return
        p0 = tuple(self.points[-1])
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        rect = layer.draw_line(p0, point, brush, self.drawing.frame,
                               offset=self.brush.center)
        if rect:
            self.rect = rect.unite(self.rect)
        self.points.append(point)

    def finish(self, layer, point, buttons, modifiers):
        # Make sure we draw a point even if the mouse was never moved
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        rect = layer.draw_line(self.points[-1], point, brush, self.drawing.frame,
                               offset=self.brush.center)
        if rect:
            self.rect = rect.unite(self.rect)


class InkTool(Tool):

    tool = ToolName.ink

    def start(self, layer, point, buttons, modifiers):
        "Run once at the beginning of the stroke."
        self.points.append(point)
        self._last_width = None
        self._last_p = None
        # TODO these should be settings somehow
        self._max_width = 5  # Actually half the max width
        self._min_width = 0.5
        self._pressure_exponent = 2

    def draw(self, layer, point, buttons, modifiers, pressure):
        if self.points[-1] == point:
            return
        x0, y0 = tuple(self.points[-1])
        x1, y1 = point
        dx = x1 - x0
        dy = y1 - y0
        d = (dx**2 + dy**2)**0.5
        dxn = dx / d
        dyn = dy / d
        w0 = self._last_width or self._min_width
        # We put some minimum width here, to prevent subpixel lines which looks
        # kind of broken. Maybe that's desirable in some cases?
        w1 = max(self._min_width, pressure**self._pressure_exponent * self._max_width)
        self._last_width = w1
        if self._last_p:
            # We cheat here by using the last end point as new starting point
            # This will make the connections look weird if there are very fast
            # turns with high pressure. But so far I have not seen any problem
            # in practice. We'll see.
            p1, p0 = self._last_p
        else:
            p0 = (x0 - dyn * w0, y0 + dxn * w0)
            p1 = (x0 + dyn * w0, y0 - dxn * w0)
        p2 = (x1 + dyn * w1, y1 - dxn * w1)
        p3 = (x1 - dyn * w1, y1 + dxn * w1)
        self._last_p = p2, p3
        rect = layer.draw_quad(p0, p1, p2, p3, self.brush_color, self.drawing.frame)
        if rect:
            self.rect = rect.unite(self.rect)
        self.points.append(point)


class PointsTool(Tool):

    "A series of spaced points along the mouse movement."

    # TODO not very accurate, as it depends a lot on how fast the mouse
    # moves and the rate of events.

    tool = ToolName.points
    ephemeral = False

    # Config
    step: (int, slice(1, 100)) = 5  # More line a minimum step

    def draw(self, layer, point, buttons, modifiers, pressure):
        if self.points[-1] == point:
            return
        self.points.append(point)
        if len(self.points) % self.step == 0:
            brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
            rect = layer.draw_line(point, point, brush, self.drawing.frame,
                                   offset=self.brush.center)
            if rect:
                self.rect = rect.unite(self.rect)

    def finish(self, layer, point, buttons, modifiers):
        # Make sure we draw a point if the mouse was never moved
        if len(self.points) == 1:
            brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
            rect = layer.draw_line(point, point, brush, self.drawing.frame,
                                   offset=self.brush.center)
            if rect:
                self.rect = rect.unite(self.rect)


class SprayTool(Tool):

    tool = ToolName.spray
    ephemeral = False
    period = 0.001

    size: (int, slice(1, 100)) = 10
    intensity: (float, slice(0, 1)) = 1.0

    @lru_cache(1)
    def _get_n_skip(self, intensity):
        return int((1/intensity) ** 2)

    def start(self, layer, point, buttons, modifiers):
        super().start(layer, point, buttons, modifiers)
        self.draw(layer, point, buttons, modifiers, 0)

    def draw(self, layer, point, buttons, modifiers, pressure):
        self.points.append(point)
        if len(self.points) % self._get_n_skip(self.intensity) == 0:
            for _ in range(int(pressure * 10)):
                # TODO draws one point at a time, really slow.
                x, y = point
                xg = gauss(x, self.size)
                yg = gauss(y, self.size)
                p = (xg, yg)
                brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
                rect = layer.draw_line(p, p, brush, self.drawing.frame,
                                       offset=self.brush.center)
                if rect:
                    self.rect = rect.unite(self.rect)


class LineTool(Tool):

    "A straight line from the starting point to the end point."

    tool = ToolName.line
    ephemeral = True

    step: (int, slice(1, 100)) = 1

    def start(self, layer, point, buttons, modifiers):
        super().start(layer, point, buttons, modifiers)
        self.points.append(None)

    def draw(self, layer, point, buttons, modifiers, pressure):
        p0 = tuple(self.points[0][:2])
        self.points[1] = point
        p1 = point
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        self.rect = layer.draw_line(p0, p1, brush, self.drawing.frame,
                                    offset=self.brush.center, step=self.step)

    def finish(self, layer, point, buttons, modifiers):
        if self.points[1] is None:
            brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
            rect = layer.draw_line(point, point, brush, self.drawing.frame,
                                   offset=self.brush.center, step=self.step)
            self.points[1] = point
            if rect:
                self.rect = rect.unite(self.rect)

    def __repr__(self):
        x0, y0 = self.points[0]
        x1, y1 = self.points[-1]
        return f"{abs(x1 - x0) + 1}, {abs(y1 - y0) + 1}"


class RectangleTool(Tool):

    "A rectangle with opposing corners at the start and end points."

    tool = ToolName.rectangle
    ephemeral = True

    def start(self, layer, point, buttons, modifiers):
        super().start(layer, point, buttons, modifiers)
        self.points.append(point)

    def draw(self, layer, point, buttons, modifiers, pressure):
        p0 = self.points[0]
        self.points[1] = point
        r = from_points([p0, point])
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        self.rect = layer.draw_rectangle(r.position, r.size, brush, self.drawing.frame,
                                           offset=self.brush.center,
                                           fill=modifiers & window.key.MOD_SHIFT,
                                           color=self.color)

    def finish(self, layer, point, buttons, modifiers):
        if len(self.points) > 1:
            return
        p0 = self.points[0]
        r = from_points([p0, point])
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        rect = layer.draw_rectangle(r.position, r.size, brush, self.drawing.frame,
                                    offset=self.brush.center,
                                    fill=modifiers & window.key.MOD_SHIFT, color=self.color)
        if rect:
            self.rect = rect.unite(self.rect)
        self.points[1] = point
        
    def __repr__(self):
        x0, y0 = self.points[0]
        x1, y1 = self.points[1]
        return f"{abs(x1 - x0) + 1}, {abs(y1 - y0) + 1}"


class EllipseTool(Tool):

    "An ellipse centered at the start point and with radii described by the end point."

    tool = ToolName.ellipse
    ephemeral = True

    def start(self, layer, point, buttons, modifiers):
        super().start(layer, point, buttons, modifiers)
        self.points.append(point)

    @try_except_log
    def draw(self, layer, point, buttons, modifiers, pressure):
        x0, y0 = self.points[0]
        self.points[1] = point
        x, y = point
        size = (int(abs(x - x0)), int(abs(y - y0)))
        brush = self.brush.get_draw_data(self.brush_color, colorize=buttons & window.mouse.RIGHT)
        self.rect = layer.draw_ellipse((x0, y0), size, brush, self.drawing.frame,
                                       offset=self.brush.center, color=self.color,
                                       fill=modifiers & window.key.MOD_SHIFT)

    def finish(self, layer, point, buttons, modifiers):
        self.points[1] = point

    def __repr__(self):
        x0, y0 = self.points[0]
        x1, y1 = self.points[-1]
        return f"{abs(x1-x0) * 2 + 1}, {abs(y1-y0) * 2 + 1}"


class FillTool(Tool):

    "Fill all adjacent pixels of the same color as the start point."

    tool = ToolName.floodfill
    brush_preview = False

    def finish(self, layer, point, buttons, modifiers):
        if point in layer.rect:
            source = self.drawing.current.get_data(self.drawing.frame)
            self.rect = layer.draw_fill(source, point, self.color, self.drawing.frame)
            self.points = [point]


class SelectionTool(Tool):

    "Set the current selection rectangle."

    tool = ToolName.selection
    brush_preview = False
    show_rect = True
    # restore_last = True

    def start(self, layer, point, buttons, modifiers):
        super().start(layer, point, buttons, modifiers)
    
    def draw(self, layer, point, buttons, modifiers, pressure):
        self.rect = layer.rect.intersect(from_points([self.points[0], point]))

    def finish(self, layer, point, buttons, modifiers):
        # self.drawing.make_brush(self.drawing.frame, self.rect, clear=buttons & window.mouse.RIGHT)
        self.drawing.selection = self.rect
        self.rect = None

    def __repr__(self):
        if self.rect:
            return f"{self.rect.width}, {self.rect.height}"
        return ""


class PickerTool(Tool):

    "Set the current color or layer to the one under the mouse when clicked."

    tool = ToolName.picker
    brush_preview = False

    def __init__(self, drawing, brush, color, initial):
        super().__init__(drawing, brush, color, initial)
        self.color = None

    def _pick(self, layer, point, buttons, modifiers, *args):
        # Find the pixel that is visible at the given point.
        x, y = point
        pos = int(x), int(y)
        layer = self.drawing.get_layer_visible_at_point(pos) or self.drawing.layers[0]

        if modifiers & window.key.MOD_SHIFT:
            # Select the layer
            self.drawing.current = layer
        else:
            # Select the color
            data = layer.get_data(self.drawing.frame)
            color_index = data[pos]
            if buttons == window.mouse.LEFT:
                self.drawing.palette.foreground = color_index
            elif buttons == window.mouse.RIGHT:
                self.drawing.palette.background = color_index

    start = _pick
    draw = _pick
