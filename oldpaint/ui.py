"""
Helper functions for rendering the user interface.
"""

from functools import lru_cache
from itertools import chain
from inspect import isgeneratorfunction
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
from .imgui_pyglet import PygletRenderer
from .plugin import render_plugins_ui
from .rect import Rectangle
from .util import show_save_dialog, throttle


logger = logging.getLogger(__name__)


def stateful(f):

    """
    This decorates a function that is expected to be a generator function. Basically it
    allows the function to be called repeatedly like a normal function, while it actually
    just keeps iterating over the generator.

    This enables a weird idiom which seems pretty useful for imgui use. The idea is that a
    function decorated with this can keep its own state over time, initialized on the first
    call, and then just loop forever or until it's done (the latter useful for dialogs and
    things that have limited lifetime.) The point is that this way we can keep "local" state
    such as open dialogs where appropriate and don't need to keep sending global state around.

    This way, functions that keep state and functions that don't can be used the same.
    """

    assert isgeneratorfunction(f), "Sorry, only accepts generator functions!"

    gen = None

    def inner(*args, **kwargs):
        nonlocal gen
        if not gen:
            gen = f(*args, **kwargs)
            return next(gen)
        try:
            return gen.send(args)
        except StopIteration:
            gen = None  # TODO reinitialize directly instead?
            return False

    return inner


@stateful
def draw_ui(window):

    renderer = PygletRenderer(window)
    io = imgui.get_io()
    font = io.fonts.add_font_from_file_ttf(
        "ttf/Topaznew.ttf", 16, io.fonts.get_glyph_ranges_latin()
    )
    renderer.refresh_font_texture()

    io.config_resize_windows_from_edges = True  # TODO does not seem to work?

    style = imgui.get_style()
    style.window_border_size = 0
    style.window_rounding = 0

    # TODO Keyboard navigation might be nice, at least for dialogs... not quite this easy though.
    io.config_flags |= imgui.CONFIG_NAV_ENABLE_KEYBOARD | imgui.CONFIG_NAV_NO_CAPTURE_KEYBOARD
    io.key_map[imgui.KEY_SPACE] = key.SPACE

    while True:
        imgui.new_frame()
        with imgui.font(font):

            render_main_menu(window)

            if window.drawing:
                w, h = window.get_size()
                imgui.set_next_window_size(115, h - 20)
                imgui.set_next_window_position(w - 115, 20)

                #
                imgui.begin("Right Panel", False, flags=(imgui.WINDOW_NO_TITLE_BAR
                                                   | imgui.WINDOW_NO_RESIZE
                                                   | imgui.WINDOW_NO_MOVE))

                render_tools(window.tools, window.icons)
                imgui.separator()
                render_brushes(window, size=(20, 20))
                imgui.separator()
                render_palette(window)
                render_layers(window.drawing)

                imgui.end()

            if window.selection:
                # Display selection rectangle with handles for tweaking
                imgui.set_next_window_size(w - 115, h - 20)
                imgui.set_next_window_position(0, 20)
                render_selection_rectangle(window)

            render_unsaved_exit(window)

            render_plugins_ui(window)

            if window._error:
                imgui.open_popup("Error")
                if imgui.begin_popup_modal("Error")[0]:
                    imgui.text(window._error)
                    if imgui.button("Doh!"):
                        window._error = None
                        imgui.close_current_popup()
                    imgui.end_popup()

        imgui.render()
        imgui.end_frame()
        renderer.render(imgui.get_draw_data())

        yield


def render_tools(tools, icons):
    current_tool = tools.current
    for i, tool in enumerate(tools):
        texture = icons[tool.tool.name]
        with imgui.colored(imgui.COLOR_BUTTON, *TOOL_BUTTON_COLORS[tool == current_tool]):
            if imgui.image_button(texture.name, 16, 16):
                tools.select(tool)
            if i % 3 != 2:
                imgui.same_line()
        if imgui.is_item_hovered():
            imgui.begin_tooltip()
            imgui.text(tool.tool.name.lower())
            imgui.end_tooltip()


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


@lru_cache(256)
def as_float(color):
    r, g, b, a = color
    return (r/256, g/256, b/256, a/256)


