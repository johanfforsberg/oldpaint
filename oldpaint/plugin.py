import inspect
import imp
from itertools import islice
from logging import getLogger
from time import time
from traceback import print_exc

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
            if hasattr(plugin, "plugin"):
                sig = inspect.signature(plugin.plugin)
                window.plugins[plugin_name] = plugin.plugin, sig.parameters, {}
            elif hasattr(plugin, "Plugin"):
                sig = inspect.signature(plugin.Plugin.__call__)
                window.plugins[plugin_name] = plugin.Plugin(), sig.parameters, {}
        except Exception as e:
            print_exc()
            

@try_except_log
def render_plugins_ui(window):
    "Draw UI windows for all plugins active for the current drawing."
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

        texture_and_size = getattr(plugin, "texture", None)
        if texture_and_size:
            texture, size = texture_and_size
            w, h = size
            ww, wh = imgui.get_window_size()
            scale = max(1, (ww - 10) // w)
            imgui.image(texture.name, w*scale, h*scale, border_color=(1, 1, 1, 1))

        last_run = getattr(plugin, "last_run", 0)
        period = getattr(plugin, "period", None)
        t = time()
        if period and t > last_run + period or imgui.button("Execute"):
            plugin.last_run = last_run
            result = plugin(window.drawing, window.brush, **args)
            if result:
                args.update(result)

        imgui.button("Help")
        if imgui.begin_popup_context_item("Help", mouse_button=0):
            if plugin.__doc__:
                imgui.text(inspect.cleandoc(plugin.__doc__))
            else:
                imgui.text("No documentation available.")
            imgui.end_popup()

        imgui.end()
