import pyglet
import pyximport

pyximport.install()  # Setup cython to autocompile pyx modules

from .window import OldpaintWindow


config = pyglet.gl.Config(major_version=4, minor_version=5,
                          double_buffer=False)  # Double buffering gives noticable cursor lag

window = OldpaintWindow(width=800, height=600, config=config)

pyglet.app.run()