def _change_channel(value, delta):
    return max(0, min(255, value + delta))


def render_color_editor(orig, color):
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


@stateful
def render_palette(window):

    # global color_editor_open  # Need a persistent way to keep track of the popup being closed...
    # global current_color_page

    color_editor_open = False
    current_color_page = 0

    while True:

        imgui.begin_child("Palette", height=460)

        drawing = window.drawing
        palette = drawing.palette
        fg = palette.foreground
        bg = palette.background
        fg_color = palette.foreground_color
        bg_color = palette.background_color

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
            done, cancelled, new_color = render_color_editor(palette.colors[fg], fg_color)
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
        elif color_editor_open:
            # The popup was closed by clicking outside, keeping the change (same as OK)
            drawing.change_colors((fg, fg_color))
            palette.clear_overlay()
            color_editor_open = False

        imgui.same_line()

        imgui.color_button(f"Background (#{bg})", *as_float(bg_color), 0, 30, 30)

        max_pages = max(0, len(palette.colors) // 64 - 1)
        imgui.push_item_width(100)
        _, current_color_page = imgui.slider_int("Page", current_color_page, min_value=0, max_value=max_pages)
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
                color = palette.overlayed_color(index)
                is_foreground = index == fg
                is_background = (index == bg) * 2
                selection = is_foreground | is_background
                color = as_float(color)

                if color[3] == 0 or selection:
                    x, y = imgui.get_cursor_screen_pos()

                if imgui.color_button(f"color {index}", *color[:3], 1, 0, 25, 25):
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

        # if any([color_editor_open != state.color_editor_open,
        #         current_color_page != state.current_color_page]):
        #     # return update_state(state,
        #     #                     color_editor_open=color_editor_open,
        #     #                     current_color_page=current_color_page)

        imgui.end_child()

        yield True
    

def render_layers(drawing: Drawing):
    
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


BRUSH_PREVIEW_PALETTE = ((0, 0, 0, 255),
                         (255, 255, 255, 255))

def render_brushes(window, size=None, compact=False):

    brushes = window.brushes

    imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND, 1, 1, 1)
    
    for i, brush in enumerate(brushes):
        is_selected = brush == brushes.current
        size1 = size or brush.size
        texture = window.get_brush_preview_texture(brush=brush, size=size1, colors=BRUSH_PREVIEW_PALETTE)
        if texture:
            # w, h = _get_brush_preview_size(brush.size)
            imgui.image(texture.name, *size1,
                        border_color=(1, 1, 1, 1) if is_selected else (.5, .5, .5, 1))
            if imgui.core.is_item_clicked(0):
                brushes.select(brush)
                window.drawing.brushes.current = None
            if imgui.is_item_hovered():
                imgui.begin_tooltip()
                imgui.text(f"{type(brush).__name__}")
                imgui.text(f"{brush.size}")
                imgui.image(texture.name, *texture.size, border_color=(.25, .25, .25, 1))
                imgui.end_tooltip()

            if i % 3 != 2:
                imgui.same_line()

    imgui.pop_style_color()

    imgui.new_line()
    return


def render_edits(drawing):

    _, opened = imgui.begin("Edits", closable=True)
    if opened:
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

    return opened


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


