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

Optionally, you can return a dict containing new values for any of the parameters.

Put your own custom plugins go in XDG_CONFIG_HOME/oldpaint/plugins, as .py files,
and oldpaint will find them.
"""

def plugin(oldpaint, drawing, brush,  # These args are mandatory even if you don't need them
           offset: int=5, extra_width: int=0, fill: bool=False):  # Any number of parameter arguments.
    """
    This simple script plugin draws two symmetric rectangles based on the current selection.
    Uses the current brush and color. Also has some options.
    """
    rect = drawing.selection
    if rect:
        x, y = rect.position
        w, h = rect.size
        size = (w+extra_width, h)
        color = drawing.palette.foreground

        # Using the edit contextmanager like this means that all our changes will be stored
        # as one single undo, which is usually convenient.
        with drawing.edit() as edit:
            for o in range(offset):
                position = (x + o, y + o)
                edit.draw_rectangle(position, size, brush, color, fill=fill)
            edit.flip_layer_horizontal()
            for o in range(offset):
                position = (x + o, y + o)
                edit.draw_rectangle(position, size, brush, color, fill=fill)
            edit.flip_layer_horizontal()

        return dict(extra_width=extra_width + 10)
