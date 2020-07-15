"""
Helper functions for rendering the user interface.
"""

from functools import lru_cache
from itertools import chain
import logging
from math import floor, ceil
import os
import sys
from time import time
from typing import Tuple, NamedTuple

import imgui
import pyglet
from pyglet.window import key

from .drawing import Drawing
from .util import show_save_dialog, throttle


logger = logging.getLogger(__name__)


class UIState(NamedTuple):
    color_editor_open: bool = False  # Need a persistent way to keep track of the popup being closed...
    current_color_page: int = 0
    animation_settings_open: bool = False
    new_drawing_size: Tuple[int, int] = None


def update_state(state, **kwargs):
    return type(state)(**{**state._asdict(), **kwargs})
    

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


def render_tools(state, tools, icons):
    current_tool = tools.current
    selected = False
    for i, tool in enumerate(tools):
        texture = icons[tool.tool.name]
        with imgui.colored(imgui.COLOR_BUTTON, *TOOL_BUTTON_COLORS[tool == current_tool]):
            if imgui.image_button(texture.name, 16, 16):
                tools.select(tool)
                selected = True
            if i % 3 != 2:
                imgui.same_line()
        if imgui.is_item_hovered():
            imgui.begin_tooltip()
            imgui.text(tool.tool.name.lower())
            imgui.end_tooltip()
    return state


@lru_cache(256)
def as_float(color):
    r, g, b, a = color
    return (r/256, g/256, b/256, a/256)


def _change_channel(value, delta):
    return max(0, min(255, value + delta))


def render_color_editor(state, orig, color):
    r0, g0, b0, a0 = r, g, b, a = color

    io = imgui.get_io()

    delta = 0
    
    imgui.push_id("R")
    with imgui.colored(imgui.COLOR_FRAME_BACKGROUND, r/255, 0, 0), \
         imgui.colored(imgui.COLOR_FRAME_BACKGROUND_HOVERED, r/255, 0, 0), \
         imgui.colored(imgui.COLOR_FRAME_BACKGROUND_ACTIVE, r/255, 0, 0), \
         imgui.colored(imgui.COLOR_SLIDER_GRAB, .5, .5, .5), \
         imgui.colored(imgui.COLOR_SLIDER_GRAB_ACTIVE, .7, .7, .7):
        r_changed, r = imgui.v_slider_int("", 30, 255, r, min_value=0, max_value=255)
        
    if r_changed and io.key_shift:
        dr = r - r0
        g = _change_channel(g, dr)
        b = _change_channel(b, dr)
    elif imgui.is_item_hovered():
        delta = int(io.mouse_wheel)
        if not io.key_shift:
            r = _change_channel(r, delta)
    imgui.pop_id()
    
    imgui.same_line()
    imgui.push_id("G")
    with imgui.colored(imgui.COLOR_FRAME_BACKGROUND, 0, g/255, 0), \
         imgui.colored(imgui.COLOR_FRAME_BACKGROUND_HOVERED, 0, g/255, 0), \
         imgui.colored(imgui.COLOR_FRAME_BACKGROUND_ACTIVE, 0, g/255, 0), \
         imgui.colored(imgui.COLOR_SLIDER_GRAB, .5, .5, .5), \
         imgui.colored(imgui.COLOR_SLIDER_GRAB_ACTIVE, .7, .7, .7):    
        g_changed, g = imgui.v_slider_int("", 30, 255, g, min_value=0, max_value=255)
    if g_changed and io.key_shift:
        dg = g - g0
        r = _change_channel(r, dg)
        b = _change_channel(b, dg)
    elif imgui.is_item_hovered():
        delta = int(io.mouse_wheel)
        if not io.key_shift:
            g = _change_channel(g, delta)
    imgui.pop_id()

    imgui.same_line()
    imgui.push_id("B")
    with imgui.colored(imgui.COLOR_FRAME_BACKGROUND, 0, 0, b/255), \
         imgui.colored(imgui.COLOR_FRAME_BACKGROUND_HOVERED, 0, 0, b/255), \
         imgui.colored(imgui.COLOR_FRAME_BACKGROUND_ACTIVE, 0, 0, b/255), \
         imgui.colored(imgui.COLOR_SLIDER_GRAB, .5, .5, .5), \
         imgui.colored(imgui.COLOR_SLIDER_GRAB_ACTIVE, .7, .7, .7):    
        b_changed, b = imgui.v_slider_int("", 30, 255, b, min_value=0, max_value=255)
    if b_changed and io.key_shift:
        db = b - b0
        r = _change_channel(r, db)
        g = _change_channel(g, db)
    elif imgui.is_item_hovered():
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
        return (r, g, b, a) != orig, False, (r, g, b, a)
    imgui.same_line()
    if imgui.button("Cancel"):
        imgui.close_current_popup()
        return False, True, (r, g, b, a)
    return False, False, (r, g, b, a)


