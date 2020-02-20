def plugin(oldpaint, drawing, brush, foo: int=0, bar: float=10.0, baz: str=""):
    """
    This plugins draws a rectangle around the current selection.
    Uses the current brush and color.
    """
    rect = drawing.selections.current
    if rect:
        color = drawing.palette.foreground
        drawing.draw_rectangle(rect, brush, color)
