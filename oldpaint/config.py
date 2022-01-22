import configparser
import logging
from pathlib import Path

from pluginbase import PluginBase
from appdirs import AppDirs

oldpaint_dirs = AppDirs("oldpaint", "nurbldoff")

CONFIG_HOME = Path(oldpaint_dirs.user_config_dir)
CONFIG_FILE = CONFIG_HOME / "oldpaint.ini"
CACHE_DIR = Path(oldpaint_dirs.user_cache_dir)


def load_config():
    config_file = configparser.ConfigParser()
    config_file.read(CONFIG_FILE)
    config = {}
    
    if "logging" in config_file:
        level = config_file["logging"].get("level", "INFO")
        logging.basicConfig(level=getattr(logging, level))
    else:
        # TODO Change this default when oldpaint is more stable.
        logging.basicConfig(level=logging.DEBUG)
        
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
    logging.info("saving config")
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


def get_drawing_cache_dir(drawing_path):
    dir_name = drawing_path.replace("/", "%")
    path = CACHE_DIR / dir_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_autosave_filename(drawing_path, keep=10):
    # TODO perhaps find some more clever method of keeping some older autosaves
    # without storing too many?
    cache_dir = get_drawing_cache_dir(drawing_path)
    files = list(get_autosaves(drawing_path))
    file_nos = sorted(int(fn.name.split(".")[0]) for fn in files[-keep:])

    to_remove = file_nos[0:-(keep-1)]
    for fn in to_remove:
        (cache_dir / f"{fn}.ora").unlink()

    if file_nos:
        latest = file_nos[-1]
    else:
        latest = -1
    return cache_dir / f"{latest + 1}.ora"


def get_autosaves(drawing_path):
    cache_dir = get_drawing_cache_dir(drawing_path)
    return cache_dir.glob("*.ora")


def get_palettes():
    palette_dir = CONFIG_HOME / "palettes"
    if palette_dir.exists():
        return palette_dir.glob("*.json")
    return []


PLUGIN_DIR = Path(__file__).parent.parent / "plugins"
USER_PLUGIN_DIR = CONFIG_HOME / "plugins"
USER_PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
plugin_base = PluginBase(package='oldpaint.plugins')
plugin_source = plugin_base.make_plugin_source(searchpath=[str(PLUGIN_DIR), str(USER_PLUGIN_DIR)])
