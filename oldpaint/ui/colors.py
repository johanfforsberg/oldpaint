from functools import lru_cache
from itertools import chain
import sys

import imgui

from ..util import stateful


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


class PaletteColors:

    def __init__(self, size=(24, 24)):
        self.size = size
        self.color_editor_open = False
        self.current_color_page = 0
        self.spread_start = None
        self.spread_end = None

    def render(self, window, pages=4):

        # global color_editor_open  # Need a persistent way to keep track of the popup being closed...
        # global current_color_page

        page_size = 256 // pages
        
        imgui.begin_child("Palette", height=460)

        drawing = window.drawing
        palette = drawing.palette
        fg = palette.foreground
        bg = palette.background
        fg_color = palette.foreground_color
        bg_color = palette.background_color
        color_width, color_height = self.size

        imgui.begin_child("Palette", border=False, height=460)
        # Edit foreground color
        if imgui.color_button(f"Foreground (#{fg})", *as_float(fg_color), 0, 30, 30):
            io = imgui.get_io()
            w, h = io.display_size
            imgui.open_popup("Edit foreground color")
            imgui.set_next_window_position(w - 115 - 120, 200)
            self.color_editor_open = True
        if imgui.begin_popup("Edit foreground color", flags=(imgui.WINDOW_NO_MOVE |
                                                             imgui.WINDOW_NO_SCROLL_WITH_MOUSE)):
            done, cancelled, new_color = render_color_editor(palette.colors[fg], fg_color)
            if done:
                # Color was changed and then OK was clicked; make change and close
                drawing.change_colors((fg, new_color))
                palette.clear_overlay()
                self.color_editor_open = False
            elif cancelled:
                # Cancel was clicked; disregard any changes and close
                palette.clear_overlay()
                self.color_editor_open = False
            else:
                # Keep editing color
                palette.set_overlay(fg, new_color)

            imgui.end_popup()
        elif self.color_editor_open:
            # The popup was closed by clicking outside, keeping the change (same as OK)
            drawing.change_colors((fg, fg_color))
            palette.clear_overlay()
            self.color_editor_open = False

        imgui.same_line()

        imgui.color_button(f"Background (#{bg})", *as_float(bg_color), 0, 30, 30)

        if pages > 1:
            max_pages = max(0, len(palette.colors) // page_size - 1)
            imgui.push_item_width(100)
            _, self.current_color_page = imgui.slider_int("Page", self.current_color_page, min_value=0, max_value=max_pages)
            start_color = page_size * self.current_color_page
        else:
            start_color = 0

        imgui.begin_child("Colors", border=False)
        imgui.push_style_var(imgui.STYLE_ITEM_SPACING, (0, 0))  # Make layout tighter
        width = int(imgui.get_window_content_region_width()) // color_width

        imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND, 0, 0, 0)

        colors = palette.colors

        # Order the colors by column instead of by row (which is the order we draw them)
        ranges = (range(i * 16,  (i + 1) * 16) for i in range(16 // pages))
        for i, c in enumerate(chain.from_iterable(zip(*ranges))):
            index = start_color + c
            if index < len(colors):
                color = palette.overlayed_color(index)
                color = as_float(color)

                is_foreground = index == fg
                is_background = (index == bg) * 2
                selection = is_foreground | is_background
                # spreading = self.spread_start is not None and self.spread_end is not None
                # is_spread_start = self.spread_start is not None

                if color[3] == 0 or selection:
                    x, y = imgui.get_cursor_screen_pos()

                if imgui.color_button(f"color {index}", *color[:3], 1, 0, color_width, color_height):
                    io = imgui.get_io()
                    if io.key_shift:
                        if self.spread_start is not None:
                            self.spread_end = index
                        else:
                            self.spread_start = index
                    else:
                        fg = index

                # Right button sets background
                if imgui.core.is_item_clicked(2):
                    bg = index                        
                    
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

            if width > 0 and i % width != width - 1:
                imgui.same_line()

        imgui.pop_style_color(1)
        imgui.pop_style_var(1)
        imgui.end_child()

        imgui.end_child()

        if pages > 1:
            if imgui.is_item_hovered():
                io = imgui.get_io()
                delta = int(io.mouse_wheel)
                self.current_color_page = min(max(self.current_color_page - delta, 0), max_pages)

        palette.foreground = fg
        palette.background = bg

        if self.spread_start is not None and self.spread_end is not None:
            from_index = min(self.spread_start, self.spread_end)
            to_index = max(self.spread_start, self.spread_end)
            spread_colors = palette.spread(from_index, to_index)
            drawing.change_colors(*zip(range(from_index + 1, to_index), spread_colors))
            self.spread_start = self.spread_end = None

        # if any([color_editor_open != state.color_editor_open,
        #         current_color_page != state.current_color_page]):
        #     # return update_state(state,
        #     #                     color_editor_open=color_editor_open,
        #     #                     current_color_page=current_color_page)

        imgui.end_child()
