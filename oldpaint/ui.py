"""
Helper functions for rendering the user interface.
"""

from functools import lru_cache
import logging

import imgui
import pyglet
from pyglet.window import key

logger = logging.getLogger(__name__)


# A hacky way to keep short-lived UI state. Find a better way!
temp_vars = {}


TOOL_BUTTON_COLORS = [
    (0.5, 0.5, 0.5),  # normal
    (1, 1, 1)         # selected
]

SELECTABLE_FRAME_COLORS = [
    (0, 0, 0),         # normal
    (1, 1, 1),         # foreground
    (0.5, 0.5, 0.5),   # background
    (1, 1, 0)          # both
]


def render_tools(tools, icons):
    current_tool = tools.current
    selected = False
    for i, tool in enumerate(tools):
        texture = icons[tool.tool]
        with imgui.colored(imgui.COLOR_BUTTON, *TOOL_BUTTON_COLORS[tool == current_tool]):
            if imgui.core.image_button(texture.name, 16, 16):
                tools.select(tool)
                selected = True
            if i % 3 != 2:
                imgui.same_line()
    return selected


@lru_cache(256)
def as_float(color):
    r, g, b, a = color
    return (r/256, g/256, b/256, a/256)


def render_color_editor(orig, color):
    r, g, b, a = color

    imgui.push_id("R")
    _, r = imgui.v_slider_int("", 30, 255, r, min_value=0, max_value=255)
    imgui.pop_id()
    imgui.same_line()
    imgui.push_id("G")
    _, g = imgui.v_slider_int("", 30, 255, g, min_value=0, max_value=255)
    imgui.pop_id()
    imgui.same_line()
    imgui.push_id("B")
    _, b = imgui.v_slider_int("", 30, 255, b, min_value=0, max_value=255)
    imgui.pop_id()

    imgui.color_button("Current color", *as_float(orig))
    imgui.same_line()
    imgui.text("->")
    imgui.same_line()
    imgui.color_button("Current color", *as_float(color))

    if imgui.button("OK"):
        imgui.close_current_popup()
        return True, False, (r, g, b, a)
    imgui.same_line()
    if imgui.button("Cancel"):
        imgui.close_current_popup()
        return False, True, (r, g, b, a)
    return False, False, (r, g, b, a)


palette_overlay = {}


def render_palette(drawing):

    palette = drawing.palette
    fg = palette.foreground
    bg = palette.background
    fg_color = palette.foreground_color
    bg_color = palette.background_color

    # Edit foreground color
    if imgui.color_button("Foreground", *palette.as_float(fg_color), 0, 30, 30):
        io = imgui.get_io()
        w, h = io.display_size
        imgui.open_popup("Edit foreground color")
        imgui.set_next_window_position(w - 115 - 120, 200)
    if imgui.begin_popup("Edit foreground color"):
        done, cancelled, new_color = render_color_editor(palette.colors[fg], fg_color)
        if done:
            drawing.change_colors(fg, [new_color])
            palette.clear_overlay()
        elif cancelled:
            palette.clear_overlay()
        else:
            palette.set_overlay(fg, new_color)
        imgui.end_popup()

    imgui.same_line()

    # Edit background color
    if imgui.color_button("Background", *palette.as_float(bg_color), 0, 30, 30):
        imgui.open_popup("Edit background color")
    # if imgui.begin_popup("Edit background color"):
    #     done, cancelled, new_color = render_color_editor(palette.colors[bg], bg_color)
    #     if done:
    #         drawing.change_colors(bg, [new_color])
    #         palette.clear_overlay()
    #     elif cancelled:
    #         palette.clear_overlay()
    #     else:
    #         palette.set_overlay(bg, new_color)
    #     imgui.end_popup()

    imgui.begin_child("Palette", border=False)
    imgui.push_style_var(imgui.STYLE_ITEM_SPACING, (0, 0))  # Make layout tighter
    width = int(imgui.get_window_content_region_width()) // 20
    spread_start = temp_vars.get("spread_start")
    for i, color in enumerate(palette):
        is_foreground = i == fg
        is_background = (i == bg) * 2
        selection = is_foreground | is_background
        if i in palette.overlay:
            color = palette.as_float(palette.overlay[i])
        else:
            color = as_float(color)
        imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND,
                               *SELECTABLE_FRAME_COLORS[selection])
        if imgui.color_button(f"color {i}", *color[:3], 1, 0, 20, 20):
            io = imgui.get_io()
            if io.key_shift:
                if "spread_start" in temp_vars:
                    temp_vars["spread_end"] = i
                else:
                    temp_vars["spread_start"] = i
            else:
                fg = i
        if imgui.core.is_item_clicked(2):
            # Detect right button clicks on the button
            bg = i

        imgui.pop_style_color(1)

        if i % width != width - 1:
            imgui.same_line()
    imgui.pop_style_var(1)
    imgui.end_child()
    # imgui.end()

    palette.foreground = fg
    palette.background = bg

    if "spread_start" in temp_vars and "spread_end" in temp_vars:
        spread_start = temp_vars.pop("spread_start")
        spread_end = temp_vars.pop("spread_end")
        from_index = min(spread_start, spread_end)
        to_index = max(spread_start, spread_end)
        spread_colors = palette.spread(from_index, to_index)
        drawing.change_colors(from_index + 1, spread_colors)


