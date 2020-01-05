"""
Helper functions for rendering the user interface.
"""

from functools import lru_cache
import logging
from math import floor, ceil
import os

import imgui
import pyglet
from pyglet.window import key

from .util import show_save_dialog, throttle


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
        texture = icons[tool.tool.name.lower()]
        with imgui.colored(imgui.COLOR_BUTTON, *TOOL_BUTTON_COLORS[tool == current_tool]):
            if imgui.core.image_button(texture.name, 16, 16):
                tools.select(tool)
                selected = True
            if i % 3 != 2:
                imgui.same_line()
        if imgui.is_item_hovered():
            imgui.begin_tooltip()
            imgui.text(tool.tool.name.lower())
            imgui.end_tooltip()
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
    if imgui.color_button("Foreground", *as_float(fg_color), 0, 30, 30):
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
    if imgui.color_button("Background", *as_float(bg_color), 0, 30, 30):
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
            color = as_float(palette.overlay[i])
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


def render_brushes(brushes, get_texture, size=None, compact=False):

    clicked = False

    for i, brush in enumerate(brushes):
        is_selected = brush == brushes.current
        size1 = size or brush.size
        texture = get_texture(brush=brush, size=size1)
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

            imgui.image(texture.name, *size1,
                        border_color=(1, 1, 1, 1) if is_selected else (.5, .5, .5, 1))
            if imgui.core.is_item_clicked(0):
                clicked = brush

            if i % 3 != 2:
                imgui.same_line()

    imgui.new_line()
    return clicked


def render_edits(drawing):

    imgui.begin("Edits", True)

    imgui.columns(3, 'layerlist')
    imgui.set_column_offset(1, 40)
    imgui.set_column_offset(2, 100)
    n = len(drawing.edits)
    for i, edit in enumerate(reversed(drawing.edits[-50:])):
        imgui.text(str(n - i))
        imgui.next_column()
        imgui.text(edit.index_str)
        imgui.next_column()
        imgui.text(edit.info_str)
        imgui.next_column()

    imgui.end()


def render_unsaved_exit(window):
    if window.unsaved_drawings:
        imgui.open_popup("Really exit?")

    imgui.set_next_window_size(500, 200)
    if imgui.begin_popup_modal("Really exit?")[0]:
        imgui.text("You have unsaved work in these drawing(s):")

        imgui.begin_child("unsaved", border=True,
                          height=imgui.get_content_region_available()[1] - 26)
        for drawing in window.unsaved_drawings:
            imgui.text(drawing.filename)
            if imgui.is_item_hovered():
                pass  # TODO popup thumbnail of the picture?
        imgui.end_child()

        if imgui.button("Yes, exit anyway"):
            imgui.close_current_popup()
            pyglet.app.exit()
        imgui.same_line()
        if imgui.button("Yes, but save first"):
            for drawing in window.unsaved_drawings:
                window.save_drawing(drawing)
            pyglet.app.exit()
        imgui.same_line()
        if imgui.button("No, cancel"):
            window.unsaved_drawings = None
            imgui.close_current_popup()
        imgui.end_popup()


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


