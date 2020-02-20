import configparser
from pathlib import Path

from pluginbase import PluginBase
from xdg import XDG_CONFIG_HOME

OLDPAINT_CONFIG_HOME = XDG_CONFIG_HOME / "oldpaint"
OLDPAINT_CONFIG_HOME.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = OLDPAINT_CONFIG_HOME / "oldpaint.ini"


def load_config():
    config_file = configparser.ConfigParser()
    config_file.read(CONFIG_FILE)
    config = {}
    if "window" in config_file:
        size = config_file["window"].get("size")
        w, h = [int(v) for v in size.split()]
        config["window_size"] = w, h
    else:
        config["window_size"] = 800, 600

    if "recent_files" in config_file:
        recent_files = config_file["recent_files"]
        config["recent_files"] = list(recent_files.values())
    else:
        config["recent_files"] = []

    return config


def save_config(window_size=None, recent_files=None):
    config_file = configparser.ConfigParser()
    config_file.read(CONFIG_FILE)
    if window_size:
        w, h = window_size
        config_file["window"] = {"size": f"{w} {h}"}
    if recent_files:
        config_file["recent_files"] = {
            f"file_{i}": filename
            for i, filename in enumerate(recent_files)
        }
    with open(CONFIG_FILE, "w") as f:
        config_file.write(f)


OLDPAINT_PLUGIN_DIR = Path(__file__).parent.parent / "plugins"
OLDPAINT_USER_PLUGIN_DIR = OLDPAINT_CONFIG_HOME / "plugins"
OLDPAINT_USER_PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
plugin_base = PluginBase(package='oldpaint.plugins')
plugin_source = plugin_base.make_plugin_source(searchpath=[str(OLDPAINT_PLUGIN_DIR),
                                                           str(OLDPAINT_USER_PLUGIN_DIR)])
