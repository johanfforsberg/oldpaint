__version__ = '0.1.0'

from argparse import ArgumentParser, ArgumentTypeError
import os
import re

import pyglet
import pyximport

pyximport.install(language_level=3)  # Setup cython to autocompile pyx modules

from .config import load_config, save_config
from .window import OldpaintWindow


def parse_drawing_spec(spec):
    m = re.match(r"@(\d+)x(\d+)", spec)
    if m:
        width = int(m.group(1))
        height = int(m.group(2))
        return width, height
    elif os.path.exists:
        return spec
    raise ArgumentTypeError("Could not understand '{spec}' as drawing specification. "
                            "It should be either a valid filename or something like '@WxH'.")


class OldpaintEventLoop(pyglet.app.EventLoop):

    "A tweaked event loop that lowers the idle refresh rate for less CPU heating."

    def idle(self):
        super().idle()
        return 0.05


def run():
    parser = ArgumentParser()
    parser.add_argument("drawing", type=parse_drawing_spec, nargs="*")

    args = parser.parse_args()

    gl_config = pyglet.gl.Config(major_version=4, minor_version=5,  # Minimum OpenGL requirement
                                 double_buffer=False)  # Double buffering gives noticable cursor lag

    config = load_config()
    width, height = config["window_size"]

    window = OldpaintWindow(width=width, height=height, recent_files=config["recent_files"],
                            config=gl_config, drawing_specs=args.drawing)

    pyglet.app.event_loop = OldpaintEventLoop()
    pyglet.app.run(0.02)

    save_config(window_size=window.get_size(),
                recent_files=window.recent_files.keys())
