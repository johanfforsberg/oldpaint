## Oldpaint ###

Oldpaint is intended to be a simple drawing program in the tradition of Deluxe Paint, but with some more "modern" features. 

Current status is "works for me". I use it, but some parts are not well tested and may break. It's fairly likely to crash or otherwise lose data. There are no releases suitable for "serious" use yet.

The motivation behind it is partly just that I want it for my own purposes, but also my learning more about OpenGL and "immediate mode" GUIs. But I would like it to become useful for other people too!

Oldpaint is written in python and uses OpenGL (via pyglet) to render things to screen. The user interface is built with (py)imgui. Some performance critical parts, basically the image handling and drawing operations, are sped up using numpy and Cython.

It's developed and used under Ubuntu Linux. I believe pyglet also supports Windows and MacOS but I have not tested either. Probably OpenGL support is the main problem there. If you try it I'd love to hear about it!


#### Current features ####
- Supports (only) 8 bit palette based images.
- Layers
- Unlimited undo
- Basic drawing operations (pencil, line, circle, fill...)
- Custom brushes
- Load/save PNG and OpenRaster/ORA files (essentially zipped PNGs, but supports layers etc).
- Autosave
- Tablet support (experimental)
- Plugins (experimental)
- Animation


#### Planned features ####
- More configuration
- Sprite sheets
- Gradients
- Brush operations (scale, rotate...)


#### Possible features ####
- Other file formats
- Palette restrictions (e.g. VGA, ECS, C64...)
- Color cycling
- Loading reference images
- Full 32 bit images


### Usage ##

If you've used DPaint or PPaint or anything similar, most things should be pretty familiar. Currently there is only support for 256 color palette based images. You draw by holding either the left ("foreground") or right ("background") mouse button. Use mouse wheel to pan and scroll. Select and edit colors in the palette, color 0 is currently always transparent background. The toolbar to the top right contains various basic drawing modes. Most other functionality is available via the menu bar, where you can also find various keyboard shortcuts. Otherwise the UI is pretty minimal - by design.


### Installation ###

Oldpaint requires a reasonably recent python version (something like 3.8 or later) and support for OpenGL 4.5.

Currently there's no release on PyPI. Recommended way to install it is by cloning this repo, cd:ing into it and running:

    $ python -m venv env
    $ env/bin/pip install -e .
    $ env/bin/oldpaint
    
It will take a few seconds to start up the first time, since it uses cython to compile some parts to machine code at import, and caches it for future runs. After that a window should appear and you can start drawing.

If any step fails, you're probably missing some required stuff such as a C compiler. On Ubuntu, something like the following should help.
    
    $ apt install build-essential python3-dev
    
If you get OpenGL related errors, it's possible that your hardware or driver does not support GL version 4.5. In that case you're currently out of luck. I'd accept MRs to improve support as long as they're not very complex.


#### License ####

Oldpaint is released under the GNU General Public License version 3. https://www.gnu.org/licenses/gpl-3.0.en.html

This basically means you're free to use, modify, and share it as you like. But if you want to distribute a modified version, you must also make the modified source files available.
