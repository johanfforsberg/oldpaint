"""
This plugin displays a grid of colors similar to the one currently selected as foreground. It
can be a useful way to navigate the palette.
"""

from functools import lru_cache
from queue import PriorityQueue


def color_distance(color1, color2):
    r1, g1, b1, _ = color1
    r2, g2, b2, _ = color2
    return abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
    

@lru_cache(1)
def get_similar_colors(color, palette):
    similarity = []
    for i, c in enumerate(palette.colors):
        d = color_distance(c, color)
        similarity.append((d, i, palette.get_color_as_float(c)))
    return sorted(similarity)[:9]


def ui_plugin(oldpaint, imgui, drawing, brush):
    """
    Displays the colors in the palette
    most similar to the current foreground.
    """
    current_color = drawing.palette.foreground_color
    most_similar_colors = get_similar_colors(current_color, drawing.palette)
    imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND, 0, 0, 0)
    imgui.push_style_var(imgui.STYLE_ITEM_SPACING, (0, 0))
    for i in range(3):
        for j in range(3):
            if (i, j) == (0, 0):
                imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND, .25, .25, .25)
            _, index, c = most_similar_colors[i*3 + j]
            if imgui.color_button(f"color_{index}", *c, 0, 25, 25):
                drawing.palette.foreground = index
            if j != 2:
                imgui.same_line()
            if (i, j) == (0, 0):
                imgui.pop_style_color()
                
    imgui.pop_style_var()
    imgui.pop_style_color()
    return {}        
