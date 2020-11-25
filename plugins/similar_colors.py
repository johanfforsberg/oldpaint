"""
This plugin displays a grid of colors similar to the one currently selected as foreground. It
can be a useful way to navigate the palette.
"""

from functools import lru_cache
from queue import PriorityQueue


def hsv(r, g, b):
    r /= 256
    g /= 256
    b /= 256
    V = xmax = max(r, g, b)
    xmin = min(r, g, b)
    C = xmax - xmin
    L = V - C/2
    S = 0 if V == 0 else C / V
    if C == 0:
        H = 0
    elif V == r:
        H = 60 * (g - b) / C
    elif V == g:
        H = 60 * (2 + (b - r) / C)
    elif V == b:
        H = 60 * (4 + (r - g) / C)
    return H, S, V


def yuv(r, g, b):
    """
    YUV is supposed to be an alternative to RGB where the eye's sensitivity to different components
    are taken into account.

    |  Y' |      |  0.299    0.587    0.114   | | R |
    |  U  |  =   | -0.14713 -0.28886  0.436   | | G |
    |  V  |      |  0.615   -0.51499 -0.10001 | | B |

    """
    return (0.299 * r + 0.587 * g + 0.114 * b,
            -0.14713 * r + -0.28886 * g + 0.436 * b,
            0.615 * r + -0.51499 * g + -0.10001 * b)


def color_distance(color1, color2):
    r1, g1, b1, _ = color1
    r2, g2, b2, _ = color2
    h1, s1, v1 = yuv(r1, g1, b1)
    h2, s2, v2 = yuv(r2, g2, b2)
    dist = (h2 - h1)**2 + (s2 - s1)**2 + (v2 - v1)**2
    return dist
    

@lru_cache(1)
def get_similar_colors(color, palette):
    similarity = []
    for i, c in enumerate(palette.colors):
        if c[:3] == (0, 0, 0):
            continue
        d = color_distance(color, c)
        similarity.append((d, i, palette.get_color_as_float(c)))
    return sorted(similarity, key=lambda c: c[0])[:9]


class Plugin:

    """
    Displays the colors in the palette that are
    "most similar" to the selected color using the
    YUV color space.
    """
    
    def ui(self, oldpaint, imgui, drawing, brush,
           current_color:int=-1, auto_update=False):
        if current_color is -1:
            current_color = drawing.palette.foreground

        max_index = len(drawing.palette.colors)
        if current_color < 0:
            current_color = 0
        elif current_color >= max_index:
            current_color = max_index - 1

        color = drawing.palette.colors[current_color]
        most_similar_colors = get_similar_colors(color, drawing.palette)
        most_similar_colors.sort(key=lambda c: sum(c[2][:3]))  # order by palette index
        imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND, 0, 0, 0)
        imgui.push_style_var(imgui.STYLE_ITEM_SPACING, (0, 0))
        for i in range(3):
            for j in range(3):
                _, index, c = most_similar_colors[i*3 + j]
                selected = index == drawing.palette.foreground
                if selected:
                    imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND, .25, .25, .25)
                if imgui.color_button(f"color_{index}", *c, 0, 25, 25):
                    drawing.palette.foreground = index
                if j != 2:
                    imgui.same_line()
                if selected:
                    imgui.pop_style_color()

        clicked, auto_update = imgui.checkbox("Auto update", auto_update)
        if auto_update or imgui.button("Update"):
            current_color = drawing.palette.foreground

        imgui.pop_style_var()
        imgui.pop_style_color()

        return {"current_color": current_color, "auto_update": auto_update}
