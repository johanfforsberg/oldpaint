import numpy as np

from oldpaint import layer, brush
from oldpaint.palette import Palette


def test_draw_line():
    l = layer.BackupLayer(size=(100, 100))
    palette = Palette([(0, 0, 0, 0), (255, 255, 255, 255)])
    b = brush.SquareBrush()
    print(b.data)
    l.draw_line((20, 30), (70, 80), b.data, offset=(0, 0))
    l.save_png("/tmp/layer.png", palette, 0)