def render_layers(drawing):

    imgui.columns(2, "Layers")
    imgui.set_column_offset(1, 100)
    if imgui.button("Add"):
        drawing.add_layer()
    if imgui.button("Remove"):
        drawing.remove_layer()
    if imgui.button("Down"):
        drawing.move_layer_down()
    if imgui.button("Up"):
        drawing.move_layer_up()

    imgui.next_column()

    imgui.begin_child("Layers", border=False, height=0)
    selected = None
    n = len(drawing.layers)
    hovered = None
    imgui.columns(2, 'layerlist_header')
    imgui.text("#")
    imgui.set_column_offset(1, 40)
    imgui.next_column()
    imgui.text("Show")
    imgui.next_column()
    imgui.separator()
    imgui.columns(1)

    imgui.begin_child("Layers list", border=False, height=0)
    imgui.columns(2, 'layerlist_header')
    for i, layer in zip(range(n - 1, -1, -1), reversed(drawing.layers)):
        _, selected = imgui.selectable(str(i), layer == drawing.current,
                                       imgui.SELECTABLE_SPAN_ALL_COLUMNS)
        if selected:
            drawing.layers.current = layer
        if imgui.is_item_hovered():
            hovered = layer
        imgui.set_column_offset(1, 40)
        imgui.next_column()

        imgui.set_item_allow_overlap()  # Let the checkbox overlap
        clicked, _ = imgui.checkbox(f"##checkbox{i}", layer.visible)
        if clicked:
            layer.visible = not layer.visible
        imgui.next_column()

        # if texture:
        #     imgui.image(texture.name, 100, 100*texture.aspect,
        #                 border_color=(1, 1, 1, 1) if is_current else (0.5, 0.5, 0.5, 1))
        #     if imgui.core.is_item_clicked(0) and not is_current:
        #         logger.info("selected %r", layer)
        #         selected = layer

    imgui.columns(1)
    imgui.end_child()
    imgui.end_child()

    return hovered


def render_brushes(brushes, get_texture, compact=False):

    clicked = False

    for brush in brushes:
        is_selected = brush == brushes.current
        texture = get_texture(brush)
        if texture:
            w, h = brush.size
            if w > 50 or h > 50:
                aspect = w / h
                if w > h:
                    w = 50
                    h = w / aspect
                else:
                    h = 50
                    w = h * aspect

            #imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND, *SELECTABLE_FRAME_COLORS[is_selected])
            imgui.image(texture.name, w*2, h*2, border_color=(1, 1, 1, 1) if is_selected else (.5, .5, .5, 1))
            #imgui.pop_style_color(1)

            if imgui.core.is_item_clicked(0):
                brushes.select(brush)
                clicked = brush
        if compact:
            imgui.same_line()

    imgui.new_line()
    return clicked


def render_edits(drawing):

    #imgui.begin("Edits", True)

    imgui.columns(2, 'layerlist')
    imgui.set_column_offset(1, 40)
    n = len(drawing.edits)
    for i, edit in enumerate(reversed(drawing.edits[-50:])):
        imgui.text(str(n - i))
        imgui.next_column()
        imgui.text(str(type(edit).__name__))
        imgui.next_column()
    #imgui.end()


def render_unsaved_exit(unsaved):
    if unsaved:
        imgui.open_popup("Really exit?")

    imgui.set_next_window_size(500, 200)
    if imgui.begin_popup_modal("Really exit?")[0]:
        imgui.text("You have unsaved work in these drawing(s):")

        imgui.begin_child("unsaved", border=True,
                          height=imgui.get_content_region_available()[1] - 26)
        for drawing in unsaved:
            imgui.text(drawing.filename)
        imgui.end_child()

        if imgui.button("Yes, exit anyway"):
            imgui.close_current_popup()
            pyglet.app.exit()
        imgui.same_line()
        if imgui.button("No, cancel"):
            unsaved = None
            imgui.close_current_popup()
        imgui.end_popup()

    return unsaved


def render_tool_menu(tools, icons):
    # TODO find out a way to close if user clicks outside the window
    imgui.open_popup("Tools menu")
    if imgui.begin_popup("Tools menu", flags=(imgui.WINDOW_NO_TITLE_BAR
                                              | imgui.WINDOW_NO_RESIZE)):
        done = render_tools(tools, icons)
        if done:
            imgui.core.close_current_popup()
        imgui.end_popup()
        return done
