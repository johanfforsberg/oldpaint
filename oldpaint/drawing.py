import logging
import zlib

from .brush import PicBrush
from .layer import Layer
from .ora import load_ora, save_ora
from .picture import LongPicture, load_png
from .palette import Palette
from .util import Selectable


logger = logging.getLogger(__name__)


class Drawing:

    """
    The "drawing" is a bunch of images with the same size and palette,
    stacked on top of each order (from the bottom).

    This is also where most functionality that affects the image is collected,
    e.g. drawing, undo/redo, load/save...

    """

    def __init__(self, size, layers=None, palette=None):
        self.size = size
        if layers:
            self.layers = Selectable(layers)
        else:
            self.layers = Selectable([Layer(LongPicture(size=self.size))])
        self.overlay = Layer(LongPicture(size=self.size))
        self._palette = palette if palette else Palette(transparency=0)
        self.brushes = Selectable()
        self.unsaved = False

        self.undos = []
        self.redos = []
        self.selection = None

        # Keep track of what we're looking at
        self.offset = (0, 0)
        self.zoom = 0

    @property
    def current(self):
        return self.layers.current

    @current.setter
    def current(self, layer):
        assert isinstance(layer, Layer)
        self.layers.set_item(layer)

    @classmethod
    def from_png(cls, path):
        pic, colors = load_png(path)
        layer = Layer(pic)
        palette = Palette(colors, transparency=0)
        return cls(size=layer.size, layers=[layer], palette=palette)

    @classmethod
    def from_ora(cls, path):
        layer_pics, colors = load_ora(path)
        pic = layer_pics[0]
        size = pic.size
        palette = Palette(colors, transparency=0)
        layers = [Layer(p) for p in layer_pics]
        return cls(size=size, layers=layers, palette=palette)

    def save_ora(self, path):
        save_ora(self.size, self.layers, self.palette, path)

    # def get_index(self, layer=None):
    #     "Return the index of the given layer (or current)."
    #     layer = layer or self.current
    #     if layer is not None:
    #         try:
    #             return self.layers.index(self.current)
    #         except ValueError:
    #             # TODO in this case, maybe some cleanup is in order?
    #             pass

    def add_layer(self, layer=None):
        layer = layer or Layer(LongPicture(self.size))
        self.layers.add(layer)

    def remove_layer(self, index=None):
        if len(self.layers) == 1:
            return
        index = index or self.layers.get_current_index()
        layer = self.layers[index]
        self.layers.remove(layer)
        if layer == self.current:
            while True:
                try:
                    self.current = self.layers[index]
                    break
                except IndexError:
                    pass
                index -= 1

    def next_layer(self):
        self.layers.cycle_forward()

    def prev_layer(self):
        self.layers.cycle_backward()

    def move_layer_up(self):
        index = self.layers.get_current_index()
        if index < len(self.layers) - 1:
            self.layers.swap(index + 1, index)

    def move_layer_down(self):
        index = self.layers.get_current_index()
        if index > 0:
            self.layers.swap(index + 1, index)

    def clear_layer(self, layer=None, color=0):
        layer = layer or self.current
        self.undos.append(self._build_action(layer, layer.rect))
        self.redos.clear()
        layer.clear(value=color)

    def update(self, new, rect, layer=None):
        "Update a part of the layer, keeping track of the change as an 'undo'"
        layer = layer or self.current
        self.undos.append(self._build_action(layer, rect))
        self.redos.clear()
        layer.blit_part(new.pic, rect, rect.topleft)

    def _build_action(self, layer, rect):
        "An 'action' here means something that can be undone/redone."
        # By using compression on the undo/redo buffers, we save a
        # *lot* of memory.  Some quick tests suggest at least an
        # order of magnitude, but it will certainly depend on the
        # contents.
        data = layer.get_subimage(rect).data
        return (layer, rect, zlib.compress(data))

    # TODO undo/redo should cover all "destructive" ops, e.g delete layer
    def undo(self):
        if self.undos:
            layer, rect, undo_data_z = self.undos.pop()
            undo_data = zlib.decompress(undo_data_z)
            self.redos.append(self._build_action(layer, rect))
            layer.blit(LongPicture(rect.size, undo_data), rect, alpha=False)
            return rect

    def redo(self):
        if self.redos:
            layer, rect, redo_data = self.redos.pop()
            redo_data = zlib.decompress(redo_data)
            self.undos.append(self._build_action(layer, rect))
            layer.blit(LongPicture(rect.size, redo_data), rect, alpha=False)
            return rect

    def make_brush(self, rect=None, layer=None):
        rect = rect or self.selection
        layer = layer or self.current
        subimage = layer.get_subimage(rect)
        brush = PicBrush(subimage)
        self.brushes.add(brush)

    @property
    def palette(self):
        return self._palette

    @palette.setter
    def palette(self, palette_data):
        self._palette = Palette(palette_data, 0)  #img.info.get("transparency"))

    def __repr__(self):
        return f"Drawing(size={self.size}, layers={self.layers}, current={self.get_index()})"

    # def layer_op(method, *args, layer=None):
    #     layer = layer or self.current
    #     rect = method(layer, *args)

    def __iter__(self):
        return iter(self.layers)
