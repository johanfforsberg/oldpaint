"""
Helper functions for rendering the user interface.
"""

import logging

import imgui

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
    for i, tool in enumerate(tools):
        texture = icons[tool.tool]
        #imgui.push_style_color(imgui.COLOR_BUTTON, *TOOL_BUTTON_COLORS[tool == current_tool])
        #with imgui.extra.styled(imgui.COLOR_BUTTON_ACTIVE, TOOL_BUTTON_COLORS[tool == current_tool]):
        if imgui.core.image_button(texture.name, 16, 16):
            tools.select(tool)
        if i % 4 != 3:
            imgui.same_line()
        #imgui.pop_style_color(1)
    imgui.new_line()


def render_palette(palette):
    #imgui.set_next_window_size(270, 400)
    imgui.begin("Palette", True)
    fg = palette.foreground
    bg = palette.background
    changed, color = imgui.drag_int4("RGB", *palette.foreground_color,
                                     min_value=0, max_value=255)
    if changed:
        palette[fg] = color
    imgui.begin_child("Palette", border=True)
    imgui.push_style_var(imgui.STYLE_ITEM_SPACING, (0, 0))  # Make layout tighter
    width = int(imgui.get_window_content_region_width()) // 20
    for i, color in enumerate(palette):
        is_foreground = i == fg
        is_background = (i == bg) * 2
        selection = is_foreground | is_background
        imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND, *SELECTABLE_FRAME_COLORS[selection])

        if imgui.color_button(f"color {i}", *color[:3], 1, 0, 20, 20):
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
