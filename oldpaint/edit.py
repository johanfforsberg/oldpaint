"""
Edit classes.

An edit is an immutable object that represent an individual change of the drawing.
It can be applied and reverted.

Ordering is very important. In general, an edit can only be correctly applied when
the drawing is in the state when it was created, and only reverted from the state
right after it was applied.
"""

import pickle
from dataclasses import dataclass
import struct
import zlib

import numpy as np

from .constants import ToolName
from .layer import Layer
from .picture import LongPicture
from .rect import Rectangle


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

    @property
    def layer_str(self):
        return ""

    @property
    def info_str(self):
        return ""


@dataclass(frozen=True)
class MultiEdit:

    "An edit that consists of several other edits in sequence."

    edits: list

    def perform(self, drawing):
        for edit in self.edits:
            edit.perform(drawing)

    def revert(self, drawing):
        for edit in reversed(self.edits):
            edit.revert(drawing)

    @property
    def index_str(self):
        return f"{len(self.edits)}"

    @property
    def info_str(self):
        return "Merged edits"


@dataclass(frozen=True)
class LayerEdit(Edit):

    "A change in the image data of a particular layer."

    # TODO the stuff below is WIP for a way to store the data in a struct

    _type = 0
    _struct = "cchhhh"
    _structsize = struct.calcsize(_struct)

    frame: int
    index: int
    tool: int
    rect: Rectangle
    data: bytes

    @classmethod
    def create(cls, drawing, orig_layer, edit_layer, frame, rect, tool=0):
        "Helper to handle compressing the data."
        data = orig_layer.make_diff(edit_layer, rect, alpha=False, frame=frame).tobytes()
        index = drawing.layers.index(orig_layer)
        return cls(frame=frame, index=index, tool=tool, data=zlib.compress(data), rect=rect)

    def perform(self, drawing):
        layer = drawing.layers[self.index]
        diff_data = np.frombuffer(zlib.decompress(self.data), dtype=np.int16).reshape(self.rect.size)
        layer.apply_diff(diff_data, self.rect, False, frame=self.frame)

    def revert(self, drawing):
        layer = drawing.layers[self.index]
        diff_data = np.frombuffer(zlib.decompress(self.data), dtype=np.int16).reshape(self.rect.size)
        layer.apply_diff(-diff_data, self.rect, True, frame=self.frame)

    # @classmethod
    # def merge(self, edits):
    #     "Combine a bunch of layer edits into one single edit."
    #     total_rect = cover([e.rect for e in edits])
    #     layer = Layer(size=total_rect.size)
    #     dx, dy = total_rect.position
    #     offset = (-dx, -dy)
    #     for edit in edits:
    #         rect = Rectangle.offset(offset)
    #         layer.blit(edit.data, rect)

    @property
    def index_str(self):
        return f"{self.index}"

    @property
    def info_str(self):
        return ToolName(self.tool).name if self.tool else ''

    def __repr__(self):
        return f"{__class__}(index={self.index}, tool={self.tool})"


@dataclass(frozen=True)
class LayerClearEdit(Edit):

    index: int
    rect: Rectangle
    color: int
    data: bytes

    @classmethod
    def create(cls, drawing, orig_layer, rect=None, color=0):
        if rect:
            data =  [orig_layer.get_subimage(rect)]
        else:
            data = orig_layer.frames
            rect = orig_layer.rect
        index = drawing.layers.index(orig_layer)
        return cls(index=index, data=zlib.compress(data), rect=rect, color=color)

    def perform(self, drawing):
        layer = drawing.layers[self.index]
        layer.clear(self.rect, value=self.color)

    def revert(self, drawing):
        layer = drawing.layers[self.index]
        data = np.frombuffer(zlib.decompress(self.data), dtype=np.uint8).reshape(self.rect.size)
        layer.apply_diff(data, self.rect)

    @property
    def index_str(self):
        return f"{self.index}"

    @property
    def info_str(self):
        return f"Clear"

    def __repr__(self):
        return f"{__class__}(index={self.index}, data={len(self.data)})"


@dataclass(frozen=True)
class LayerCropEdit(Edit):

    index: int
    rect: Rectangle
    orig_size: tuple
    data: bytes

    @classmethod
    def create(cls, drawing, orig_layer, rect):
        data = orig_layer.pic.data
        index = drawing.layers.index(orig_layer)
        return cls(index=index, data=zlib.compress(data), rect=rect, orig_size=orig_layer.size)

    def perform(self, drawing):
        layer = drawing.layers[self.index]
        drawing.layers[self.index] = layer.crop(self.rect)

    def revert(self, drawing):
        data = zlib.decompress(self.data)
        drawing.layers[self.index] = Layer(pic=LongPicture(self.orig_size, data))

    @property
    def index_str(self):
        return f"{self.index}"

    @property
    def info_str(self):
        return f"Crop layer"

    def __repr__(self):
        return f"{__class__}(index={self.index}, data={len(self.data)}, rect={self.rect})"
        

