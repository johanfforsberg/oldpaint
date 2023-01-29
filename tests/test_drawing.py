from oldpaint.drawing import Drawing
from oldpaint.tool import PencilTool
from oldpaint.brush import RectangleBrush
from oldpaint.rect import Rectangle


def test_drawing():
    d = Drawing((20, 10))
    print(d.current.get_data(0))
    b = RectangleBrush(1, 1)
    print(d.palette.colors)
    data = b.get_draw_data(10)
    # d.overlay.draw_polygon( (0.1, 1), (1.8, 8), (9, 1), (9, 8), 2)
    d.draw_polygon((1, 0.9), (1, 1.1), (9, 7.1), (9, 0.9), 2)
    # print(d.overlay.get_data())
    d.change_layer(d.overlay, Rectangle((0, 0), (20, 10)), PencilTool)
    print(d.current.get_data())
    d.save_png("/tmp/test_drawing.png")
