import logging
from typing import NamedTuple
import zlib

from .brush import PicBrush
from .layer import Layer
from .ora import load_ora, save_ora
from .picture import LongPicture, load_png
from .palette import Palette
from .rect import Rectangle
from .util import Selectable, try_except_log


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

        self.edits = []
        self.edits_index = -1

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

    def add_layer(self, index=None, layer=None):
        layer = layer or Layer(LongPicture(self.size))
        # self.layers.add(layer, index)
        index = (index if index is not None else self.layers.get_current_index()) + 1

        self.layers.add(layer, index=index)
        self.layers.select(layer)
        edit = AddLayerEdit.create(self, layer, index)
        self._add_edit(edit)

    def remove_layer(self, index=None):
        if len(self.layers) == 1:
            return
        index = index or self.layers.get_current_index()
        layer = self.layers[index]
        edit = RemoveLayerEdit.create(self, layer)
        edit.perform(self)
        self._add_edit(edit)
        # self.layers.remove(layer)
        # if layer == self.current:
        #     while True:
        #         try:
        #             self.current = self.layers[index]
        #             break
        #         except IndexError:
        #             pass
        #         index -= 1

    def next_layer(self):
        self.layers.cycle_forward()

    def prev_layer(self):
        self.layers.cycle_backward()

    def move_layer_up(self):
        index1 = self.layers.get_current_index()
        if index1 < (len(self.layers) - 1):
            index2 = index1 + 1
            edit = SwapLayersEdit(index1, index2)
            edit.perform(self)
            self._add_edit(edit)

    def move_layer_down(self):
        index1 = self.layers.get_current_index()
        if 0 < index1:
            index1 = self.layers.get_current_index()
            index2 = index1 - 1
            edit = SwapLayersEdit(index1, index2)
            edit.perform(self)
            self._add_edit(edit)

    def clear_layer(self, layer=None, color=0):
        layer = layer or self.current
        self._add_edit(self._build_action(layer, layer.rect))
        layer.clear(value=color)

    @try_except_log
    def change_layer(self, new, rect, layer=None):
        "Update a part of the layer, keeping track of the change as an 'undo'"
        layer = layer or self.current
        edit = LayerEdit.create(self, layer, new, rect)
        self._add_edit(edit)
        layer.blit_part(new.pic, rect, rect.topleft)

    def change_color(self, i, rgba0, rgba1):
        print("change_color", i, rgba0, rgba1)
        r0, g0, b0, a0 = rgba0
        r1, g1, b1, a1 = rgba1
        delta = r1-r0, g1-g0, b1-b0, a1-a0
        edit = PaletteEdit(index=i, data=[delta])
        self._add_edit(edit)

    def _add_edit(self, edit):
        "Insert an edit into the history, keeping track of things"
        if self.edits_index < -1:
            del self.edits[self.edits_index + 1:]
            self.edits_index = -1
        self.edits.append(edit)

    @try_except_log
    def undo(self):
        if -self.edits_index <= len(self.edits):
            edit = self.edits[self.edits_index]
            edit.undo(self)
            self.edits_index -= 1
        logger.info("No more edits to undo!")

    @try_except_log
    def redo(self):
        if self.edits_index < -1:
            self.edits_index += 1
            edit = self.edits[self.edits_index]
            edit.perform(self)
        logger.info("No more edits to redo!")

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

    def __iter__(self):
        return iter(self.layers)


# Edit classes; immutable objects that represent an individual change of the drawing.

class LayerEdit(NamedTuple):

    "A change in the image data of a particular layer."

    index: int
    data: bytes
    rect: Rectangle

    @classmethod
    def create(cls, drawing, orig_layer, edit_layer, rect):
        "Helper to handle compressing the data."
        data = orig_layer.make_diff(edit_layer, rect)
        index = drawing.layers.index(orig_layer)
        return cls(index=index, data=zlib.compress(data), rect=rect)

    def perform(self, drawing):
        layer = drawing.layers[self.index]
        diff_data = zlib.decompress(self.data)
        layer.apply_diff(memoryview(diff_data).cast("h"), self.rect, False)

    def undo(self, drawing):
        layer = drawing.layers[self.index]
        diff_data = zlib.decompress(self.data)
        layer.apply_diff(memoryview(diff_data).cast("h"), self.rect, True)

    def __repr__(self):
        return f"{__class__}(index={self.index}, data={len(self.data)}B, rect={self.rect})"


class PaletteEdit(NamedTuple):

    "A change in the color data of the palette."

    index: int
    data: list

    def perform(self, drawing):
        for i, (dr, dg, db, da) in enumerate(self.data, start=self.index):
            r0, g0, b0, a0 = drawing.palette.colors[i]
            drawing.palette[i] = r0 + dr, g0 + dg, b0 + db, a0 + da

    def undo(self, drawing):
        for i, (dr, dg, db, da) in enumerate(self.data, start=self.index):
            r0, g0, b0, a0 = drawing.palette.colors[i]
            print(r0, g0, b0, a0)
            drawing.palette[i] = r0 - dr, g0 - dg, b0 - db, a0 - da


class AddLayerEdit(NamedTuple):

    index: int
    data: bytes
    size: tuple

    @classmethod
    def create(cls, drawing, layer, index):
        return cls(index, zlib.compress(layer.pic.data), layer.size)

    def perform(self, drawing):
        layer = Layer(LongPicture(size=self.size, data=zlib.decompress(self.data)))
        drawing.layers.add(layer, index=self.index)

    def undo(self, drawing):
        layer = drawing.layers[self.index]
        drawing.layers.remove(layer)

    def __repr__(self):
        return f"{__class__}(index={self.index}, data={len(self.data)}B, size={self.size})"


class RemoveLayerEdit(NamedTuple):

    index: int
    data: bytes
    size: tuple

    @classmethod
    def create(cls, drawing, layer):
        index = drawing.layers.index(layer)
        return cls(index, zlib.compress(layer.pic.data), layer.size)

    # This is the inverse operation of adding a layer
    perform = AddLayerEdit.undo
    undo = AddLayerEdit.perform

    def __repr__(self):
        return f"{__class__}(index={self.index}, data={len(self.data)}B, size={self.size})"


class SwapLayersEdit(NamedTuple):

    index1: int
    index2: int

    def perform(self, drawing):
        drawing.layers.swap(self.index1, self.index2)

    undo = perform
