import logging
from time import time

from .layer import Layer
from .ora import load_ora, save_ora
from .picture import Picture, LongPicture
from .palette import Palette
from .util import Selectable


logger = logging.getLogger(__name__)


class Brushes(Selectable):
    pass


class Stack:

    """
    The "stack" is a bunch of images with the same size and palette, stacked on top of each order (from the bottom).

    This is also where most functionality that affects the image is collected, e.g. strokes, undo/redo, load/save...
    """

    def __init__(self, size, layers=None, palette=None):
        self.size = size
        self.layers = layers or []
        self.current = layers[0] if layers else None
        self._palette = palette if palette else Palette(transparency=0)
        self.unsaved = False

        self.undos = []
        self.redos = []
        # self.brushes = Brushes([RectangleBrush(1, 1), RectangleBrush(2, 2),
        #                         EllipseBrush(3, 3), EllipseBrush(10, 10)])

        self.selection = None
        self.stroke = None

    def load_image(self, path):
        #img = PILImage.open(path)
        layer, palette = Layer.load_png(path)
        self.layers.clear()
        self.add_layer(layer)
        self.palette = palette
        self.path = path

    # @classmethod
    # def from_ora(cls, path):
    #     layer_images = load_ora(path)
    #     img = layer_images[0]
    #     size = img.size
    #     palette = Palette(img.getpalette(), transparency=0)
    #     layers = [PillowImage(i) for i in layer_images]
    #     return cls(size=size, layers=layers, palette=palette)

    # @classmethod
    # def from_png(cls, path):
    #     img = PILImage.open(path)
    #     size = img.size
    #     palette = Palette(img.getpalette(), transparency=0)
    #     layers = [PillowImage(img)]
    #     return cls(size=size, layers=layers, palette=palette)

    def save_ora(self, path):
        save_ora(self.size, self.layers, self.palette, path)

    def get_index(self, layer=None):
        "Return the stack index of the given layer (or current)."
        layer = layer or self.current
        if layer is not None:
            try:
                return self.layers.index(self.current)
            except ValueError:
                # TODO in this case, maybe some cleanup is in order?
                pass

    def add_layer(self, layer=None):
        # if data:
        #     layer = PillowImage(data=data)
        # else:
        #     layer = PillowImage(PILImage.new("P", self.size))
        #     layer.clear()
        layer = layer or Layer(Picture(self.size))
        index = self.get_index()
        if index is None:
            self.layers.append(layer)
        else:
            self.layers.insert(index + 1, layer)
        self.current = layer
        self.dirty = True

    def remove_layer(self, index=None):
        if len(self.layers) == 1:
            return
        index = index or self.get_index()
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
        self.dirty = True

    def next_layer(self):
        index = min(self.get_index() + 1, len(self.layers) - 1)
        self.current = self.layers[index]

    def prev_layer(self):
        index = max(self.get_index() - 1, 0)
        self.current = self.layers[index]

    def move_layer_up(self):
        index = self.get_index()
        if index < len(self.layers) - 1:
            self.layers.remove(self.current)
            self.layers.insert(index + 1, self.current)
            self.dirty = True

    def move_layer_down(self):
        index = self.get_index()
        if index > 0:
            self.layers.remove(self.current)
            self.layers.insert(index - 1, self.current)
            self.dirty = True

    def clear_layer(self, layer=None, color=0):
        layer = layer or self.current
        prev_data = layer.get_subimage(layer.rect)
        self.undos.append((layer, layer.rect, prev_data))
        layer.clear(value=color)

    def undo(self):
        if self.undos:
            layer, rect, undo_data = self.undos.pop()
            redo_data = layer.get_subimage(rect)
            self.redos.append((layer, rect, redo_data))
            layer.blit(undo_data, rect)
            return rect

    def redo(self):
        if self.redos:
            layer, rect, redo_data = self.redos.pop()
            undo_data = layer.get_subimage(rect)
            self.undos.append((layer, rect, undo_data))
            layer.blit(redo_data, rect)
            return rect

    def make_brush(self, rect=None, layer=None):
        rect = rect or self.selection
        layer = layer or self.current
        subimage = layer.get_subimage(rect)
        brush = Brush(subimage)
        self.brushes.add(brush)

    @property
    def palette(self):
        return self._palette

    @palette.setter
    def palette(self, palette_data):
        self._palette = Palette(palette_data, 0)  #img.info.get("transparency"))

    def __repr__(self):
        return f"ImageStack(size={self.size}, layers={self.layers}, current={self.get_index()})"

    def layer_op(method, *args, layer=None):
        layer = layer or self.current
        rect = method(layer, *args)

    def update(self, new_data, rect, layer=None):
        layer = layer or self.current
        prev_data = layer.get_subimage(rect)
        self.undos.append((layer, rect, prev_data))
        layer.blit(new_data, rect)

    def __iter__(self):
        return iter(self.layers)
