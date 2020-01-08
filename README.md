## Oldpaint ###

Oldpaint is intended to be a drawing program in the tradition of "Deluxe Paint", but with a more modern interface and feature set.

Current status is *under construction*. It's getting close to being useful, but it's not well tested. It's pretty likely to crash or otherwise lose data. Performance may vary. Not ready for serious use.

Oldpaint is written in python and uses OpenGL (via pyglet) to render things to screen. The user interface is built with (py)imgui. Some performance critical parts, basically the image handling, is sped up using Cython.

The motivation behind it is partly just that I want it for my own purposes, but also my learning more about OpenGL and "immediate mode" GUIs. But I would like it to become useful for other people too.


### Usage ##

If you've used DPaint or PPaint or anything similar, most things should be pretty familiar. Currently there is only support for 256 color palette based images. You draw by holding either the left ("foreground") or right ("background") mouse button. Use mouse wheel to pan and scroll. Select and edit colors in the palette, color 0 is currently always transparent background. The toolbar to the top right contains various basic drawing modes. Most other functionality is available via the menu bar, where you can also find various keyboard shortcuts. Otherwise the UI is pretty minimal - by design.


#### Current features ####
- Supports (only) 8 bit palette based images.
- Layers
- Unlimited undo
- Basic drawing operations (pencil, line, circle, fill...)
- Custom brushes
- Load/save PNG, OpenRaster files (essentially zipped PNGs, but supports layers etc)


#### Planned features ####
- Animation
- Sprite sheets
- Gradients
- Extensibility/scripting (it's all written in python anyway)


#### Possible features ####
- Other file formats
- Palette restrictions (e.g. ECS, C64...)
- Palette cycling
- Loading reference images
- Full 32 bit images


#### Installation ####

Since oldpaint is under heavy development, there's currently no way to install it without building it yourself.

Oldpaint is developed with python 3.7, it might work with 3.6 but nothing older than that. It's only been tested on Ubuntu linux, using a fairly new AMD graphics card, and on a laptop with a fairly new Intel GPU.

Oldpaint has a special dependency, on the "fogl" library (https://github.com/johanfforsberg/fogl). Right now the way to go is to clone it somewhere, installing it according to its readme, and editing oldpaint's `pyproject.toml` file to point to the location of the fogl repo. Then (assuming you have poetry installed), in oldpaint's repo, run:

    $ poetry install
    
That should install the various other dependencies of oldpaint. Then you should be able to start it with

    $ poetry run python -m oldpaint
    
It will take a few seconds to start up the first time, since it uses cython to compile some parts to machine code. If this (or installation of the dependencies) fails, you're probably missing some compiler stuff. On ubuntu, something like the following should help.
    
    $ apt install build-essential python3-dev
    
If you try it, especially on a non-linux platform, I'd love to hear about it!


#### License ####

Oldpaint is released under the GNU General Public License version 3. https://www.gnu.org/licenses/gpl-3.0.en.html
