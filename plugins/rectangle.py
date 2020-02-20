"""
Example plugin.

Plugins can be as simple as this; a function that takes a few standard arguments
and any number of custom parameters. Oldpaint will render a GUI to allow configuration
of the parameters, and running the plugin. It can do whatever you want. But it's
probably best to not reach too far into the internals; stick with the helper "draw_*"
methods on Drawing, and you should be safe! Otherwise it's probably very easy to mess
up the program state, in particular regarding undo, or even cause crashes.
You've been warned.

The "oldpaint" argument provides the whole package namespace, since you can't import
it here. "drawing" and "brush" are the current active ones.

For now only int, float, str and bool parameters are allowed. You must give default
values for them.

Put your own custom plugins go in XDG_CONFIG_HOME/oldpaint/plugins, as .py files,
and oldpaint will find them.
"""

def plugin(oldpaint, drawing, brush,  # These args are mandatory even if you don't need them
           extra_width: int=0, fill: bool=False):  # Any number of parameter arguments.
    """
    This simple script plugin draws a rectangle around the current selection.
    Uses the current brush and color. Also has some options.
    """
    rect = drawing.selections.current
    if rect:
        w, h = rect.size
        rect = oldpaint.rect.Rectangle(position=rect.position, size=(w+extra_width, h))
        color = drawing.palette.foreground
        drawing.draw_rectangle(rect, brush, color, fill=fill)
