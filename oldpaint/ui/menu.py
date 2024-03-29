from contextlib import contextmanager
import inspect
import imgui
import os
from time import time

from ..brush import BUILTIN_BRUSH_TYPES
from ..drawing import Drawing
from ..palette import get_builtin_palettes, get_custom_palettes, Palette
from ..plugin import activate_plugin
from ..util import stateful


@contextmanager
def ending(started, end_function):
    yield started
    if started:
        end_function()


class MainMenu:

    def __init__(self):

        self.new_drawing_size = (320, 256)
        self.show_edit_history = False
        self.show_metrics = False
        self.new_drawing_palette = 0

    def render(self, window):

        w, h = window.get_size()
        drawing = window.drawing 

        popup = None

        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File", True):
                clicked_load, selected_load = imgui.menu_item("Load", "o", False, True)
                if clicked_load:
                    popup = "load-drawing"

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
                    popup = "save-drawing"

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

                # Import image
                clicked_import, selected_import = imgui.menu_item("Import PNG", None, False,
                                                                  window.drawing)
                if clicked_import:
                    popup = "import-png"

                imgui.separator()

                clicked_quit, _ = imgui.menu_item(
                    "Quit", 'Cmd+q', False, True
                )
                if clicked_quit:
                    window._quit()

                imgui.end_menu()

            if imgui.begin_menu("Drawing", True):

                if imgui.begin_menu("New", True):
                    _, self.new_drawing_size = imgui.drag_int2(
                        "Size", *self.new_drawing_size,
                        min_value=1, max_value=2048)

                    clicked, current = imgui.combo(
                        "##preset shapes", 0, list(Drawing.PREDEFINED_SIZES.keys()))
                    if clicked and current:
                        self.new_drawing_size = list(Drawing.PREDEFINED_SIZES.values())[current]

                    builtin_palettes = get_builtin_palettes()
                    custom_palettes = get_custom_palettes()
                    palettes = builtin_palettes + custom_palettes
                    palette_names = [p.stem for p in palettes]
                    clicked, self.new_drawing_palette = imgui.combo(
                        "Palette", self.new_drawing_palette, palette_names)

                    if imgui.button("OK"):
                        palette = Palette.from_file(palettes[self.new_drawing_palette])
                        window.create_drawing(self.new_drawing_size, palette)
                        imgui.close_current_popup()
                    imgui.same_line()
                    if imgui.button("Cancel"):
                        imgui.close_current_popup()

                    imgui.end_menu()

                if imgui.menu_item("Clone", None, False, drawing)[0]:
                    window.clone_drawing()

                if drawing and drawing.unsaved:
                    if imgui.begin_menu("Close unsaved...", window.recent_files):
                        clicked, _ = imgui.menu_item("Really? You can't undo this.",
                                                     None, False, True)
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

                layer = drawing.current
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
                if imgui.begin_menu("Alpha...", True):
                    changed, new_alpha = imgui.slider_float("Alpha value", layer.alpha,
                                                            # change_speed=0.01,
                                                            min_value=0, max_value=1)
                    if changed:
                        layer.alpha = new_alpha
                    imgui.end_menu()
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
                    selected = drawing.current == layer
                    index = n_layers - i - 1
                    if imgui.menu_item(f"{index} {'v' if layer.visible else ''}", str(index), selected, True)[1]:
                        drawing.current = layer
                    if imgui.is_item_hovered():
                        hovered_layer = layer

                        imgui.begin_tooltip()
                        texture = window.get_layer_preview_texture(layer,
                                                                   colors=drawing.palette.as_tuple())
                        lw, lh = texture.size
                        imgui.image(texture.name, lw, lh, border_color=(.25, .25, .25, 1))
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

                if imgui.begin_menu("Settings...", True):
                    render_animation_settings(window)
                    imgui.end_menu()

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
                            pass
                        elif param.annotation is int:
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
                    w, h = window.brush.size
                    window.brush.resize((w//2.5, h//2.5))
                    window.get_brush_preview_texture.cache_clear()

                imgui.separator()

                if imgui.menu_item("Save current", None, False, drawing.brushes.current)[0]:
                    popup = "save-brush"

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
                _, self.show_edit_history = imgui.menu_item("Edit history", None, self.show_edit_history, True)
                _, self.show_metrics = imgui.menu_item("ImGui Metrics", None, self.show_metrics, True)
                # if imgui.begin_menu("Backup", drawing):
                #     imgui.image(texture.name, w*2, h*2, border_color=(.25, .25, .25, 1))
                imgui.end_menu()

            if imgui.begin_menu("Plugins", drawing):
                active_plugins = window.drawing.active_plugins
                for name in window.plugins.keys():
                    is_active = name in active_plugins
                    clicked, selected = imgui.menu_item(name, None, is_active, True)
                    if clicked and selected:
                        activate_plugin(window, drawing, name, {})
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
                    if window.stroke:
                        txt = repr(window.stroke.tool)
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

        if self.show_edit_history:
            self.show_edit_history = render_edits(window.drawing)

        return popup


def render_animation_settings(window):

    drawing = window.drawing

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