palette_overlay = {}

color_editor_open = False
current_color_page = 0

def render_palette(state: UIState, drawing: Drawing):

    # global color_editor_open  # Need a persistent way to keep track of the popup being closed...
    # global current_color_page

    palette = drawing.palette
    fg = palette.foreground
    bg = palette.background
    fg_color = palette.foreground_color
    bg_color = palette.background_color

    color_editor_open = state.color_editor_open
    imgui.begin_child("Palette", border=False, height=460)
    # Edit foreground color
    if imgui.color_button(f"Foreground (#{fg})", *as_float(fg_color), 0, 30, 30):
        io = imgui.get_io()
        w, h = io.display_size
        imgui.open_popup("Edit foreground color")
        imgui.set_next_window_position(w - 115 - 120, 200)
        color_editor_open = True
    if imgui.begin_popup("Edit foreground color", flags=(imgui.WINDOW_NO_MOVE |
                                                         imgui.WINDOW_NO_SCROLL_WITH_MOUSE)):
        done, cancelled, new_color = render_color_editor(state, palette.colors[fg], fg_color)
        if done:
            # Color was changed and then OK was clicked; make change and close
            drawing.change_colors((fg, new_color))
            palette.clear_overlay()
            color_editor_open = False
        elif cancelled:
            # Cancel was clicked; disregard any changes and close
            palette.clear_overlay()
            color_editor_open = False
        else:
            # Keep editing color
            palette.set_overlay(fg, new_color)

        imgui.end_popup()
    elif state.color_editor_open:
        # The popup was closed by clicking outside, keeping the change (same as OK)
        drawing.change_colors((fg, fg_color))
        palette.clear_overlay()
        color_editor_open = False

    imgui.same_line()

    imgui.color_button(f"Background (#{bg})", *as_float(bg_color), 0, 30, 30)
    
    max_pages = max(0, len(palette.colors) // 64 - 1)
    imgui.push_item_width(100)
    _, current_color_page = imgui.slider_int("Page", state.current_color_page, min_value=0, max_value=max_pages)
    start_color = 64 * current_color_page

    imgui.begin_child("Colors", border=False)
    imgui.push_style_var(imgui.STYLE_ITEM_SPACING, (0, 0))  # Make layout tighter
    width = int(imgui.get_window_content_region_width()) // 20

    imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND, 0, 0, 0)

    colors = palette.colors

    # Order the colors by column instead of by row (which is the order we draw them)
    for i, c in enumerate(chain.from_iterable(zip(range(0, 16), range(16, 32), range(32, 48), range(48, 64)))):
        index = start_color + c
        if index < len(colors):
            color = colors[index]
            is_foreground = index == fg
            is_background = (index == bg) * 2
            selection = is_foreground | is_background
            color = as_float(color)

            if color[3] == 0 or selection:
                x, y = imgui.get_cursor_screen_pos()

            if imgui.color_button(f"color {i}", *color[:3], 1, 0, 25, 25):
                # io = imgui.get_io()
                # if io.key_shift:
                #     if "spread_start" in temp_vars:
                #         temp_vars["spread_end"] = i
                #     else:
                #         temp_vars["spread_start"] = i
                # else:
                fg = index

            draw_list = imgui.get_window_draw_list()            
            if color[3] == 0:
                # Mark transparent color
                draw_list.add_line(x+1, y+1, x+24, y+24, imgui.get_color_u32_rgba(0, 0, 0, 1), 1)
                draw_list.add_line(x+1, y+2, x+23, y+24, imgui.get_color_u32_rgba(1, 1, 1, 1), 1)

            if is_foreground:
                # Mark foregroupd color
                draw_list.add_rect_filled(x+2, y+2, x+10, y+10, imgui.get_color_u32_rgba(1, 1, 1, 1))
                draw_list.add_rect(x+2, y+2, x+10, y+10, imgui.get_color_u32_rgba(0, 0, 0, 1))
            if is_background:
                # Mark background color
                draw_list.add_rect_filled(x+15, y+2, x+23, y+10, imgui.get_color_u32_rgba(0, 0, 0, 1))
                draw_list.add_rect(x+15, y+2, x+23, y+10, imgui.get_color_u32_rgba(1, 1, 1, 1))

            if imgui.core.is_item_clicked(2):
                # Right button sets background
                bg = index

            # Drag and drop (currently does not accomplish anything though)
            if imgui.begin_drag_drop_source():
                imgui.set_drag_drop_payload('start_index', c.to_bytes(1, sys.byteorder))
                imgui.color_button(f"color {c}", *color[:3], 1, 0, 20, 20)
                imgui.end_drag_drop_source()
            if imgui.begin_drag_drop_target():
                start_index = imgui.accept_drag_drop_payload('start_index')
                if start_index is not None:
                    start_index = int.from_bytes(start_index, sys.byteorder)
                    io = imgui.get_io()
                    image_only = io.key_shift
                    drawing.swap_colors(start_index, index, image_only=image_only)
                    palette.clear_overlay()
                imgui.end_drag_drop_target()
        else:
            imgui.color_button(f"no color", 0, 0, 0, 1, 0, 25, 25)

        if i % width != width - 1:
            imgui.same_line()

    imgui.pop_style_color(1)
    imgui.pop_style_var(1)
    imgui.end_child()
    
    imgui.end_child()

    if imgui.is_item_hovered():
        io = imgui.get_io()
        delta = int(io.mouse_wheel)
        current_color_page = min(max(current_color_page - delta, 0), max_pages)

    palette.foreground = fg
    palette.background = bg

    # if "spread_start" in temp_vars and "spread_end" in temp_vars:
    #     spread_start = temp_vars.pop("spread_start")
    #     spread_end = temp_vars.pop("spread_end")
    #     from_index = min(spread_start, spread_end)
    #     to_index = max(spread_start, spread_end)
    #     spread_colors = palette.spread(from_index, to_index)
    #     drawing.change_colors(from_index + 1, spread_colors)

    if any([color_editor_open != state.color_editor_open,
            current_color_page != state.current_color_page]):
        return update_state(state,
                            color_editor_open=color_editor_open,
                            current_color_page=current_color_page)
    return state
    

