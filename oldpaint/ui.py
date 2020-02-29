"""
Helper functions for rendering the user interface.
"""

from functools import lru_cache
import logging
from math import floor, ceil
import os
import sys

import imgui
import pyglet
from pyglet.window import key

from .drawing import Drawing
from .util import show_save_dialog, throttle


logger = logging.getLogger(__name__)


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


def _change_channel(value, delta):
    return max(0, min(255, value + delta))


def render_color_editor(orig, color):
    r, g, b, a = color

    io = imgui.get_io()

    delta = 0
    imgui.push_id("R")
    # TODO find a less verbose way to do something like this:
    # imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND, r/255, 0, 0)
    # imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND_HOVERED, r/255, 0, 0)
    # imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND_ACTIVE, r/255, 0, 0)
    # imgui.push_style_color(imgui.COLOR_SLIDER_GRAB, 1, 1, 1)
    # imgui.push_style_color(imgui.COLOR_SLIDER_GRAB_ACTIVE, 1, 1, 1)
    _, r = imgui.v_slider_int("", 30, 255, r, min_value=0, max_value=255)
    # imgui.pop_style_color()
    # imgui.pop_style_color()
    # imgui.pop_style_color()
    # imgui.pop_style_color()
    # imgui.pop_style_color()
    if imgui.is_item_hovered():
        delta = int(io.mouse_wheel)
        if not io.key_shift:
            r = _change_channel(r, delta)
    imgui.pop_id()
    imgui.same_line()
    imgui.push_id("G")
    _, g = imgui.v_slider_int("", 30, 255, g, min_value=0, max_value=255)
    if imgui.is_item_hovered():
        delta = int(io.mouse_wheel)
        if not io.key_shift:
            g = _change_channel(g, delta)
    imgui.pop_id()
    imgui.same_line()
    imgui.push_id("B")
    _, b = imgui.v_slider_int("", 30, 255, b, min_value=0, max_value=255)
    if imgui.is_item_hovered():
        delta = int(io.mouse_wheel)
        if not io.key_shift:
            b = _change_channel(b, delta)
    imgui.pop_id()

    if delta and io.key_shift:
        r = _change_channel(r, delta)
        g = _change_channel(g, delta)
        b = _change_channel(b, delta)

    if imgui.checkbox("Transp.", a == 0)[1]:
        a = 0
    else:
        a = 255

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

color_editor_open = False
current_color_page = 0

def render_palette(drawing: Drawing):

    global color_editor_open  # Need a persistent way to keep track of the popup being closed...
    global current_color_page

    palette = drawing.palette
    fg = palette.foreground
    bg = palette.background
    fg_color = palette.foreground_color
    bg_color = palette.background_color

    # Edit foreground color
    if imgui.color_button(f"Foreground (#{fg})", *as_float(fg_color), 0, 30, 30):
        io = imgui.get_io()
        w, h = io.display_size
        imgui.open_popup("Edit foreground color")
        imgui.set_next_window_position(w - 115 - 120, 200)
        color_editor_open = True
    if imgui.begin_popup("Edit foreground color", flags=(imgui.WINDOW_NO_MOVE |
                                                         imgui.WINDOW_NO_SCROLL_WITH_MOUSE)):
        done, cancelled, new_color = render_color_editor(palette.colors[fg], fg_color)
        if done and new_color != fg_color:
            drawing.change_colors(fg, [new_color])
            palette.clear_overlay()
        elif cancelled:
            palette.clear_overlay()
        else:
            palette.set_overlay(fg, new_color)
        imgui.end_popup()
    elif color_editor_open:
        # The popup was closed by clicking outside, keeping the change (same as OK)
        drawing.change_colors(fg, [fg_color])
        palette.clear_overlay()
        color_editor_open = False

    imgui.same_line()

    # Edit background color
    if imgui.color_button(f"Background (#{bg})", *as_float(bg_color), 0, 30, 30):
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

    max_pages = len(palette.colors) // 64 - 1
    imgui.push_item_width(100)
    _, current_color_page = imgui.slider_int("Page", current_color_page, min_value=0, max_value=max_pages)
    start_color = 64 * current_color_page

    imgui.begin_child("Palette", border=False)
    imgui.push_style_var(imgui.STYLE_ITEM_SPACING, (0, 0))  # Make layout tighter
    width = int(imgui.get_window_content_region_width()) // 20
    for i, color in enumerate(palette[start_color:start_color + 64], start_color):
        is_foreground = i == fg
        is_background = (i == bg) * 2
        selection = is_foreground | is_background
        if i in palette.overlay:
            color = as_float(palette.overlay[i])
        else:
            color = as_float(color)
        imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND,
                               *SELECTABLE_FRAME_COLORS[selection])
        if imgui.color_button(f"color {i}", *color[:3], 1, 0, 25, 25):
            # io = imgui.get_io()
            # if io.key_shift:
            #     if "spread_start" in temp_vars:
            #         temp_vars["spread_end"] = i
            #     else:
            #         temp_vars["spread_start"] = i
            # else:
            fg = i
        imgui.pop_style_color(1)

        if imgui.core.is_item_clicked(2):
            # Detect right button clicks on the button
            bg = i

        if imgui.begin_drag_drop_source():
            imgui.set_drag_drop_payload('start_index', i.to_bytes(1, sys.byteorder))
            imgui.color_button(f"color {i}", *color[:3], 1, 0, 20, 20)
            imgui.end_drag_drop_source()
        if imgui.begin_drag_drop_target():
            start_index = imgui.accept_drag_drop_payload('start_index')
            if start_index is not None:
                start_index = int.from_bytes(start_index, sys.byteorder)
                io = imgui.get_io()
                image_only = io.key_shift
                drawing.swap_colors(start_index, i, image_only=image_only)
                palette.clear_overlay()
            imgui.end_drag_drop_target()

        if imgui.is_item_hovered():
            io = imgui.get_io()
            delta = int(io.mouse_wheel)
            current_color_page = min(max(current_color_page + delta, 0), max_pages)

        if i % width != width - 1:
            imgui.same_line()
    imgui.pop_style_var(1)
    imgui.end_child()
    # imgui.end()

    palette.foreground = fg
    palette.background = bg

    # if "spread_start" in temp_vars and "spread_end" in temp_vars:
    #     spread_start = temp_vars.pop("spread_start")
    #     spread_end = temp_vars.pop("spread_end")
    #     from_index = min(spread_start, spread_end)
    #     to_index = max(spread_start, spread_end)
    #     spread_colors = palette.spread(from_index, to_index)
    #     drawing.change_colors(from_index + 1, spread_colors)