@stateful
def render_main_menu(window):

    new_drawing_open = False
    animation_settings_open = False
    show_edit_history = False
    show_metrics = False

    while True:

        w, h = window.get_size()
        drawing = window.drawing if window.drawing and not window.drawing.playing_animation else False
        # animation_settings_open = state.animation_settings_open

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
                            drawing.load_ora(save)
                    imgui.end_menu()

                imgui.separator()

                # Save drawing
                clicked_save, selected_save = imgui.menu_item("Save", "Ctrl+s", False, window.drawing)
                if clicked_save:
                    window.save_drawing()

                clicked_save_as, selected_save = imgui.menu_item("Save as", None, False, window.drawing)
                if clicked_save_as:
                    window.save_drawing(ask_for_path=True)

                imgui.separator()

                # Export drawing
                clicked_export, selected_export = imgui.menu_item("Export", "Ctrl+e", False,
                                                                  window.drawing and window.drawing.export_path)
                if clicked_export:
                    window.export_drawing()

                clicked_export_as, selected_export = imgui.menu_item("Export as", None, False, window.drawing)
                if clicked_export_as:
                    window.export_drawing(ask_for_path=True)

                imgui.separator()

                clicked_quit, _ = imgui.menu_item(
                    "Quit", 'Cmd+q', False, True
                )
                if clicked_quit:
                    window._quit()

                imgui.end_menu()

            if imgui.begin_menu("Drawing", True):
                new_drawing_open = imgui.menu_item("New", None, new_drawing_open, True)[0]

                if drawing and drawing.unsaved:
                    if imgui.begin_menu("Close unsaved...", window.recent_files):
                        clicked, _ = imgui.menu_item("Really? You can't undo this.", None, False, True)
                        if clicked:
                            window.close_drawing(unsaved=True)
                        imgui.menu_item("No way!", None, False, True)
                        imgui.end_menu()
                else:
                    if imgui.menu_item("Close", None, False, drawing)[0]:
                        window.close_drawing()

                imgui.separator()

                if imgui.menu_item("Flip horizontally", None, False, drawing)[0]:
                    window.drawing.flip_horizontal()
                if imgui.menu_item("Flip vertically", None, False, drawing)[0]:
                    window.drawing.flip_vertical()

                if imgui.menu_item("Crop", None, False, False)[0]:
                    window.drawing.crop(window.drawing.selection)

                imgui.separator()

                if imgui.menu_item("Undo", "z", False, drawing and drawing.can_undo)[0]:
                    window.drawing.undo()
                elif imgui.menu_item("Redo", "y", False, drawing and drawing.can_redo)[0]:
                    window.drawing.redo()

                imgui.separator()

                # selected = imgui.menu_item("Show selection", "", window.show_selection, drawing)[1]
                # window.show_selection = selected

                grid = imgui.menu_item("Show grid", "", drawing and drawing.grid, drawing)[1]
                if drawing:
                    drawing.grid = grid
                if imgui.begin_menu("Grid size", drawing and drawing.grid):
                    gw, gh = drawing.grid_size
                    wc, (gw, gh) = imgui.drag_int2("W, H", gw, gh)
                    if gw > 0 and gh > 0:
                        drawing.grid_size = (gw, gh)
                    imgui.end_menu()

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

            if imgui.begin_menu("Palette", bool(drawing)):
                if imgui.menu_item("Add color", None, False, True)[0]:
                    drawing.add_colors([(0, 0, 0, 255)])
                if imgui.menu_item("Insert color", None, False, False)[0]:
                    # TODO Inserting colors also requires shifting all higher colors in the image
                    drawing.add_colors([(0, 0, 0, 255)], drawing.palette.foreground)
                if imgui.menu_item("Remove color", None, False, False)[0]:
                    # TODO Removing colors is a bit more complicated; what to do with pixels using
                    # that color in the image? Clear them? Only allow removing unused colors?
                    drawing.remove_colors(1, drawing.palette.foreground)
                imgui.end_menu()

            if imgui.begin_menu("Layer", bool(drawing)):

                layer = drawing.layers.current
                index = drawing.layers.index(layer)
                n_layers = len(drawing.layers)

                if imgui.menu_item("Add", "l", False, True)[0]:
                    drawing.add_layer()
                elif imgui.menu_item("Remove", None, False, True)[0]:
                    drawing.remove_layer()
                elif imgui.menu_item("Merge down", None, False, index > 0)[0]:
                    drawing.merge_layer_down()

                elif imgui.menu_item("Toggle visibility", "V", False, True)[0]:
                    layer.visible = not layer.visible
                elif imgui.menu_item("Move up", "W", False, index < n_layers-1)[0]:
                    drawing.move_layer_up()
                elif imgui.menu_item("Move down", "S", False, index > 0)[0]:
                    drawing.move_layer_down()

                imgui.separator()

                if imgui.menu_item("Flip horizontally", None, False, True)[0]:
                    drawing.flip_layer_horizontal()
                elif imgui.menu_item("Flip vertically", None, False, True)[0]:
                    drawing.flip_layer_vertical()
                elif imgui.menu_item("Clear", "Delete", False, True)[0]:
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

                animation_settings_open = imgui.menu_item("Settings", None, animation_settings_open, True)[0]

                imgui.end_menu()

            if imgui.begin_menu("Brush", drawing):

                if imgui.menu_item("Create from selection", None, False, drawing.selection)[0]:
                    drawing.make_brush()

                imgui.separator()

                if imgui.menu_item("Flip horizontally", None, False, drawing.brushes.current)[0]:
                    window.brush.flip(vertical=False)
                    window.get_brush_preview_texture.cache_clear()

                elif imgui.menu_item("Flip vertically", None, False, drawing.brushes.current)[0]:
                    window.brush.flip(vertical=True)
                    window.get_brush_preview_texture.cache_clear()

                elif imgui.menu_item("Rotate clockwise", None, False, drawing.brushes.current)[0]:
                    window.brush.rotate(1)
                    window.get_brush_preview_texture.cache_clear()

                elif imgui.menu_item("Rotate counter clockwise", None, False, drawing.brushes.current)[0]:
                    window.brush.rotate(-1)
                    window.get_brush_preview_texture.cache_clear()

                elif imgui.menu_item("Resize", None, False, drawing.brushes.current)[0]:
                    window.brush.resize((20, 30))
                    window.get_brush_preview_texture.cache_clear()

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
                _, show_edit_history = imgui.menu_item("Edit history", None, show_edit_history, True)
                _, show_metrics = imgui.menu_item("ImGui Metrics", None, show_metrics, True)
                imgui.end_menu()

            if imgui.begin_menu("Plugins", drawing):
                active_plugins = window.drawing.active_plugins
                for name, plugin in window.plugins.items():
                    is_active = name in active_plugins
                    clicked, selected = imgui.menu_item(name, None, is_active, True)
                    if clicked and selected:
                        active_plugins[name] = {}
                    elif not selected and is_active:
                        del active_plugins[name]
                imgui.separator()
                if imgui.menu_item("Clear", None, False, True)[0]:
                    active_plugins.clear()
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
                    x, y = window.to_image_coords(*window.mouse_position)
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

            if new_drawing_open:
                new_drawing_open = render_new_drawing_popup(window)

            if animation_settings_open:
                animation_settings_open = render_animation_settings(window)

            if show_edit_history:
                show_edit_history = render_edits(window.drawing)

            yield

    # if animation_settings_open != state.animation_settings_open:
    #     return update_state(state, animation_settings_open=animation_settings_open)
    # return state