# edit_color = 0

# def render_palette_popup(state: UIState, drawing: Drawing):

#     # global edit_color
#     # global color_editor_open

#     palette = drawing.palette
#     fg = palette.foreground
#     bg = palette.background
#     fg_color = palette.foreground_color
#     bg_color = palette.background_color
#     open_color_editor = False

#     _, opened = imgui.begin("Color popup", True)

#     imgui.begin_child("Colors", width=0, height=0)

#     imgui.push_style_var(imgui.STYLE_ITEM_SPACING, (0, 0))  # Make layout tighter
#     width = int(imgui.get_window_content_region_width()) // 25

#     for i, color in enumerate(palette, 0):
#         is_foreground = i == fg
#         is_background = (i == bg) * 2
#         selection = is_foreground | is_background
#         if i in palette.overlay:
#             color = as_float(palette.overlay[i])
#         else:
#             color = as_float(color)
#         imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND,
#                                *SELECTABLE_FRAME_COLORS[selection])
#         if imgui.color_button(f"color {i}", *color[:3], 1, 0, 25, 25):
#             # io = imgui.get_io()
#             # if io.key_shift:
#             #     if "spread_start" in temp_vars:
#             #         temp_vars["spread_end"] = i
#             #     else:
#             #         temp_vars["spread_start"] = i
#             # else:
#             fg = i
#         imgui.pop_style_color(1)

#         if imgui.core.is_item_clicked(1):
#             edit_color = i
#             color_editor_open = True
#             imgui.open_popup("Edit foreground color")
#             # imgui.set_next_window_position(w - 115 - 120, 200)

#         if imgui.core.is_item_clicked(2):
#             # Detect right button clicks on the button
#             bg = i

