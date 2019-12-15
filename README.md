## Oldpaint ###

Oldpaint is intended to be a drawing program in the tradition of "Deluxe Paint", but with a more modern interface and feature set.

Current status is "under construction". The most important things work to some degree, but there are bugs and parts missing, and performance may vary. It will likely crash. Definitely not ready for actual use.

Oldpaint is written in python and uses OpenGL (via pyglet) to render things to screen. The user interface is built with imgui. Some performance critical parts, basically the image handling, is sped up using Cython.

The motivation behind it is partly just that I want it for my own purposes, but also my learning more about OpenGL and "immediate mode" GUIs.


#### Current features ####
- Supports (only) 8 bit palette based images.
- Layers
- Unlimited undo
- Basic drawing operations (pencil, line, circle...)
- Custom brushes
- Load/save OpenRaster files (essentially zipped PNGs, but supports layers etc)


#### Planned features ####
- Animation
- Sprite sheets
- Gradients
- Export to PNG
- Extensibility/scripting (it's all written in python anyway)


#### Possible features ####
- Other file formats
- Palette restrictions (e.g. ECS, C64...)
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


#### License ####

Oldpaint is released under the GNU General Public License version 3. https://www.gnu.org/licenses/gpl-3.0.en.html