edit_color = 0

def render_palette_popup(drawing: Drawing):

    global edit_color
    global color_editor_open

    palette = drawing.palette
    fg = palette.foreground
    bg = palette.background
    fg_color = palette.foreground_color
    bg_color = palette.background_color
    open_color_editor = False

    _, opened = imgui.begin("Color popup", True)

    imgui.begin_child("Colors", width=0, height=0)

    imgui.push_style_var(imgui.STYLE_ITEM_SPACING, (0, 0))  # Make layout tighter
    width = int(imgui.get_window_content_region_width()) // 25

    for i, color in enumerate(palette, 0):
        is_foreground = i == fg
        is_background = (i == bg) * 2
        selection = is_foreground | is_background
        if i in palette.overlay:
            color = as_float(palette.overlay[i])
        else:
            color = as_float(color)
        imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND,
                               *SELECTABLE_FRAME_COLORS[selection])
        if imgui.color_button(f"color {i}", *color[:3], 1, 0, 25, 25):
            # io = imgui.get_io()
            # if io.key_shift:
            #     if "spread_start" in temp_vars:
            #         temp_vars["spread_end"] = i
            #     else:
            #         temp_vars["spread_start"] = i
            # else:
            fg = i
        imgui.pop_style_color(1)

        if imgui.core.is_item_clicked(1):
            edit_color = i
            color_editor_open = True
            imgui.open_popup("Edit foreground color")
            # imgui.set_next_window_position(w - 115 - 120, 200)

        if imgui.core.is_item_clicked(2):
            # Detect right button clicks on the button
            bg = i

        if imgui.begin_drag_drop_source():
            imgui.set_drag_drop_payload('start_index', i.to_bytes(1, sys.byteorder))
            imgui.color_button(f"color {i}", *color[:3], 1, 0, 20, 20)
            imgui.end_drag_drop_source()
        if imgui.begin_drag_drop_target():
            start_index = imgui.accept_drag_drop_payload('start_index')
            if start_index is not None:
                start_index = int.from_bytes(start_index, sys.byteorder)
                io = imgui.get_io()
                image_only = io.key_shift
                drawing.swap_colors(start_index, i, image_only=image_only)
                palette.clear_overlay()
            imgui.end_drag_drop_target()

        # if imgui.is_item_hovered():
        #     io = imgui.get_io()
        #     delta = int(io.mouse_wheel)

        if i % width != width - 1:
            imgui.same_line()

    imgui.pop_style_var(1)
    color_editor_open = render_color_editor_popup(drawing, edit_color, color_editor_open)

    imgui.end_child()
    imgui.end()

    palette.foreground = fg
    palette.background = bg

    return opened, open_color_editor