#         if imgui.begin_drag_drop_source():
#             imgui.set_drag_drop_payload('start_index', i.to_bytes(1, sys.byteorder))
#             imgui.color_button(f"color {i}", *color[:3], 1, 0, 20, 20)
#             imgui.end_drag_drop_source()
#         if imgui.begin_drag_drop_target():
#             start_index = imgui.accept_drag_drop_payload('start_index')
#             if start_index is not None:
#                 start_index = int.from_bytes(start_index, sys.byteorder)
#                 io = imgui.get_io()
#                 image_only = io.key_shift
#                 drawing.swap_colors(start_index, i, image_only=image_only)
#                 palette.clear_overlay()
#             imgui.end_drag_drop_target()

#         # if imgui.is_item_hovered():
#         #     io = imgui.get_io()
#         #     delta = int(io.mouse_wheel)

#         if i % width != width - 1:
#             imgui.same_line()

#     imgui.pop_style_var(1)
#     color_editor_open = render_color_editor_popup(drawing, edit_color, color_editor_open)

#     imgui.end_child()
#     imgui.end()

#     palette.foreground = fg
#     palette.background = bg

#     return opened, open_color_editor


# def render_color_editor_popup(drawing, i, still_open):

#     palette = drawing.palette
#     orig_color = palette.colors[i]
#     color = palette.get_color(i)
#     if imgui.begin_popup("Edit foreground color", flags=(imgui.WINDOW_NO_MOVE |
#                                                          imgui.WINDOW_NO_SCROLL_WITH_MOUSE)):
#         done, cancelled, new_color = render_color_editor(palette.colors[i], color)
#         if done and new_color != orig_color:
#             drawing.change_colors(i, [new_color])
#             palette.clear_overlay()
#             still_open = False
#         elif cancelled:
#             palette.clear_overlay()
#             still_open = False
#         else:
#             palette.set_overlay(i, new_color)
#         imgui.end_popup()
#     elif still_open:
#         # The popup was closed by clicking outside, keeping the change (same as OK)
#         drawing.change_colors(i, [color])
#         palette.clear_overlay()
#         still_open = False
#     return still_open


def render_layers(state: UIState, drawing: Drawing):
    
    # imgui.columns(2, "Layers")
    # imgui.set_column_offset(1, 100)
    # if imgui.button("Add"):
    #     drawing.add_layer()
    # if imgui.button("Remove"):
    #     drawing.remove_layer()
    # if imgui.button("Down"):
    #     drawing.move_layer_down()
    # if imgui.button("Up"):
    #     drawing.move_layer_up()

    # imgui.next_column()         

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

    return state


@lru_cache(16)
def _get_brush_preview_size(size):
    w, h = size
    if w > 50 or h > 50:
        aspect = w / h
        if w > h:
            w = 50
            h = w / aspect
        else:
            h = 50
            w = h * aspect
    return w, h


def render_brushes(state, brushes, get_texture, size=None, compact=False):

    clicked = False

    imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND, 1, 1, 1)
    
    for i, brush in enumerate(brushes):
        is_selected = brush == brushes.current
        size1 = size or brush.size
        texture = get_texture(brush=brush, size=size1)
        if texture:
            # w, h = _get_brush_preview_size(brush.size)
            imgui.image(texture.name, *size1,
                        border_color=(1, 1, 1, 1) if is_selected else (.5, .5, .5, 1))
            if imgui.core.is_item_clicked(0):
                clicked = brush

            if i % 3 != 2:
                imgui.same_line()
                
    imgui.pop_style_color()

    imgui.new_line()
    return state, clicked


def render_edits(state: UIState, drawing):

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

    return state


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


def render_tool_menu(state, tools, icons):
    # TODO find out a way to close if user clicks outside the window
    imgui.open_popup("Tools menu")
    if imgui.begin_popup("Tools menu", flags=(imgui.WINDOW_NO_TITLE_BAR
                                              | imgui.WINDOW_NO_RESIZE)):
        done = render_tools(tools, icons)
        if done:
            imgui.core.close_current_popup()
        imgui.end_popup()
    return state


