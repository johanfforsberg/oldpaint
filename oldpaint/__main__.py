import pyglet
import pyximport

pyximport.install()  # Setup cython to autocompile pyx modules

from .config import load_config, save_config
from .window import OldpaintWindow


gl_config = pyglet.gl.Config(major_version=4, minor_version=5,  # Minimum OpenGL requirement
                             double_buffer=False)  # Double buffering gives noticable cursor lag


config = load_config()
width, height = config["window_size"]

window = OldpaintWindow(width=width, height=height, recent_files=config["recent_files"],
                        config=gl_config)


class OldpaintEventLoop(pyglet.app.EventLoop):

    "A tweaked event loop that lowers the idle refresh rate for less CPU heating."

    def idle(self):
        super().idle()
        return 0.05


pyglet.app.event_loop = OldpaintEventLoop()
pyglet.app.run(0.02)


save_config(window_size=window.get_size(),
            recent_files=window.recent_files.keys())