def render_main_menu(window):

    w, h = window.get_size()

    if imgui.begin_main_menu_bar():
        if imgui.begin_menu("File", True):

            clicked_load, selected_load = imgui.menu_item("Load", "o", False, True)
            if clicked_load:
                window.load_drawing()

            if imgui.begin_menu("Load recent...", window.recent_files):
                for path in reversed(window.recent_files):
                    clicked, _ = imgui.menu_item(os.path.basename(path), None, False, True)
                    if clicked:
                        window.load_drawing(path)
                imgui.end_menu()

            imgui.separator()

            clicked_save, selected_save = imgui.menu_item("Save", "s", False, window.drawing)
            if clicked_save:
                window.save_drawing()

            clicked_save_as, selected_save = imgui.menu_item("Save as", "S", False, window.drawing)
            if clicked_save_as:
                window.save_drawing(ask_for_path=True)

            imgui.separator()

            clicked_quit, selected_quit = imgui.menu_item(
                "Quit", 'Cmd+Q', False, True
            )
            if clicked_quit:
                window._quit()

            imgui.end_menu()

        if imgui.begin_menu("Drawing", True):
            if imgui.menu_item("New", None, False, True)[0]:
                window._create_drawing()

            elif imgui.menu_item("Close", None, False, window.drawing)[0]:
                window._close_drawing()

            imgui.separator()

            if imgui.menu_item("Flip horizontally", "H", False, window.drawing)[0]:
                window.drawing.flip_horizontal()
            if imgui.menu_item("Flip vertically", "V", False, window.drawing)[0]:
                window.drawing.flip_vertical()

            imgui.separator()

            if imgui.menu_item("Undo", "z", False, window.drawing)[0]:
                window.drawing.undo()
            elif imgui.menu_item("Redo", "y", False, window.drawing)[0]:
                window.drawing.redo()

            imgui.separator()

            for drawing in window.drawings.items:
                if imgui.menu_item(f"{drawing.filename} {drawing.size}",
                                   None, drawing == window.drawing, True)[0]:
                    window.drawings.select(drawing)
            imgui.end_menu()

        if imgui.begin_menu("Layer", bool(window.drawing)) :

            layer = window.drawing.layers.current
            index = window.drawing.layers.index(layer)
            n_layers = len(window.drawing.layers)

            if imgui.menu_item("Add", "L", False, True)[0]:
                window.drawing.add_layer()
            if imgui.menu_item("Remove", None, False, True)[0]:
                window.drawing.remove_layer()
            if imgui.menu_item("Merge down", None, False, index > 0)[0]:
                window.drawing.merge_layer_down()

            if imgui.menu_item("Toggle visibility", "v", False, True)[0]:
                layer.visible = not layer.visible
            if imgui.menu_item("Move up", "w", False, index < n_layers-1)[0]:
                window.drawing.move_layer_up()
            if imgui.menu_item("Move down", "s", False, index > 0)[0]:
                window.drawing.move_layer_down()

            imgui.separator()

            if imgui.menu_item("Flip horizontally", "H", False, True)[0]:
                window.drawing.flip_layer_horizontal()
            if imgui.menu_item("Flip vertically", "V", False, True)[0]:
                window.drawing.flip_layer_vertical()
            if imgui.menu_item("Clear", "Delete", False, True)[0]:
                window.drawing.clear()

            imgui.separator()

            hovered_layer = None
            for i, layer in enumerate(reversed(window.drawing.layers)):
                selected = window.drawing.layers.current == layer
                index = n_layers - i - 1
                if imgui.menu_item(f"{index} {'v' if layer.visible else ''}", str(index), selected, True)[1]:
                    window.drawing.layers.select(layer)
                if imgui.is_item_hovered():
                    hovered_layer = layer

                    imgui.begin_tooltip()
                    texture = window.get_layer_preview_texture(layer,
                                                             colors=window.drawing.palette.as_tuple())
                    lw, lh = texture.size
                    aspect = w / h
                    max_size = 256
                    if aspect > 1:
                        pw = max_size
                        ph = int(max_size / aspect)
                    else:
                        pw = int(max_size * aspect)
                        ph = max_size
                    imgui.image(texture.name, pw, ph, border_color=(.25, .25, .25, 1))
                    imgui.end_tooltip()

            window.highlighted_layer = hovered_layer

            imgui.end_menu()

        if imgui.begin_menu("Brush", bool(window.drawing)):
            if imgui.menu_item("Save current", None, False, window.drawing.brushes.current)[0]:
                fut = window.executor.submit(show_save_dialog,
                                             title="Select file",
                                             filetypes=(
                                                 ("PNG files", "*.png"),
                                                 ("all files", "*.*"))
                                             )

                def save_brush(fut):
                    path = fut.result()
                    if path:
                        window.add_recent_file(path)
                        window.drawing.brushes.current.save_png(path, window.drawing.palette.colors)

                fut.add_done_callback(save_brush)

            elif imgui.menu_item("Remove", None, False, window.drawing.brushes.current)[0]:
                window.drawing.brushes.remove()

            elif imgui.menu_item("Flip horizontally", None, False, window.drawing.brushes.current)[0]:
                window.brush.flip_horizontal()
                # window.get_brush_preview_texture.cache_clear()

            elif imgui.menu_item("Flip vertically", None, False, window.drawing.brushes.current)[0]:
                window.brush.flip_vertical()

            elif imgui.menu_item("Rotate clockwise", None, False, window.drawing.brushes.current)[0]:
                window.brush.rotate_clockwise()
                # window.get_brush_preview_texture.cache_clear()

            elif imgui.menu_item("Rotate counter clockwise", None, False, window.drawing.brushes.current)[0]:
                window.brush.rotate_counter_clockwise()
                # window.get_brush_preview_texture.cache_clear()

            imgui.separator()

            for i, brush in enumerate(reversed(window.drawing.brushes[-10:])):

                is_selected = window.drawing.brushes.current == brush

                bw, bh = brush.size
                clicked, selected = imgui.menu_item(f"{bw}x{bh}", None, is_selected, True)

                if selected:
                    window.drawing.brushes.select(brush)

                if imgui.is_item_hovered():
                    imgui.begin_tooltip()
                    texture = window.get_brush_preview_texture(brush,
                                                               colors=window.drawing.palette.as_tuple())
                    imgui.image(texture.name, *texture.size, border_color=(.25, .25, .25, 1))
                    imgui.end_tooltip()

            imgui.end_menu()

        if imgui.begin_menu("Info", True):
            _, state = imgui.menu_item("Show edit history", None, window.window_visibility["edits"], True)
            window.window_visibility["edits"] = state
            imgui.end_menu()

        # Show some info in the right part of the menu bar

        imgui.set_cursor_screen_pos((w // 2, 0))
        drawing = window.drawing
        if drawing:
            imgui.text(f"{drawing.filename} {drawing.size} {'*' if drawing.unsaved else ''}")

            imgui.set_cursor_screen_pos((w - 200, 0))
            imgui.text(f"Zoom: x{2**window.zoom}")

            if window.mouse_position:
                imgui.set_cursor_screen_pos((w - 100, 0))
                x, y = window._to_image_coords(*window.mouse_position)
                if window.stroke_tool:
                    txt = repr(window.stroke_tool)
                    if txt:
                        imgui.text(txt)
                    else:
                        imgui.text(f"{int(x)}, {int(y)}")
                else:
                    imgui.text(f"{int(x)}, {int(y)}")
                # imgui.set_cursor_screen_pos((w - 30, 0))
                # color_index = window.drawing.layers.current.pic.get_pixel(x, y)
                # r, g, b, _ = window.drawing.palette.colors[color_index]
                # imgui.color_button("current_color", r/255, g/255, b/255, 0, 10, 20, 20)

        imgui.end_main_menu_bar()

