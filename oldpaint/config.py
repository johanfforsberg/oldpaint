import configparser

from xdg import XDG_CONFIG_HOME


CONFIG_FILE = XDG_CONFIG_HOME / "oldpaint.ini"


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
