import pyglet
import pyximport

pyximport.install()  # Setup cython to autocompile pyx modules

from .window import OldpaintWindow


config = pyglet.gl.Config(major_version=4, minor_version=5,  # Minimum OpenGL requirement
                          double_buffer=False)  # Double buffering gives noticable cursor lag

window = OldpaintWindow(width=800, height=600, config=config)


class OldpaintEventLoop(pyglet.app.EventLoop):

    "A tweaked event loop that lowers the idle refresh rate for less CPU heating."

    def idle(self):
        super().idle()
        return 0.05


pyglet.app.event_loop = OldpaintEventLoop()
pyglet.app.run()
