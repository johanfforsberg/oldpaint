from dataclasses import dataclass, field
from enum import Enum
import logging
import os
import shutil
import struct
import zlib

from .brush import PicBrush
from .layer import Layer
from .ora import load_ora, save_ora
from .picture import LongPicture, load_png, save_png
from .palette import Palette
from .rect import Rectangle

from .util import Selectable, try_except_log


logger = logging.getLogger(__name__)


class ToolName(Enum):
    PENCIL = 1
    POINTS = 2
    SPRAY = 3
    LINE = 4
    RECTANGLE = 5
    ELLIPSE = 6
    FLOODFILL = 7
    BRUSH = 8
    PICKER = 9


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
        self.active_plugins = {}

        # History of changes
        self._edits = []
        self._edits_index = -1
        self._latest_save_index = 0

        self.selections = Selectable()
        self.show_selection = False

        # Keep track of what we're looking at
        self.offset = (0, 0)
        self.zoom = 0

        self.path = path

    @property
    def current(self) -> Layer:
        return self.layers.current

    @current.setter
    def current(self, layer):
        assert isinstance(layer, Layer)
        self.layers.set_item(layer)

    @property
    def selection(self):
        if self.show_selection:
            return self.selections.current

    @property
    def filename(self):
        return os.path.basename(self.path) if self.path else "[Unnamed]"

    @property
    def edits(self):
        if self._edits_index == -1:
            return self._edits
        return self._edits[:self._edits_index + 1]

    @property
    def can_undo(self):
        return bool(self.edits)

    @property
    def can_redo(self):
        return self._edits_index != -1

    @property
    def unsaved(self):
        "Return whether there have been edits since last time the drawing was saved."
        return self._latest_save_index < len(self._edits)

    @classmethod
    def from_png(cls, path):
        """Load a PNG into a single layer drawing."""
        pic, colors = load_png(path)
        layer = Layer(pic)
        palette = Palette(colors, transparency=0, size=len(colors))
        return cls(size=layer.size, layers=[layer], palette=palette, path=path)

    def save_png(self, path):
        """Save as a single PNG file. Flattens all visible layers into one image."""
        if self.layers[0].visible:
            combined = self.layers[0].clone()
        else:
            combined = Layer(size=self.size)
        transparent_colors = set(self.palette.transparent_colors)
        for layer in self.layers[1:]:
            if layer.visible:
                layer.pic.fix_alpha(transparent_colors)
                combined.blit(layer.pic, layer.rect)
        with open(path, "wb") as f:
            save_png(combined.pic, f, palette=self.palette.colors)

    @classmethod
    def from_ora(cls, path):
        """Load a complete drawing from an ORA file."""
        layer_pics, colors = load_ora(path)
        palette = Palette(colors, transparency=0)
        layers = [Layer(p) for p in reversed(layer_pics)]
        return cls(size=layers[0].size, layers=layers, palette=palette, path=path)

    def save_ora(self, path=None):
        """Save in ORA format, which keeps all layers intact."""
        if path is None and self.path:
            self._save_ora(self.path)
        elif path:
            self._save_ora(path)
            self.path = path
        else:
            raise RuntimeError("Can't save without path")
        self._latest_save_index = len(self._edits)

    def _save_ora(self, path):
        """
        Save the drawing in a temporary file before moving it to the path
        This should prevent us from leaving the user with a broken file in case
        something bad happens while writing.
        """
        tmp_path = path + ".tmp"
        save_ora(self.size, self.layers, self.palette, tmp_path)
        shutil.move(tmp_path, path)

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

    @try_except_log
    def merge_layers(self, layer1, layer2):
        edit = MergeLayersEdit.create(self, layer1, layer2)
        edit.perform(self)
        self._add_edit(edit)

    def merge_layer_down(self, layer=None):
        layer1 = layer or self.layers.current
        index = self.layers.index(layer1)
        if index > 0:
            layer2 = self.layers[index - 1]
            self.merge_layers(layer1, layer2)

    def flip_horizontal(self):
        edit = DrawingFlipEdit(True)
        edit.perform(self)
        self._add_edit(edit)

    def flip_vertical(self):
        edit = DrawingFlipEdit(False)
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
    def change_layer(self, new, rect, tool=None, layer=None):
        "Update a part of the layer, keeping track of the change as an 'undo'"
        layer = layer or self.current
        edit = LayerEdit.create(self, layer, new, rect, tool.value if tool else 0)
        edit.perform(self)
        self._add_edit(edit)

    @try_except_log
    def change_colors(self, i, colors):
        data = []
        for j, color in enumerate(colors):
            r0, g0, b0, a0 = self.palette[i + j]
            r1, g1, b1, a1 = color
            delta = r1-r0, g1-g0, b1-b0, a1-a0
            data.append(delta)
        edit = PaletteEdit(index=i, data=data)
        edit.perform(self)
        self._add_edit(edit)

    def swap_colors(self, index1, index2):
        edit = ColorSwap.create(self, index1=index1, index2=index2)
        edit.perform(self)
        self._add_edit(edit)

    def make_brush(self, rect=None, layer=None, clear=False):
        "Create a brush from part of the given layer."
        rect = rect or self.selection
        if rect.area() == 0:
            return
        layer = layer or self.current
        rect = layer.rect.intersect(rect)
        subimage = layer.get_subimage(rect)
        subimage.fix_alpha(set(self.palette.transparent_colors))
        if clear:
            edit = LayerClearEdit.create(self, layer, rect,
                                         color=self.palette.background)
            edit.perform(self)
            self._add_edit(edit)
        brush = PicBrush(subimage)
        self.brushes.append(brush)

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
            edit.revert(self)
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

    # Drawing helpers, for scripting/plugin use

    def draw_rectangle(self, rect, brush, color=None):
        color = color or self.palette.foreground
        rect = self.overlay.draw_rectangle(rect.position, rect.size, brush.get_pic(color), brush.center)
        self.change_layer(self.overlay, rect, ToolName.RECTANGLE)
        self.overlay.clear()

    # ...TODO...

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