class DrawingCropEdit(MultiEdit):

    @classmethod
    def create(cls, drawing, rect):
        return cls([
            LayerCropEdit.create(drawing, layer, rect)
            for layer in drawing.layers
        ])

    def perform(self, drawing):
        super().perform(drawing)
        drawing.size = self.edits[0].rect.size

    def revert(self, drawing):
        super().revert(drawing)
        drawing.size = self.edits[0].orig_size
        
    @property
    def index_str(self):
        return f"Crop(rect={self.rect})"

    @property
    def info_str(self):
        return "Crop drawing"

     
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

    revert = perform  # Mirroring is it's own inverse!

    @property
    def index_str(self):
        return f"{self.index}"

    @property
    def info_str(self):
        return f"Flip " + ("horizontal" if self.horizontal else "vertical")

    def __repr__(self):
        return f"{__class__}(index={self.index}, horizontal={self.horizontal})"


@dataclass(frozen=True)
class DrawingFlipEdit(Edit):

    "Mirror layer. This is a non-destructive operation, so we don't have to store any of the data."

    horizontal: bool

    def perform(self, drawing):
        for layer in drawing.layers:
            if self.horizontal:
                layer.flip_horizontal()
            else:
                layer.flip_vertical()

    revert = perform  # Mirroring is it's own inverse!

    @property
    def info_str(self):
        return f"Flip " + ("horizontal" if self.horizontal else "vertical")

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

    def revert(self, drawing):
        for i, (dr, dg, db, da) in enumerate(self.data, start=self.index):
            r0, g0, b0, a0 = drawing.palette.colors[i]
            drawing.palette[i] = r0 - dr, g0 - dg, b0 - db, a0 - da

    @property
    def index_str(self):
        return str(self.index)

    @property
    def info_str(self):
        return "Color"


@dataclass(frozen=True)
class AddLayerEdit(Edit):

    index: int
    size: tuple
    data: bytes

    @classmethod
    def create(cls, drawing, layer, index):
        return cls(index=index, data=zlib.compress(pickle.dumps(layer.frames)), size=layer.size)

    def perform(self, drawing):
        frames = pickle.loads(zlib.decompress(self.data))
        layer = Layer(frames=frames, size=self.size)
        drawing.layers.add(layer, index=self.index)

    def revert(self, drawing):
        layer = drawing.layers[self.index]
        drawing.layers.remove(layer)

    @property
    def index_str(self):
        return f"{self.index}"

    @property
    def info_str(self):
        return f"Add layer"

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
        return cls(index=index, data=zlib.compress(pickle.dumps(layer.frames)), size=layer.size)

    # This is the inverse operation of adding a layer
    perform = AddLayerEdit.revert
    revert = AddLayerEdit.perform

    @property
    def index_str(self):
        return f"{self.index}"

    @property
    def info_str(self):
        return f"Remove layer"

    def __repr__(self):
        return f"{__class__}(index={self.index}, data={len(self.data)}B, size={self.size})"


@dataclass(frozen=True)
class SwapLayersEdit(Edit):

    index1: int
    index2: int

    def perform(self, drawing):
        drawing.layers.swap(self.index1, self.index2)

    @property
    def index_str(self):
        return f"{self.index1}, {self.index2}"

    @property
    def info_str(self):
        return f"Swap layers"

    revert = perform


class MergeLayersEdit(MultiEdit):

    @classmethod
    def create(cls, drawing, source_layer, destination_layer, frame):
        # source_layer.pic.fix_alpha(set(drawing.palette.transparent_colors))
        return cls([
            LayerEdit.create(drawing, destination_layer, source_layer, frame, source_layer.rect),
            RemoveLayerEdit.create(drawing, source_layer)
        ])

    @property
    def index_str(self):
        return f"{self.edits[1].index}, {self.edits[0].index}"

    @property
    def info_str(self):
        return "Merge layers"


@dataclass(frozen=True)
class SwapColorsEdit(Edit):

    "A swap between two colors in the palette, also affecting the image."

    index1: int
    index2: int

    def perform(self, drawing):
        palette = drawing.palette
        palette[self.index1], palette[self.index2] = palette[self.index2], palette[self.index1]

    revert = perform

    @property
    def index_str(self):
        return f"{self.index1}, {self.index2}"

    @property
    def info_str(self):
        return "Swap colors"


@dataclass(frozen=True)
class SwapColorsImageEdit(Edit):

    "A swap between two colors in the image."

    index1: int
    index2: int

    def perform(self, drawing):
        for layer in drawing.layers:
            layer.swap_colors(self.index1, self.index2)

    revert = perform

    @property
    def index_str(self):
        return f"{self.index1}, {self.index2}"

    @property
    def info_str(self):
        return "Swap image colors"


class SwapColorsPaletteEdit(MultiEdit):

    """
    Change places between two colors in the palette, without affecting
    the image.
    """

    @classmethod
    def create(cls, index1, index2):
        return cls([
            SwapColorsEdit(index1=index1, index2=index2),
            SwapColorsImageEdit(index1=index1, index2=index2)
        ])

    @property
    def index_str(self):
        return f"{self.edits[0].index1}, {self.edits[0].index2}"

    @property
    def info_str(self):
        return "Swap palette colors"


 