def render_main_menu(state, window):

    w, h = window.get_size()
    drawing = window.drawing if window.drawing and not window.drawing.playing_animation else False
    animation_settings_open = state.animation_settings_open
    
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

            autosaves = drawing and drawing.get_autosaves()
            if imgui.begin_menu("Load autosave...", autosaves):
                t = time()
                for save in autosaves:
                    age = int(t - save.stat().st_mtime)
                    
                    if age > 86400:
                        age_str = f"{age // 86400} days"
                    elif age > 3600:
                        age_str = f"{age // 3600} hours"
                    elif age > 60:
                        age_str = f"{age // 60} minutes"
                    else:
                        age_str = "seconds"
                    clicked, _ = imgui.menu_item(f"{save.name} ({age_str} ago)", None, False, True)
                    if clicked:
                        print("loading", save)
                        drawing.load_ora(save)
                imgui.end_menu()
                
            imgui.separator()

            clicked_save, selected_save = imgui.menu_item("Save", "Ctrl+s", False, window.drawing)
            if clicked_save:
                window.save_drawing()

            clicked_save_as, selected_save = imgui.menu_item("Save as", None, False, window.drawing)
            if clicked_save_as:
                window.save_drawing(ask_for_path=True)

            imgui.separator()

            clicked_quit, _ = imgui.menu_item(
                "Quit", 'Cmd+q', False, True
            )
            if clicked_quit:
                window._quit()

            imgui.end_menu()

        if imgui.begin_menu("Drawing", True):
            if imgui.menu_item("New", None, False, True)[0]:
                size = drawing.size if drawing else (640, 480)
                state = update_state(state, new_drawing_size=size)

            elif imgui.menu_item("Close", None, False, drawing)[0]:
                window._close_drawing()

            imgui.separator()

            if imgui.menu_item("Flip horizontally", None, False, drawing)[0]:
                window.drawing.flip_horizontal()
            if imgui.menu_item("Flip vertically", None, False, drawing)[0]:
                window.drawing.flip_vertical()

            if imgui.menu_item("Crop", None, False, drawing and drawing.selection)[0]:
                window.drawing.crop(window.drawing.selection)
                
            imgui.separator()

            if imgui.menu_item("Undo", "z", False, drawing and drawing.can_undo)[0]:
                window.drawing.undo()
            elif imgui.menu_item("Redo", "y", False, drawing and drawing.can_redo)[0]:
                window.drawing.redo()

            imgui.separator()

            selected = imgui.menu_item("Show selection", "", window.show_selection, drawing)[1]
            window.show_selection = selected

            only_show_current_layer = imgui.menu_item("Only show current layer", "",
                                                      drawing and drawing.only_show_current_layer,
                                                      drawing)[1]
            if window.drawing:
                window.drawing.only_show_current_layer = only_show_current_layer
            imgui.separator()
            
            for i, d in enumerate(window.drawings.items):
                if imgui.menu_item(f"{i+1}: {d.filename} {d.size}",
                                   None, d == drawing, True)[0]:
                    window.drawings.select(d)
            imgui.end_menu()

        if imgui.begin_menu("Layer", bool(drawing)):

            layer = drawing.layers.current
            index = drawing.layers.index(layer)
            n_layers = len(drawing.layers)

            if imgui.menu_item("Add", "l", False, True)[0]:
                drawing.add_layer()
            if imgui.menu_item("Remove", None, False, True)[0]:
                drawing.remove_layer()
            if imgui.menu_item("Merge down", None, False, index > 0)[0]:
                drawing.merge_layer_down()

            if imgui.menu_item("Toggle visibility", "V", False, True)[0]:
                layer.visible = not layer.visible
            if imgui.menu_item("Move up", "W", False, index < n_layers-1)[0]:
                drawing.move_layer_up()
            if imgui.menu_item("Move down", "S", False, index > 0)[0]:
                drawing.move_layer_down()

            imgui.separator()

            if imgui.menu_item("Flip horizontally", None, False, True)[0]:
                drawing.flip_layer_horizontal()
            if imgui.menu_item("Flip vertically", None, False, True)[0]:
                drawing.flip_layer_vertical()
            if imgui.menu_item("Clear", "Delete", False, True)[0]:
                drawing.clear_layer()

            imgui.separator()

            hovered_layer = None
            for i, layer in enumerate(reversed(drawing.layers)):
                selected = drawing.layers.current == layer
                index = n_layers - i - 1
                if imgui.menu_item(f"{index} {'v' if layer.visible else ''}", str(index), selected, True)[1]:
                    drawing.layers.select(layer)
                if imgui.is_item_hovered():
                    hovered_layer = layer

                    imgui.begin_tooltip()
                    texture = window.get_layer_preview_texture(layer,
                                                               colors=drawing.palette.as_tuple())
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

        if imgui.begin_menu("Animation", bool(drawing)):

            if imgui.menu_item("Add frame", None, False, True)[0]:
                drawing.add_frame()
            if imgui.menu_item("Duplicate frame", None, False, True)[0]:
                drawing.add_frame(copy=True)
            if imgui.menu_item("Remove frame", None, False, True)[0]:
                drawing.remove_frame()

            frame = drawing.frame
            if imgui.menu_item("Move frame forward", None, False, frame < drawing.n_frames - 1)[0]:
                drawing.move_frame_forward()
            if imgui.menu_item("Move frame backward", None, False, frame > 0)[0]:
                drawing.move_frame_backward()
                
            imgui.separator()

            if imgui.menu_item("First frame  |<", None, False, True)[0]:
                drawing.first_frame()
            if imgui.menu_item("Last frame  >|", None, False, True)[0]:
                drawing.last_frame()
            
            if imgui.menu_item("Next frame  >", None, False, True)[0]:
                drawing.next_frame()
            if imgui.menu_item("Prev frame  <", None, False, True)[0]:
                drawing.prev_frame()

            if imgui.menu_item("Play  >>", None, False, True)[0]:
                drawing.start_animation()
            if imgui.menu_item("Stop  ||", None, False, True)[0]:
                drawing.stop_animation()

            imgui.separator()

            _, animation_settings_open = imgui.menu_item("Settings", None, state.animation_settings_open, True)
                
            imgui.end_menu()

        if imgui.begin_menu("Brush", drawing):

            if imgui.menu_item("Create from selection", None, False, drawing.selection)[0]:
                drawing.make_brush()

            imgui.separator()
                
            if imgui.menu_item("Flip horizontally", None, False, drawing.brushes.current)[0]:
                window.brush.flip(vertical=False)
                # window.get_brush_preview_texture.cache_clear()

            elif imgui.menu_item("Flip vertically", None, False, drawing.brushes.current)[0]:
                window.brush.flip(vertical=True)

            elif imgui.menu_item("Rotate clockwise", None, False, drawing.brushes.current)[0]:
                window.brush.rotate(1)
                # window.get_brush_preview_texture.cache_clear()

            elif imgui.menu_item("Rotate counter clockwise", None, False, drawing.brushes.current)[0]:
                window.brush.rotate(-1)
                # window.get_brush_preview_texture.cache_clear()

            imgui.separator()

            if imgui.menu_item("Save current", None, False, drawing.brushes.current)[0]:
                fut = window.executor.submit(show_save_dialog,
                                             title="Select file",
                                             filetypes=(
                                                 ("PNG files", "*.png"),
                                                 ("all files", "*.*")))

                def save_brush(fut):
                    path = fut.result()
                    if path:
                        window.add_recent_file(path)
                        window.drawing.brushes.current.save_png(path, drawing.palette.colors)

                fut.add_done_callback(save_brush)

            elif imgui.menu_item("Remove", None, False, drawing.brushes.current)[0]:
                window.drawing.brushes.remove()

            imgui.separator()

            for i, brush in enumerate(reversed(drawing.brushes[-10:])):

                is_selected = drawing.brushes.current == brush

                bw, bh = brush.size
                clicked, selected = imgui.menu_item(f"{bw}x{bh}", None, is_selected, True)

                if selected:
                    drawing.brushes.select(brush)

                if imgui.is_item_hovered():
                    imgui.begin_tooltip()
                    texture = window.get_brush_preview_texture(brush,
                                                               colors=drawing.palette.as_tuple())
                    imgui.image(texture.name, *texture.size, border_color=(.25, .25, .25, 1))
                    imgui.end_tooltip()

            imgui.end_menu()

        if imgui.begin_menu("Info", drawing):
            _, opened = imgui.menu_item("Show edit history", None, window.window_visibility["edits"], True)
            window.window_visibility["edits"] = opened
            imgui.end_menu()

        if imgui.begin_menu("Plugins", drawing):
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

            imgui.set_cursor_screen_pos((w - 350, 0))
            imgui.text(f"Layer: {window.drawing.layers.index()} ")
            imgui.text(f"Zoom: x{2**window.zoom}")
            if drawing.is_animated:
                imgui.text(f"Frame: {drawing.frame + 1}/{drawing.n_frames}")

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

    if animation_settings_open != state.animation_settings_open:
        return update_state(state, animation_settings_open=animation_settings_open)
    return state


