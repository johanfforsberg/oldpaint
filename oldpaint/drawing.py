from dataclasses import dataclass, field
import logging
import os
import struct
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

    IMPORTANT! It's a bad idea to directly modify the layers! Always
    use the corresponding methods in this class instead. Otherwise you will
    mess up the undo history beyond repair.
    """

    def __init__(self, size, layers=None, palette=None, path=None):
        self.size = size
        if layers:
            self.layers = Selectable(layers)
        else:
            self.layers = Selectable([Layer(LongPicture(size=self.size))])
        self.overlay = Layer(LongPicture(size=self.size))
        self.palette = palette if palette else Palette(transparency=0)
        self.brushes = Selectable()

        # History of changes
        self._edits = []
        self._edits_index = -1
        self._latest_save_index = 0

        self.selection = None

        # Keep track of what we're looking at
        self.offset = (0, 0)
        self.zoom = 0

        self.path = path

    @property
    def current(self):
        return self.layers.current

    @current.setter
    def current(self, layer):
        assert isinstance(layer, Layer)
        self.layers.set_item(layer)

    @property
    def filename(self):
        return os.path.basename(self.path) if self.path else "[Unnamed]"

    @property
    def edits(self):
        if self._edits_index == -1:
            return self._edits
        return self._edits[:self._edits_index + 1]

    @property
    def unsaved(self):
        "Return whether there have been edits since last time the drawing was saved."
        return self._latest_save_index < len(self._edits)

    @classmethod
    def from_png(cls, path):
        pic, colors = load_png(path)
        layer = Layer(pic)
        palette = Palette(colors, transparency=0, size=len(colors))
        return cls(size=layer.size, layers=[layer], palette=palette, path=path)

    @classmethod
    def from_ora(cls, path):
        layer_pics, colors = load_ora(path)
        pic = layer_pics[0]
        size = pic.size
        palette = Palette(colors, transparency=0)
        layers = [Layer(p) for p in layer_pics]
        return cls(size=size, layers=layers, palette=palette, path=path)

    def save_ora(self, path=None):
        if path is None and self.path:
            save_ora(self.size, self.layers, self.palette, self.path)
        elif path:
            self.path = path
            save_ora(self.size, self.layers, self.palette, path)
        else:
            raise RuntimeError("Can't save without path")
        self._latest_save_index = len(self._edits)

    def add_layer(self, index=None, layer=None):
        layer = layer or Layer(LongPicture(self.size))
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
        edit = LayerClearEdit.create(self, layer, color=color)
        edit.perform(self)
        self._add_edit(edit)

    def flip_layer_horizontal(self, layer=None):
        layer = layer or self.current
        edit = LayerFlipEdit(self.layers.index(layer), True)
        edit.perform(self)
        self._add_edit(edit)

    def flip_layer_vertical(self, layer=None):
        layer = layer or self.current
        edit = LayerFlipEdit(self.layers.index(layer), False)
        edit.perform(self)
        self._add_edit(edit)

    @try_except_log
    def change_layer(self, new, rect, layer=None):
        "Update a part of the layer, keeping track of the change as an 'undo'"
        layer = layer or self.current
        edit = LayerEdit.create(self, layer, new, rect)
        self._add_edit(edit)
        layer.blit_part(new.pic, rect, rect.topleft)

    def change_color(self, i, rgba0, rgba1):
        r0, g0, b0, a0 = rgba0
        r1, g1, b1, a1 = rgba1
        delta = r1-r0, g1-g0, b1-b0, a1-a0
        edit = PaletteEdit(index=i, data=[delta])
        self._add_edit(edit)

    def make_brush(self, rect=None, layer=None, clear=False):
        "Create a brush from part of the given layer."
        rect = rect or self.selection
        layer = layer or self.current
        subimage = layer.get_subimage(rect)
        subimage.fix_alpha([0])  # TODO Use the proper list of transparent colors
        # TODO In fact this should not really be needed...
        if clear:
            edit = LayerClearEdit.create(self, layer, rect,
                                         color=self.palette.background)
            edit.perform(self)
            self._add_edit(edit)
        brush = PicBrush(subimage)
        self.brushes.add(brush)

    def _add_edit(self, edit):
        "Insert an edit into the history, keeping track of things"
        if self._edits_index < -1:
            del self._edits[self._edits_index + 1:]
            self._edits_index = -1
        self._edits.append(edit)

    @try_except_log
    def undo(self):
        "Restore the drawing to the state it was in before the current edit was made."
        if -self._edits_index <= len(self._edits):
            edit = self._edits[self._edits_index]
            edit.undo(self)
            self._edits_index -= 1
        logger.info("No more edits to undo!")

    @try_except_log
    def redo(self):
        "Restore the drawing to the state it was in after the current edit was made."
        if self._edits_index < -1:
            self._edits_index += 1
            edit = self._edits[self._edits_index]
            edit.perform(self)
        logger.info("No more edits to redo!")

    def __repr__(self):
        return f"Drawing(size={self.size}, layers={self.layers}, current={self.get_index()})"

    def __iter__(self):
        return iter(self.layers)


# Edit classes; immutable objects that represent an individual change of the drawing.

class Edit:

    @classmethod
    def get_type_mapping(cls):
        return {
            subclass.type: subclass
            for subclass in cls.__subclasses__
        }

    def store(self):
        return struct.pack(self._struct, self._type, self.index, *self.rect) + self.data

    @classmethod
    def load(cls, stored):
        index, *rect = struct.unpack(cls._struct, stored[:cls._structsize])
        z = zlib.decompressobj()
        data = z.decompress(stored[5:])
        return cls(index=index, rect=Rectangle(*rect), data=data), z.unused_data


@dataclass(frozen=True)
class LayerEdit(Edit):

    "A change in the image data of a particular layer."

    _type = 0
    _struct = "cchhhh"
    _structsize = struct.calcsize(_struct)

    index: int
    rect: Rectangle
    data: bytes

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


@dataclass(frozen=True)
class LayerClearEdit(Edit):

    index: int
    rect: Rectangle
    color: int
    data: bytes

    @classmethod
    def create(cls, drawing, orig_layer, rect=None, color=0):
        if rect:
            data = orig_layer.get_subimage(rect).data
        else:
            data = orig_layer.pic.data
            rect = orig_layer.rect
        index = drawing.layers.index(orig_layer)
        return cls(index=index, data=zlib.compress(data), rect=rect, color=color)

    def perform(self, drawing):
        layer = drawing.layers[self.index]
        layer.clear(self.rect, value=self.color)

    def undo(self, drawing):
        layer = drawing.layers[self.index]
        diff_data = zlib.decompress(self.data)
        layer.blit(LongPicture(self.rect.size, diff_data), self.rect, alpha=False)

    def __repr__(self):
        return f"{__class__}(index={self.index}, data={len(self.data)}B)"


@dataclass(frozen=True)
class LayerFlipEdit(Edit):

    "Mirror layer. This is a non-destructive operation, so we don't have to store any of the data."

    index: int
    horizontal: bool

    def perform(self, drawing):
        layer = drawing.layers[self.index]
        if self.horizontal:
            layer.flip_horizontal()
        else:
            layer.flip_vertical()

    undo = perform  # Mirroring is it's own inverse!

    def __repr__(self):
        return f"{__class__}(index={self.index}, horizontal={self.horizontal})"


@dataclass(frozen=True)
class PaletteEdit(Edit):

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
            drawing.palette[i] = r0 - dr, g0 - dg, b0 - db, a0 - da


@dataclass(frozen=True)
class AddLayerEdit(Edit):

    index: int
    size: tuple
    data: bytes

    @classmethod
    def create(cls, drawing, layer, index):
        return cls(index=index, data=zlib.compress(layer.pic.data), size=layer.size)

    def perform(self, drawing):
        layer = Layer(LongPicture(size=self.size, data=zlib.decompress(self.data)))
        drawing.layers.add(layer, index=self.index)

    def undo(self, drawing):
        layer = drawing.layers[self.index]
        drawing.layers.remove(layer)

    def __repr__(self):
        return f"{__class__}(index={self.index}, data={len(self.data)}B, size={self.size})"


@dataclass(frozen=True)
class RemoveLayerEdit(Edit):

    index: int
    size: tuple
    data: bytes

    @classmethod
    def create(cls, drawing, layer):
        index = drawing.layers.index(layer)
        return cls(index=index, data=zlib.compress(layer.pic.data), size=layer.size)

    # This is the inverse operation of adding a layer
    perform = AddLayerEdit.undo
    undo = AddLayerEdit.perform

    def __repr__(self):
        return f"{__class__}(index={self.index}, data={len(self.data)}B, size={self.size})"


@dataclass(frozen=True)
class SwapLayersEdit(Edit):

    index1: int
    index2: int

    def perform(self, drawing):
        drawing.layers.swap(self.index1, self.index2)

    undo = perform
