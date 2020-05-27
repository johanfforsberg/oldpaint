from contextlib import contextmanager
from functools import lru_cache
import logging
import os
import shutil
from uuid import uuid4

import numpy as np
from pyglet import clock

from .brush import PicBrush
from .constants import ToolName
from .edit import (LayerEdit, LayerClearEdit, DrawingCropEdit, LayerFlipEdit,
                   AddFrameEdit, RemoveFrameEdit,
                   DrawingFlipEdit, PaletteEdit, AddLayerEdit,
                   RemoveLayerEdit, SwapLayersEdit, MergeLayersEdit,
                   SwapColorsImageEdit, SwapColorsPaletteEdit,
                   MultiEdit)
from .layer import Layer, TemporaryLayer
from .ora import load_ora, save_ora, load_png, save_png
# from .picture import LongPicture, load_png, save_png
from .palette import Palette
from .rect import Rectangle

from .util import Selectable, try_except_log


logger = logging.getLogger(__name__)


class Drawing:

    """
    The "drawing" is a bunch of images with the same size and palette,
    stacked on top of each other (from the bottom). They are referred to as
    "layers".

    This is also where most functionality that affects the image is collected,
    e.g. drawing, undo/redo, load/save...

    Since several drawings can be loaded at once, we also need to keep track
    of view position and such for each drawing.

    IMPORTANT! It's a bad idea to directly modify the layers! Always
    use the corresponding methods in this class instead. Otherwise you will
    mess up the undo history beyond repair.
    """
    
    def __init__(self, size, layers=None, palette=None, path=None, selection=None):
        self.size = size
        if layers:
            self.layers = Selectable(layers)
        else:
            self.layers = Selectable([Layer(size=self.size)])
        self.palette = palette if palette else Palette(transparency=0)

        self.frame = 0
        self.n_frames = max(1, *(len(l.frames) for l in self.layers))
        
        self.brushes = Selectable()

        self.active_plugins = {}
        
        # History of changes
        self._edits = []
        self._edits_index = -1
        self._latest_save_index = 0

        self.selection = Rectangle.from_dict(selection) if selection else None
        self.only_show_current_layer = False

        # Keep track of what we're looking at
        self.offset = (0, 0)
        self.zoom = 0

        self.path = path
        self.uuid = str(uuid4())

    @property
    def current(self) -> Layer:
        return self.layers.current

    @current.setter
    def current(self, layer):
        assert isinstance(layer, Layer)
        self.layers.set_item(layer)

    @property
    def overlay(self):
        return self._get_overlay(self.size)

    @lru_cache(1)
    def _get_overlay(self, size):
        return TemporaryLayer(size=size)
    
    @property
    def visible_layers(self):
        if self.only_show_current_layer:
            return [self.current]
        return [layer for layer in self.layers if layer.visible]
    
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
        pic, info = load_png(path)
        layer = Layer([pic])
        colors = info["palette"]
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
                layer.pic.fix_alpha(transparent_colors)  # TODO
                combined.blit(layer.pic, layer.rect)
        with open(path, "wb") as f:
            save_png(combined.pic, f, palette=self.palette.colors)

    @classmethod
    def from_ora(cls, path):
        """Load a complete drawing from an ORA file."""
        layer_pics, info, kwargs = load_ora(path)
        palette = Palette(info["palette"], transparency=0)
        layers = [Layer(frames, visible=visibility)
                  for frames, visibility in layer_pics]
        return cls(size=layers[0].size, layers=layers, palette=palette, path=path)

    def save_ora(self, path=None, auto=False):
        """Save in ORA format, which keeps all layers intact."""
        if path is None and self.path:
            self._save_ora(self.path)
        elif path:
            self._save_ora(path)
            if not auto:
                self.path = path
        else:
            raise RuntimeError("Can't save without path")
        if not auto:
            self._latest_save_index = len(self._edits)

    def _save_ora(self, path):
        """
        Save the drawing in a temporary file before moving it to the path
        This should prevent us from leaving the user with a broken file in case
        something bad happens while writing.
        """
        tmp_path = path + ".tmp"
        selection = self.selection.as_dict() if self.selection else None
        save_ora(self.size, self.layers, self.palette, tmp_path, selection=selection)
        shutil.move(tmp_path, path)

    def crop(self, rect):
        edit = DrawingCropEdit.create(self, rect)
        edit.perform(self)
        self._add_edit(edit)
        self.selection = None

    def add_frame(self, frame=None, copy=False):
        frame = frame if frame is not None else self.frame + 1
        if copy:
            # TODO does not seem to work
            edit = MultiEdit([
                AddFrameEdit.create(layer.frames[self.frame], self.size, i, frame)
                for i, layer in enumerate(self.layers)
            ])
        else:
            edit = MultiEdit([
                AddFrameEdit.create(None, self.size, i, frame)
                for i, layer in enumerate(self.layers)
            ])
        edit.perform(self)
        self._add_edit(edit)
         
        self.frame = frame
 
    def remove_frame(self, frame=None):
        frame = frame if frame is not None else self.frame
        edit = MultiEdit([
            RemoveFrameEdit.create(layer.frames[frame], self.size, i, frame)
            for i, layer in enumerate(self.layers)
        ])
        edit.perform(self)
        self._add_edit(edit)

    def next_frame(self):
        self.frame = (self.frame + 1) % self.n_frames

    def prev_frame(self):
        self.frame = (self.frame - 1) % self.n_frames

    def first_frame(self):
        self.frame = 0

    def last_frame(self):
        self.frame = self.n_frames - 1
        
    def add_layer(self, index=None, layer=None):
        layer = layer or Layer(size=self.size)
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

    def clear_layer(self, layer=None, color=0, frame=None):
        layer = layer or self.current
        frame = frame if frame is not None else self.frame
        edit = LayerClearEdit.create(self, layer, frame, color=color)
        edit.perform(self)
        self._add_edit(edit)

    @try_except_log
    def merge_layers(self, layer1, layer2, frame):
        edit = MergeLayersEdit.create(self, layer1, layer2, frame)
        edit.perform(self)
        self._add_edit(edit)

    def merge_layer_down(self, layer=None, frame=None):
        "Combine a layer with the layer below it, by superpositioning."
        layer1 = layer or self.layers.current
        index = self.layers.index(layer1)
        frame = frame if frame is not None else self.frame
        if index > 0:
            layer2 = self.layers[index - 1]
            self.merge_layers(layer1, layer2, frame)

    def flip(self, horizontal):
        "Mirror all layers."
        edit = DrawingFlipEdit(horizontal)
        edit.perform(self)
        self._add_edit(edit)
        
    def flip_horizontal(self):
        self.flip(True)
        
    def flip_vertical(self):
        self.flip(False)

    def flip_layer(self, layer, horizontal):
        "Mirror a single layer."
        layer = layer or self.current
        edit = LayerFlipEdit(self.layers.index(layer), horizontal)
        edit.perform(self)
        self._add_edit(edit)
        
    def flip_layer_horizontal(self, layer=None):
        self.flip_layer(layer, True)

    def flip_layer_vertical(self, layer=None):
        self.flip_layer(layer, False)

    @try_except_log
    def change_layer(self, new, rect, tool=None, layer=None, frame=None):
        "Update a part of the layer, keeping track of the change as an 'undo'"
        layer = layer or self.current
        frame = frame if frame is not None else self.frame
        edit = LayerEdit.create(self, layer, new, frame, rect, tool.value if tool else 0)
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

    def swap_colors(self, index1, index2, image_only=False):
        if image_only:
            edit = SwapColorsImageEdit(index1, index2)
        else:
            edit = SwapColorsPaletteEdit.create(index1=index1, index2=index2)
        edit.perform(self)
        self._add_edit(edit)

    def make_brush(self, frame=None, rect=None, layer=None, clear=False):
        "Create a brush from part of the given layer."
        rect = rect or self.selection
        frame = frame or self.frame
        if rect.area() == 0:
            return
        layer = layer or self.current
        rect = layer.rect.intersect(rect)
        subimage = layer.get_subimage(rect, frame=frame)
        #subimage.fix_alpha(set(self.palette.transparent_colors))
        if clear:
            edit = LayerClearEdit.create(self, layer, rect,
                                         color=self.palette.background)
            edit.perform(self)
            self._add_edit(edit)
        brush = PicBrush(data=subimage)
        self.brushes.append(brush)

    def copy_layer(self, frame=None, layer=None):
        frame = frame if frame is not None else self.frame
        layer = layer or self.current
        return layer.get_subimage(layer.rect, frame)
    
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

    @contextmanager
    def edit(self):
        maker = EditMaker(self)
        yield maker
        maker.finish()
        self._add_edit(MultiEdit(maker.edits))

    def __repr__(self):
        return f"Drawing(size={self.size}, layers={self.layers}, current={self.get_index()})"

    def __iter__(self):
        return iter(self.layers)


class EditMaker():

    def __init__(self, drawing: Drawing):
        self.drawing = drawing
        self._rect = None
        self.edits = []

    def _push_layer_edit(self, rect):
        if self._rect:
            self._rect = self._rect.unite(rect)
        else:
            self._rect = rect

    def _cleanup(self):
        if self._rect:
            layer = self.drawing.current
            overlay = self.drawing.overlay
            edit = LayerEdit.create(self.drawing, layer, overlay, self._rect, 0)
            edit.perform(self.drawing)
            self.edits.append(edit)
            overlay.clear()
            self._rect = None

    def finish(self):
        self._cleanup()

    def draw_rectangle(self, position, size, brush, color=None, fill=False):
        rect = self.drawing.overlay.draw_rectangle(position, size, brush.get_pic(color), brush.center,
                                                   color=color, fill=fill)
        self._push_layer_edit(rect)

    def flip_layer_horizontal(self):
        self._cleanup()
        edit = LayerFlipEdit(self.drawing.layers.index(), horizontal=True)
        edit.perform(self.drawing)
        self.edits.append(edit)

    # ...TODO...