def render_animation_settings(state, window):

    drawing = window.drawing
    
    _, opened = imgui.begin("Animation settings", closable=True)
    
    animation_settings_open = opened

    imgui.push_item_width(60)        
    changed, framerate = imgui.drag_int("Framerate", drawing.framerate,
                                        min_value=1, max_value=30)
    if changed:
        drawing.set_framerate(framerate)

    imgui.push_item_width(60)
    changed, time_per_frame = imgui.drag_float("Time per frame", 1 / drawing.framerate,
                                               min_value=0.0333, max_value=1)
    if changed:
        drawing.set_framerate(round(1 / time_per_frame))

    # Layers & frames

    imgui.begin_child("layers_frames", border=True)

    imgui.columns(drawing.n_frames + 1)

    imgui.text("L/F")
    imgui.next_column()

    draw_list = imgui.get_window_draw_list()            
    
    for i in range(drawing.n_frames):
        if i == drawing.frame:
            x, y = imgui.get_cursor_screen_pos()
            draw_list.add_rect_filled(x-10, y-3, x + 30, y + 20, imgui.get_color_u32_rgba(.1, .1, .1, 1))            
        imgui.set_column_offset(i+1, 40 + i*30)
        imgui.text(str(i))

        if imgui.core.is_item_clicked(0):
            drawing.frame = i
        
        imgui.next_column()

    imgui.separator()
    
    for i, layer in reversed(list(enumerate(drawing.layers))):
        imgui.text(str(i))
        imgui.next_column()
        for j in range(drawing.n_frames):
            if j == drawing.frame:
                x, y = imgui.get_cursor_screen_pos()
                draw_list.add_rect_filled(x-10, y-3, x + 30, y + 20,
                                          imgui.get_color_u32_rgba(.2, .2, .2, 1))            
            if layer.frames[j] is not None:
                imgui.text("*")

                if imgui.core.is_item_clicked(0):
                    drawing.frame = i
                
            imgui.next_column()
            
    imgui.end_child()
        
    imgui.end()

    if animation_settings_open != state.animation_settings_open:
        return update_state(state, animation_settings_open=animation_settings_open)
    return state