@stateful
def render_animation_settings(window):

    opened = True

    while opened:

        drawing = window.drawing

        _, opened = imgui.begin("Animation settings", closable=True)

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

        yield True


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


@stateful
def render_new_drawing_popup(window):

    "Settings for creating a new drawing."

    drawing = window.drawing
    size = drawing.size if drawing else (640, 480)

    done = False
    while not done:

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
                size = new_size

            clicked, current = imgui.combo("##preset shapes", 0, list(PREDEFINED_SIZES.keys()))
            if clicked:
                if current:
                    size = list(PREDEFINED_SIZES.values())[current]

            if imgui.button("OK"):
                window.create_drawing(size)
                imgui.close_current_popup()
                done = True
            imgui.same_line()
            if imgui.button("Cancel"):
                imgui.close_current_popup()
                done = True
            imgui.end_popup()

        yield True


@stateful
def render_selection_rectangle(window):

    original_selection = None
    selection_corner_dragged = None

    while True:

        rectangle = window.drawing.selection
        if rectangle:
            w, h = window.get_pixel_aligned_size()
            x0, y0, x1, y1 = rectangle.box()

            tl_x, tl_y = window.to_window_coords(x0, y0)
            tr_x, tr_y = window.to_window_coords(x1, y0)
            bl_x, bl_y = window.to_window_coords(x0, y1)
            br_x, br_y = window.to_window_coords(x1, y1)
            # ...

            imgui.set_next_window_bg_alpha(0)
            # imgui.set_next_window_position(0, 0)
            # imgui.set_next_window_size(w, h)

            imgui.begin("Selection", False, flags=(imgui.WINDOW_NO_TITLE_BAR
                                                   | imgui.WINDOW_NO_RESIZE
                                                   | imgui.WINDOW_NO_MOVE
                                                   | imgui.WINDOW_NO_FOCUS_ON_APPEARING))
            io = imgui.get_io()
            left_mouse = io.mouse_down[0]
            handle_size = 10

            with imgui.colored(imgui.COLOR_FRAME_BACKGROUND, 1, 1, 1):

                imgui.set_cursor_screen_pos((int(tl_x - handle_size), int(h - tl_y - handle_size)))
                imgui.button("##topleft", width=handle_size, height=handle_size)
                if imgui.is_item_clicked():
                    original_selection = rectangle
                    selection_corner_dragged = "topleft"

                imgui.set_cursor_screen_pos((int(tr_x), int(h - tr_y - handle_size)))
                imgui.button("##topright", width=handle_size, height=handle_size)
                if imgui.is_item_clicked():
                    original_selection = rectangle
                    selection_corner_dragged = "topright"

                imgui.set_cursor_screen_pos((int(bl_x - handle_size), int(h - bl_y)))
                imgui.button("##bottomleft", width=handle_size, height=handle_size)
                if imgui.is_item_clicked():
                    original_selection = rectangle
                    selection_corner_dragged = "bottomleft"

                imgui.set_cursor_screen_pos((int(br_x), int(h - br_y)))
                imgui.button("##bottomright", width=handle_size, height=handle_size)
                if imgui.is_item_clicked():
                    original_selection = rectangle
                    selection_corner_dragged = "bottomright"

            imgui.set_cursor_screen_pos((tl_x, h-tl_y))
            imgui.invisible_button("center", width=int(tr_x - tl_x), height=int(tl_y - bl_y))
            if imgui.is_item_clicked():
                original_selection = rectangle
                selection_corner_dragged = "center"

            imgui.set_cursor_screen_pos((0, 0))
            ww, wh = imgui.get_window_size()
            if imgui.invisible_button("backdrop", width=ww, height=wh):
                window.drawing.selection = None
                original_selection = None
                selection_corner_dragged = None

            scale = window.scale
            orig = original_selection
            dx, dy = imgui.get_mouse_drag_delta()

            if left_mouse:
                if selection_corner_dragged == "center":
                    if dx or dy:
                        window.drawing.selection = Rectangle((orig.x + round(dx / scale), orig.y + round(dy / scale)),
                                                             (orig.width, orig.height))

                elif selection_corner_dragged == "topleft":
                    if dx or dy:
                        window.drawing.selection = Rectangle((orig.x + round(dx / scale), orig.y + round(dy / scale)),
                                                             (orig.width - round(dx / scale), orig.height - round(dy / scale)))
                elif selection_corner_dragged == "topright":
                    if dx or dy:
                        window.drawing.selection = Rectangle((orig.x, orig.y + round(dy / scale)),
                                                             (orig.width + round(dx / scale), orig.height - round(dy / scale)))
                elif selection_corner_dragged == "bottomleft":
                    if dx or dy:
                        window.drawing.selection = Rectangle((orig.x + round(dx / scale), orig.y),
                                                             (orig.width - round(dx / scale), orig.height + round(dy / scale)))
                elif selection_corner_dragged == "bottomright":
                    if dx or dy:
                        window.drawing.selection = Rectangle(orig.position,
                                                             (orig.width + round(dx / scale), orig.height + round(dy / scale)))
            else:
                # User is doing stateful else, let's allow e.g. zooming and panning.
                selection_corner_dragged = None
                imgui.capture_mouse_from_app(False)

            # imgui.set_cursor_screen_pos((tr_x-4, h-tr_y-4))
            # imgui.color_button("##topright", r=1, g=0, b=0, width=10, height=10)

            # io = imgui.get_io()
            # left_mouse = io.mouse_down[0]
            # if imgui.is_item_hovered() and left_mouse:
            #     if not state.original_selection:
            #         state = update_state(state, original_selection=rectangle)
            #     else:
            #         dx, dy = imgui.get_mouse_drag_delta()
            #         if dx != 0 or dy != 0:
            #             orig = state.original_selection
            #             window.drawing.selection = Rectangle((orig.x, orig.y + dx),
            #                                                  (orig.width + int(dx), orig.height + int(dy)))

            imgui.end()

        yield
