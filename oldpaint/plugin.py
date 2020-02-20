import inspect
from itertools import islice

import imgui

from .config import plugin_source
import oldpaint


def init_plugins(window):
    plugins = plugin_source.list_plugins()
    for plugin_name in plugins:
        print("init", plugin_name)
        try:
            plugin = plugin_source.load_plugin(plugin_name)
            sig = inspect.signature(plugin.plugin)
            window.plugins[plugin_name] = plugin.plugin, sig.parameters, {}
        except Exception as e:
            print(e)


def render_plugins_ui(window):
    if not window.drawing:
        return
    for name in window.drawing.active_plugins:
        plugin, sig, args = window.plugins[name]
        imgui.begin(name, True)
        imgui.columns(2)
        for param_name, param_sig in islice(sig.items(), 3, None):
            imgui.text(param_name)
            imgui.next_column()
            default_value = args.get(param_name)
            if default_value is not None:
                value = default_value
            else:
                value = param_sig.default
            label = f"##{param_name}_val"
            if param_sig.annotation == int:
                changed, args[param_name] = imgui.drag_int(label, value)
            elif param_sig.annotation == float:
                changed, args[param_name] = imgui.drag_float(label, value)
            elif param_sig.annotation == str:
                changed, args[param_name] = imgui.input_text(label, value, 20)
            elif param_sig.annotation == bool:
                changed, args[param_name] = imgui.checkbox(label, value)
            imgui.next_column()
        imgui.columns(1)

        if imgui.button("Execute"):
            plugin(oldpaint, window.drawing, window.brush, **args)

        imgui.same_line()
        imgui.button("Help")
        if imgui.begin_popup_context_item("Help", mouse_button=0):
            imgui.text(inspect.cleandoc(plugin.__doc__))
            imgui.end_popup()

        imgui.end()