# TODO Allow configuration
PREDEFINED_SIZES = {
    "Presets": None,
    **{f"{w}, {h}": (w, h)
       for (w, h) in [
               (320, 256),
               (640, 512),
               (800, 600),
               
               (16, 16),
               (32, 32),
               (64, 64),
       ]}
}


def render_new_drawing_popup(state, window):

    "Settings for creating a new drawing."

    size = state.new_drawing_size
    
    if size:
        imgui.open_popup("New drawing")
        w, h = window.get_size()
        imgui.set_next_window_size(300, 140)
        imgui.set_next_window_position(w // 2 - 100, h // 2 - 60)

    if imgui.begin_popup_modal("New drawing")[0]:
        imgui.text("Creating a new drawing.")
        imgui.separator()
        
        changed, new_size = imgui.drag_int2("Shape", *size,
                                            min_value=1, max_value=2048)
        if changed:
            state = update_state(state, new_drawing_size=new_size)

        clicked, current = imgui.combo("##preset shapes", 0, list(PREDEFINED_SIZES.keys()))
        if clicked:
            if current:
                state = update_state(state, new_drawing_size=list(PREDEFINED_SIZES.values())[current])
            
        if imgui.button("OK"):
            window.create_drawing(state.new_drawing_size)
            state = update_state(state, new_drawing_size=None)
            imgui.close_current_popup()
        imgui.same_line()
        if imgui.button("Cancel"):
            state = update_state(state, new_drawing_size=None)
            imgui.close_current_popup()
        imgui.end_popup()

    return state
    
