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
        with imgui.extra.styled(imgui.COLOR_BUTTON, TOOL_BUTTON_COLORS[tool == current_tool]):
            if imgui.core.image_button(texture.name, 16, 16):
                tools.select(tool)
        if i % 4 != 3:
            imgui.same_line()
        #imgui.pop_style_color(1)
    imgui.new_line()


def render_palette(palette):
    imgui.set_next_window_size(270, 400)
    imgui.begin("Palette", True)
    fg = palette.foreground
    bg = palette.background
    #r, g, b, a = palette.get_as_float(fg)
    #_, color = imgui.color_edit3(str(fg), r, g, b)
    r, g, b, a = palette.foreground_color
    imgui.push_item_width(256)
    r_changed, r = imgui.slider_int("R", r, 0, 255)
    g_changed, g = imgui.slider_int("G", g, 0, 255)
    b_changed, b = imgui.slider_int("B", b, 0, 255)
    imgui.pop_item_width()
    if any((r_changed, g_changed, b_changed)):
        palette[fg] = r, g, b, a
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


def render_layers(stack):
    imgui.set_next_window_size(100, 400)

    imgui.begin("Layers", True)
    if imgui.button("Add"):
        stack.add_layer()
    imgui.same_line()
    if imgui.button("Remove"):
        stack.remove_layer()
    if imgui.button("Down"):
        stack.move_layer_down()
    imgui.same_line()
    if imgui.button("Up"):
        stack.move_layer_up()

    imgui.begin_child("Layers", border=True)
    selected = None
    n = len(stack.layers)
    hovered = None
    for i, layer in zip(range(n - 1, -1, -1), reversed(stack.layers)):
        clicked, _ = imgui.checkbox(f"##checkbox{i}", layer.visible)
        if clicked:
            layer.visible = not layer.visible

        imgui.same_line()
        _, selected = imgui.selectable(str(i), layer == stack.current)
        if selected:
            stack.current = layer
        if imgui.is_item_hovered():
            hovered = layer
        # imgui.same_line()
        #texture = get_texture(layer)
        texture = None
        # if texture:
        #     imgui.image(texture.name, 100, 100*texture.aspect,
        #                 border_color=(1, 1, 1, 1) if is_current else (0.5, 0.5, 0.5, 1))
        #     if imgui.core.is_item_clicked(0) and not is_current:
        #         logger.info("selected %r", layer)
        #         selected = layer
    imgui.end_child()
    imgui.end()
    # if selected is not None:
    #     stack.current = selected
    return hovered


def render_brushes(some_brushes, more_brushes, get_texture):
    if imgui.button("Delete"):
        more_brushes.remove()

    imgui.begin_child("brushes", border=True)

    for i, brushes in enumerate([some_brushes, more_brushes]):
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
        imgui.separator()
    imgui.end()
