"""
Helper functions for rendering the user interface.
"""

import logging

import imgui
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
    for i, tool in enumerate(tools):
        texture = icons[tool.tool]
        # imgui.push_style_color(imgui.COLOR_BUTTON,
        #                        *TOOL_BUTTON_COLORS[tool == current_tool])
        # with imgui.extra.styled(imgui.COLOR_BUTTON_ACTIVE, TOOL_BUTTON_COLORS[tool == current_tool]):
        # with imgui.colored(imgui.BUTTON_FRAME_BACKGROUND,
        #                    *TOOL_BUTTON_COLORS[tool == current_tool]):
        if imgui.core.image_button(texture.name, 16, 16, border_color=(*TOOL_BUTTON_COLORS[tool == current_tool], 1)):
            tools.select(tool)
        if i % 4 != 3:
            imgui.same_line()
        # imgui.pop_style_color(1)
    imgui.new_line()


def render_palette(drawing):
    #imgui.set_next_window_size(270, 400)

    palette = drawing.palette

    io = imgui.get_io()

    imgui.begin("Palette", True)
    fg = palette.foreground
    bg = palette.background
    fg_color = palette.foreground_color
    changed, color = imgui.drag_int4("RGBA", *fg_color, change_speed=0.1,
                                     min_value=0, max_value=255)
    if changed:
        if "palette_fg_change_start" not in temp_vars and imgui.is_mouse_dragging():
            temp_vars["palette_fg_change_start"] = fg_color
        # TODO there should be an "overlay" here too, so that we don't need to
        # change the actual palette data in real time.
        palette[fg] = color

    if "palette_fg_change_start" in temp_vars and not imgui.is_mouse_dragging():
        orig_fg_color = temp_vars.pop("palette_fg_change_start")
        print("color edited", fg, orig_fg_color, color)
        drawing.change_color(fg, orig_fg_color, color)

    palette_sizes = [8, 16, 32, 64, 128, 256]
    imgui.same_line()
    imgui.text(f"  #: {palette.size}")
    if imgui.begin_popup_context_item("#Colors", mouse_button=0):
        for size in palette_sizes:
            _, selected = imgui.selectable(str(size), size == palette.size)
            if selected:
                palette.size = size
        imgui.end_popup()

    imgui.begin_child("Palette", border=True)
    imgui.push_style_var(imgui.STYLE_ITEM_SPACING, (0, 0))  # Make layout tighter
    width = int(imgui.get_window_content_region_width()) // 20
    spread_start = temp_vars.get("spread_start")
    for i, color in enumerate(palette):
        is_foreground = i == fg
        is_background = (i == bg) * 2
        selection = is_foreground | is_background
        imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND,
                               *SELECTABLE_FRAME_COLORS[selection])
        if imgui.color_button(f"color {i}", *color[:3], 1, 0, 20, 20):
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
    imgui.end()

    palette.foreground = fg
    palette.background = bg

    if "spread_start" in temp_vars and "spread_end" in temp_vars:
        spread_start = temp_vars.pop("spread_start")
        spread_end = temp_vars.pop("spread_end")
        palette.spread(spread_start, spread_end)


# TODO Consider using https://github.com/mlabbe/nativefiledialog instead of the following?

def render_open_file_dialog(loader):
    imgui.begin("File list", True)
    imgui.text(loader.path)
    imgui.text(loader.input)
    if imgui.button("Load"):
        loader.finish()
    imgui.begin_child("Dir", border=True)
    listing = loader.get_alternatives()
    for item in listing:
        _, sel = imgui.selectable(item, False)
        if sel:
            loader.select(item)
    imgui.end_child()
    imgui.end()


def render_save_file_dialog(loader):
    imgui.begin("File list", True)
    imgui.text(loader.path)
    changed, loader.input = imgui.input_text("Filename:", loader.input, 100)
    if imgui.button("Save"):
        loader.finish()
    imgui.begin_child("Dir", border=True)
    listing = loader.get_alternatives()
    for item in listing:
        _, sel = imgui.selectable(item, False)
        if sel:
            loader.input = item
    imgui.end_child()
    imgui.end()


def render_layers(drawing):
    imgui.set_next_window_size(100, 400)

    imgui.begin("Layers", True)
    if imgui.button("Add"):
        drawing.add_layer()
    imgui.same_line()
    if imgui.button("Remove"):
        drawing.remove_layer()
    if imgui.button("Down"):
        drawing.move_layer_down()
    imgui.same_line()
    if imgui.button("Up"):
        drawing.move_layer_up()

    imgui.begin_child("Layers", border=True)
    selected = None
    n = len(drawing.layers)
    hovered = None
    imgui.columns(2, 'layerlist')
    imgui.text("#")
    imgui.set_column_offset(1, 40)
    imgui.next_column()
    imgui.text("Show")
    imgui.next_column()
    imgui.separator()

    for i, layer in zip(range(n - 1, -1, -1), reversed(drawing.layers)):
        _, selected = imgui.selectable(str(i), layer == drawing.current,
                                       imgui.SELECTABLE_SPAN_ALL_COLUMNS)
        if selected:
            drawing.layers.current = layer
        if imgui.is_item_hovered():
            hovered = layer
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
    imgui.end()
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

    imgui.begin("Edits", True)

    imgui.columns(2, 'layerlist')
    imgui.text("#")
    imgui.set_column_offset(1, 40)
    imgui.next_column()
    imgui.text("Type")
    imgui.next_column()
    imgui.separator()
    n = len(drawing.edits)
    for i, edit in enumerate(reversed(drawing.edits)):
        imgui.text(str(n - i))
        imgui.next_column()
        imgui.text(str(type(edit).__name__))
        imgui.next_column()
    imgui.end()
