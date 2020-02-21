# Edit classes; immutable objects that represent an individual change of the drawing.

from dataclasses import dataclass
import struct
import zlib

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
class LayerEdit(Edit):

    "A change in the image data of a particular layer."

    _type = 0
    _struct = "cchhhh"
    _structsize = struct.calcsize(_struct)

    index: int
    tool: int
    rect: Rectangle
    data: bytes

    @classmethod
    def create(cls, drawing, orig_layer, edit_layer, rect, tool=0):
        "Helper to handle compressing the data."
        data = orig_layer.make_diff(edit_layer, rect, alpha=False)
        index = drawing.layers.index(orig_layer)
        return cls(index=index, tool=tool, data=zlib.compress(data), rect=rect)

    def perform(self, drawing):
        layer = drawing.layers[self.index]
        diff_data = zlib.decompress(self.data)
        layer.apply_diff(memoryview(diff_data).cast("h"), self.rect, False)

    def revert(self, drawing):
        layer = drawing.layers[self.index]
        diff_data = zlib.decompress(self.data)
        layer.apply_diff(memoryview(diff_data).cast("h"), self.rect, True)

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
            data = orig_layer.get_subimage(rect).data
        else:
            data = orig_layer.pic.data
            rect = orig_layer.rect
        index = drawing.layers.index(orig_layer)
        return cls(index=index, data=zlib.compress(data), rect=rect, color=color)

    def perform(self, drawing):
        layer = drawing.layers[self.index]
        layer.clear(self.rect, value=self.color)

    def revert(self, drawing):
        layer = drawing.layers[self.index]
        diff_data = zlib.decompress(self.data)
        layer.blit(LongPicture(self.rect.size, diff_data), self.rect, alpha=False)

    @property
    def index_str(self):
        return f"{self.index}"

    @property
    def info_str(self):
        return f"Clear"

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
class PaletteColorSwap(Edit):

    "A swap between two colors in the palette."

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
        return "Palette color swap"


@dataclass(frozen=True)
class DrawingColorSwap(Edit):

    "A swap between two colors in the palette."

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
        return "Drawing color swap"


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
        return cls(index=index, data=zlib.compress(layer.pic.data), size=layer.size)

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


class MergeLayersEdit(MultiEdit):

    @classmethod
    def create(cls, drawing, source_layer, destination_layer):
        source_layer.pic.fix_alpha(set(drawing.palette.transparent_colors))
        return cls([
            LayerEdit.create(drawing, destination_layer, source_layer, source_layer.rect),
            RemoveLayerEdit.create(drawing, source_layer)
        ])

    @property
    def index_str(self):
        return f"{self.edits[1].index}, {self.edits[0].index}"

    @property
    def info_str(self):
        return "Merge layers"


class ColorSwap(MultiEdit):

    @classmethod
    def create(cls, drawing, index1, index2):
        return cls([
            PaletteColorSwap(index1=index1, index2=index2),
            DrawingColorSwap(index1=index1, index2=index2)
        ])

    @property
    def index_str(self):
        return f"{self.edits[0].index1}, {self.edits[0].index2}"

    @property
    def info_str(self):
        return "Swap colors"
