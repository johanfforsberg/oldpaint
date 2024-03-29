"""
Plugin architecture. Currently very minimal, hacky and fragile.
The plugin API is also not stable.
"""

import inspect
import imp
from itertools import islice
import inspect
from logging import getLogger
from time import time
from traceback import format_exc
from typing import Tuple, get_args, get_origin

import imgui
import oldpaint

from .config import plugin_source
from .util import try_except_log


logger = getLogger("oldpaint").getChild("plugins")


def init_plugins(window):
    "(Re)initialize all found plugins"
    plugins = plugin_source.list_plugins()
    for plugin_name in plugins:
        logger.info("Initializing plugin: %s", plugin_name)
        try:
            plugin = plugin_source.load_plugin(plugin_name)
            if plugin_name in window.plugins:
                imp.reload(plugin)
            # TODO more sophisticated way of handling the different kinds of plugin
            if hasattr(plugin, "plugin"):
                # Simple function plugin
                assert inspect.isfunction(plugin.plugin), "'plugin' with lowercase p should be a function"
                sig = inspect.signature(plugin.plugin)
                window.plugins[plugin_name] = plugin.plugin, sig.parameters
            elif hasattr(plugin, "Plugin"):
                # Class plugin
                assert inspect.isclass(plugin.Plugin), "'Plugin' with capital P should be a class"
                assert hasattr(plugin.Plugin, "__call__"), "Class plugins must have a __call__ method"
                sig = inspect.signature(plugin.Plugin.__call__)
                params = dict(islice(sig.parameters.items(), 1, None))
                window.plugins[plugin_name] = plugin.Plugin, params
        except Exception:
            logger.exception(f"Problem initializing plugin {plugin_name}")


@try_except_log            
def activate_plugin(window, drawing, plugin_name, args):
    active_plugins = drawing.active_plugins
    plugin, params = window.plugins[plugin_name]
    if inspect.isclass(plugin):
        active_plugins[plugin_name] = (plugin(**args), {})
    else:
        active_plugins[plugin_name] = (plugin, args)


@try_except_log
def render_plugins_ui(window):
    "Draw UI windows for all plugins active for the current drawing."
    if not window.drawing:
        return

    drawing = window.drawing

    deactivated = set()
    for name, (plugin, args) in window.drawing.active_plugins.items():
        plugin_base, sig = window.plugins[name]
        window_size = getattr(plugin, "window_size", None)
        if window_size:
            imgui.set_next_window_size(*window_size)
        _, opened = imgui.begin(f"{ name } ##{ drawing.path or drawing.uuid }", True)
        if not opened:
            deactivated.add(name)
        imgui.columns(2)
        user_params = ((name, param) for name, param in sig.items() if param.kind == param.KEYWORD_ONLY)
        for param_name, param_sig in user_params:
            if param_sig.annotation == inspect._empty:
                continue
            imgui.text(param_name)
            imgui.next_column()
            default_value = args.get(param_name, param_sig.default)
            label = f"##{param_name}_val"
            if param_sig.annotation == int:
                changed, args[param_name] = imgui.drag_int(label, value)
            elif param_sig.annotation == float:
                changed, args[param_name] = imgui.drag_float(label, value)
            elif param_sig.annotation == str:
                changed, args[param_name] = imgui.input_text(label, value, 20)
            elif param_sig.annotation == bool:
                changed, args[param_name] = imgui.checkbox(label, value)
            elif get_origin(param_sig.annotation) == tuple:
                param_args = get_args(param_sig.annotation)
                if all(arg == int for arg in param_args):
                    if len(param_args) == 2:
                        changed, args[param_name] = imgui.input_int2(label, *value)
                    elif len(param_args) == 3:
                        changed, args[param_name] = imgui.input_int3(label, *value)
                
            imgui.next_column()
        imgui.columns(1)

        texture_and_size = getattr(plugin, "texture", None)
        if texture_and_size:
            texture, size = texture_and_size
            w, h = size
            ww, wh = imgui.get_window_size()
            scale = max(1, (ww - 10) // w)
            imgui.image(texture.name, w*scale, h*scale, border_color=(1, 1, 1, 1))

        if not inspect.isfunction(plugin) or imgui.button("Execute"):
            try:
                available_args = {
                    "oldpaint": oldpaint,
                    "window": window,
                    "drawing": window.drawing,
                    "brush": window.brush,
                    "imgui": imgui,
                }
                inject_args = {
                    name: value
                    for name, value in available_args.items()
                    if name in sig
                }
                result = plugin(**inject_args, **args)
                if result:
                    args.update(result)
            except Exception:
                # We don't want crappy plugins to ruin everything
                # Still probably probably possible to crash opengl though...
                logger.error(f"Plugin {name}: {format_exc()}")

        imgui.button("Help")
        if imgui.begin_popup_context_item("Help", mouse_button=0):
            if plugin.__doc__:
                imgui.text(inspect.cleandoc(plugin.__doc__))
            else:
                imgui.text("No documentation available.")
            imgui.end_popup()

        imgui.end()
    for name in deactivated:
        window.drawing.active_plugins.pop(name, None)


def check_plugin_keys(window, symbol, modifiers):
    if not window.drawing:
        return

    drawing = window.drawing

    deactivated = set()
    for name, (plugin, _) in window.drawing.active_plugins.items():
        try:
            return plugin.on_key_press(symbol, modifiers)
        except AttributeError:
            pass
                
