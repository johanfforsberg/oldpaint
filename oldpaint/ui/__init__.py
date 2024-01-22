"""
Helper functions for rendering the user interface.
"""

from functools import lru_cache
import logging
from math import floor, ceil
import os
import sys
from time import time
from typing import Tuple, NamedTuple
from importlib import resources as impresources

import imgui
import pyglet
from pyglet.window import key

from ..brush import BUILTIN_BRUSH_TYPES
from ..drawing import Drawing
from ..imgui_pyglet import PygletRenderer
from ..palette import get_builtin_palettes, get_custom_palettes, Palette
from ..plugin import render_plugins_ui
from ..rect import Rectangle
from ..util import show_save_dialog, throttle, stateful

from .file_browser import render_file_browser
from .colors import PaletteColors
from .menu import MainMenu
from .. import ttf


logger = logging.getLogger(__name__)


class UI:

    def __init__(self, window):

        self.renderer = PygletRenderer(window)
        io = imgui.get_io()
        #config = imgui.core.FontConfig(merge_mode=True)
        self.font = io.fonts.add_font_from_file_ttf(
            str(impresources.files(ttf) / "Topaznew.ttf"), 16, glyph_ranges=io.fonts.get_glyph_ranges_latin()
        )
        self.renderer.refresh_font_texture()

        # io.config_resize_windows_from_edges = True  # TODO does not seem to work?

        style = imgui.get_style()
        style.window_border_size = 0
        style.window_rounding = 0

        # TODO Keyboard navigation might be nice, at least for dialogs... not quite this easy though.
        io.config_flags |= imgui.CONFIG_NAV_ENABLE_KEYBOARD | imgui.CONFIG_NAV_NO_CAPTURE_KEYBOARD
        io.key_map[imgui.KEY_SPACE] = key.SPACE

        self.main_menu = MainMenu()
        self.palette_colors = PaletteColors()

    def render(self, window):
        imgui.new_frame()
        with imgui.font(self.font):

            popup = self.main_menu.render(window)
            if popup:
                imgui.set_next_window_size(600, 500)
                imgui.open_popup(popup)

            file_to_load = render_file_browser(window, "load-drawing")
            if file_to_load is not None:
                window.load_drawing(file_to_load)

            file_to_import = render_file_browser(window, "import-png")
            if file_to_import is not None:
                window.import_png(file_to_import)

            file_to_save = render_file_browser(window, "save-drawing", edit_filename=True)
            if file_to_save:
                window.save_drawing(path=file_to_save)

            file_to_save_brush = render_file_browser(window, "save-brush", edit_filename=True)
            if file_to_save_brush:
                window.drawing.brushes.current.save_png(file_to_save_brush, window.drawing.palette.colors)
                window.add_recent_file(file_to_save_brush)

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
                self.palette_colors.render(window)
                render_layers(window)

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
        self.renderer.render(imgui.get_draw_data())


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


@stateful
def render_layers(window):

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

    mouseover = False

    while True:

        drawing = window.drawing

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
                drawing.current = layer
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

        if hovered:
            window.highlighted_layer = hovered
            mouseover = True
        elif mouseover:
            window.highlighted_layer = None
            mouseover = False
        else:
            mouseover = False

        imgui.columns(1)
        imgui.end_child()
        imgui.end_child()

        yield True


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
        is_selected = brush == brushes.current and not window.drawing.brushes.current
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


def render_unsaved_exit(window):

    if window.unsaved_drawings:
        imgui.open_popup("Really exit?")

    imgui.set_next_window_size(500, 200)
    if imgui.begin_popup_modal("Really exit?")[0]:
        imgui.text("You have unsaved work in these drawing(s):")

        imgui.begin_child("unsaved", border=True, height=-26)
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
