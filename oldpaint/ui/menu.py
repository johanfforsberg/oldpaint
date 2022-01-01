import imgui
import os
from time import time

from ..brush import BUILTIN_BRUSH_TYPES
from ..drawing import Drawing
from ..palette import get_builtin_palettes, get_custom_palettes, Palette
from ..util import stateful


@stateful
def render_main_menu(window):

    print("rebder_main_mebny")

    new_drawing_size = (320, 256)
    animation_settings_open = False
    show_edit_history = False
    show_metrics = False
    new_drawing_palette = 0

    while True:

        w, h = window.get_size()
        drawing = window.drawing  # if window.drawing and not window.drawing.playing_animation else False
        # animation_settings_open = state.animation_settings_open

        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File", True):

                clicked_load, selected_load = imgui.menu_item("Load", "o", False, True)
                if clicked_load:
                    # window.load_drawing()
                    imgui.end_menu()
                    imgui.end_main_menu_bar()
                    yield "load-drawing"
                    continue

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
                    # window.save_drawing(ask_for_path=True)
                    imgui.end_menu()
                    imgui.end_main_menu_bar()
                    yield "save-drawing"
                    continue

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

                if imgui.begin_menu("New", True):
                    _, new_drawing_size = imgui.drag_int2("Size", *new_drawing_size,
                                                          min_value=1, max_value=2048)

                    clicked, current = imgui.combo("##preset shapes", 0, list(Drawing.PREDEFINED_SIZES.keys()))
                    if clicked and current:
                        new_drawing_size = list(Drawing.PREDEFINED_SIZES.values())[current]

                    builtin_palettes = get_builtin_palettes()
                    custom_palettes = get_custom_palettes()
                    palettes = builtin_palettes + custom_palettes
                    palette_names = [p.stem for p in palettes]
                    clicked, new_drawing_palette = imgui.combo("Palette", new_drawing_palette, palette_names)

                    if imgui.button("OK"):
                        palette = Palette.from_file(palettes[new_drawing_palette])
                        window.create_drawing(new_drawing_size, palette)
                    imgui.same_line()
                    if imgui.button("Cancel"):
                        imgui.close_current_popup()

                    imgui.end_menu()

                if imgui.menu_item("Clone", None, False, drawing)[0]:
                    window.clone_drawing()

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

                grid = imgui.menu_item("Use grid", "", drawing and drawing.grid, drawing)[1]
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
                if imgui.menu_item("Add color", None, False, len(drawing.palette) < 256)[0]:
                    drawing.add_colors([(0, 0, 0, 255)])
                if imgui.menu_item("Insert color", None, False, False)[0]:
                    # TODO Inserting colors also requires shifting all higher colors in the image
                    drawing.add_colors([(0, 0, 0, 255)], drawing.palette.foreground)
                if imgui.menu_item("Remove color", None, False, False)[0]:
                    # TODO Removing colors is a bit more complicated; what to do with pixels using
                    # that color in the image? Clear them? Only allow removing unused colors?
                    drawing.remove_colors(1, drawing.palette.foreground)
                imgui.separator()
                if imgui.menu_item("Export as JSON", None, False, drawing)[0]:
                    window.export_palette()
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

            if imgui.begin_menu("Animation", drawing is not None):

                if imgui.menu_item("Add frame", None, False, not drawing.locked)[0]:
                    drawing.add_frame()
                if imgui.menu_item("Duplicate frame", None, False, not drawing.locked)[0]:
                    drawing.add_frame(copy=True)
                if imgui.menu_item("Remove frame", None, False, not drawing.locked)[0]:
                    drawing.remove_frame()

                frame = drawing.frame
                if imgui.menu_item("Move frame forward", None, False, not drawing.locked and frame < drawing.n_frames - 1)[0]:
                    drawing.move_frame_forward()
                if imgui.menu_item("Move frame backward", None, False, not drawing.locked and frame > 0)[0]:
                    drawing.move_frame_backward()

                imgui.separator()

                if imgui.menu_item("First frame  |<", None, False, not drawing.playing_animation)[0]:
                    drawing.first_frame()
                if imgui.menu_item("Last frame  >|", None, False, not drawing.playing_animation)[0]:
                    drawing.last_frame()

                if imgui.menu_item("Next frame  >", None, False, not drawing.playing_animation)[0]:
                    drawing.next_frame()
                if imgui.menu_item("Prev frame  <", None, False, not drawing.playing_animation)[0]:
                    drawing.prev_frame()

                if imgui.menu_item("Play  >>", None, False, not drawing.playing_animation)[0]:
                    drawing.start_animation()
                if imgui.menu_item("Stop  ||", None, False, drawing.playing_animation)[0]:
                    drawing.stop_animation()

                imgui.separator()

                clicked, state = imgui.menu_item("Settings", None, animation_settings_open, True)
                if clicked:
                    animation_settings_open = state

                imgui.end_menu()

            if imgui.begin_menu("Tool", drawing):
                for tool in window.tools:
                    if imgui.menu_item(tool.tool.name, None, tool == window.tools.current)[0]:
                        window.tools.select(tool)
                imgui.separator()

                if imgui.begin_menu("Configure..."):
                    tool = window.tools.current
                    params = tool.get_config_params()
                    if params:
                        imgui.text(tool.tool.name)
                        for name, (type_, slc), value in params:
                            if type_ is int:
                                changed, value = imgui.slider_int(name, value, slc.start, slc.stop)
                            elif type_ is float:
                                changed, value = imgui.slider_float(name, value, slc.start, slc.stop)
                            if changed:
                                setattr(tool, name, value)
                    else:
                        imgui.text(f"{tool.tool.name} has no options!")
                    imgui.end_menu()

                imgui.end_menu()

            if imgui.begin_menu("Brush", drawing):

                if imgui.begin_menu("Configure default...", window.brushes):
                    changed, new_index = imgui.combo("brush type", window.brushes.index(),
                                                     [b.name for b in BUILTIN_BRUSH_TYPES])
                    if changed:
                        new_type = BUILTIN_BRUSH_TYPES[new_index]
                        window.brushes.set_item(new_type())

                    brush = window.brushes.get_current()
                    any_changed = False
                    args = {}
                    for name, param in brush.get_params().items():
                        if name == "self":
                            continue
                        if param.annotation is int:
                            changed, value = imgui.slider_int(name, getattr(brush, name), param.default, 100)
                            if changed:
                                args[name] = value
                                any_changed = True
                            else:
                                args[name] = getattr(brush, name)
                    if any_changed:
                        window.brushes.set_item(type(brush)(**args))

                    imgui.end_menu()

                if imgui.menu_item("Create from selection", "b", False, drawing.selection)[0]:
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
                    imgui.end_menu()
                    imgui.end_main_menu_bar()
                    yield "save-brush"
                    continue

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
                        w, h = texture.size
                        imgui.image(texture.name, w*2, h*2, border_color=(.25, .25, .25, 1))
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

            # if new_drawing_open:
            #     new_drawing_open = render_new_drawing_popup(window)

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