def render_color_editor_popup(drawing, i, still_open):

    palette = drawing.palette
    orig_color = palette.colors[i]
    color = palette.get_color(i)
    if imgui.begin_popup("Edit foreground color", flags=(imgui.WINDOW_NO_MOVE |
                                                         imgui.WINDOW_NO_SCROLL_WITH_MOUSE)):
        done, cancelled, new_color = render_color_editor(palette.colors[i], color)
        if done and new_color != orig_color:
            drawing.change_colors(i, [new_color])
            palette.clear_overlay()
            still_open = False
        elif cancelled:
            palette.clear_overlay()
            still_open = False
        else:
            palette.set_overlay(i, new_color)
        imgui.end_popup()
    elif still_open:
        # The popup was closed by clicking outside, keeping the change (same as OK)
        drawing.change_colors(i, [color])
        palette.clear_overlay()
        still_open = False
    return still_open


def render_layers(drawing: Drawing):

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

    imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND, 1, 1, 1)
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
    imgui.pop_style_color()

    imgui.new_line()
    return clicked


def render_edits(drawing):

    imgui.begin("Edits", True)

    imgui.columns(3, 'layerlist')
    imgui.set_column_offset(1, 40)
    imgui.set_column_offset(2, 100)
    n = len(drawing.edits)
    selection = None
    for i, edit in enumerate(reversed(drawing.edits[-50:])):
        imgui.text(str(n - i))
        imgui.next_column()
        imgui.text(edit.index_str)
        imgui.next_column()
        imgui.button(edit.info_str)
        if hasattr(edit, "rect"):
            if imgui.is_item_hovered():
                selection = edit.rect
        imgui.next_column()
    drawing.selection = selection
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

            clicked_save, selected_save = imgui.menu_item("Save", "Ctrl+s", False, window.drawing)
            if clicked_save:
                window.save_drawing()

            clicked_save_as, selected_save = imgui.menu_item("Save as", None, False, window.drawing)
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

            if imgui.menu_item("Flip horizontally", None, False, window.drawing)[0]:
                window.drawing.flip_horizontal()
            if imgui.menu_item("Flip vertically", None, False, window.drawing)[0]:
                window.drawing.flip_vertical()

            imgui.separator()

            if imgui.menu_item("Undo", "z", False, window.drawing and window.drawing.can_undo)[0]:
                window.drawing.undo()
            elif imgui.menu_item("Redo", "y", False, window.drawing and window.drawing.can_redo)[0]:
                window.drawing.redo()

            imgui.separator()

            selected = imgui.menu_item("Show selection", "z", window.drawing and window.drawing.selection, window.drawing)[1]
            if window.drawing:
                window.drawing.show_selection = selected
            imgui.separator()

            for drawing in window.drawings.items:
                if imgui.menu_item(f"{drawing.filename} {drawing.size}",
                                   None, drawing == window.drawing, True)[0]:
                    window.drawings.select(drawing)
            imgui.end_menu()

        if imgui.begin_menu("Layer", bool(window.drawing)):

            layer = window.drawing.layers.current
            index = window.drawing.layers.index(layer)
            n_layers = len(window.drawing.layers)

            if imgui.menu_item("Add", "l", False, True)[0]:
                window.drawing.add_layer()
            if imgui.menu_item("Remove", None, False, True)[0]:
                window.drawing.remove_layer()
            if imgui.menu_item("Merge down", None, False, index > 0)[0]:
                window.drawing.merge_layer_down()

            if imgui.menu_item("Toggle visibility", "V", False, True)[0]:
                layer.visible = not layer.visible
            if imgui.menu_item("Move up", "W", False, index < n_layers-1)[0]:
                window.drawing.move_layer_up()
            if imgui.menu_item("Move down", "S", False, index > 0)[0]:
                window.drawing.move_layer_down()

            imgui.separator()

            if imgui.menu_item("Flip horizontally", None, False, True)[0]:
                window.drawing.flip_layer_horizontal()
            if imgui.menu_item("Flip vertically", None, False, True)[0]:
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

            if imgui.menu_item("Flip horizontally", None, False, window.drawing.brushes.current)[0]:
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

        if imgui.begin_menu("Info", bool(window.drawing)):
            _, state = imgui.menu_item("Show edit history", None, window.window_visibility["edits"], True)
            window.window_visibility["edits"] = state
            imgui.end_menu()

        if imgui.begin_menu("Plugins", bool(window.drawing)):
            active_plugins = window.drawing.active_plugins.values()
            for name, plugin in window.plugins.items():
                is_active = plugin in active_plugins
                clicked, selected = imgui.menu_item(name, None, is_active, True)
                if selected:
                    window.drawing.active_plugins[name] = plugin
                elif is_active:
                    del window.drawing.active_plugins[name]
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

