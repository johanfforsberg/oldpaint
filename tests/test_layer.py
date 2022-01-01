import numpy as np

from oldpaint import layer, brush


def test_draw_line():
    l = layer.Layer(size=(100, 100))
    b = brush.EllipseBrush()
    l.draw_line((20, 30), (70, 80), b.data, (0, 0))
