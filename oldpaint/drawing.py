from contextlib import contextmanager
from functools import lru_cache
import logging
import os
import shutil
from uuid import uuid4

import numpy as np
from pyglet import clock

from .brush import PicBrush
from .config import get_autosave_filename, get_autosaves
from .edit import (LayerEdit, LayerClearEdit, DrawingCropEdit, LayerFlipEdit,
                   AddFrameEdit, RemoveFrameEdit,
                   MoveFrameForwardEdit, MoveFrameBackwardEdit,
                   DrawingFlipEdit, PaletteEdit, AddLayerEdit,
                   RemoveLayerEdit, SwapLayersEdit, MergeLayersEdit,
                   SwapColorsImageEdit, SwapColorsPaletteEdit,
                   MultiEdit)
from .layer import Layer, TemporaryLayer
from .ora import load_ora, save_ora, load_png, save_png
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
    
    def __init__(self, size, layers=None, palette=None, path=None, selection=None, framerate=10, **kwargs):
        if kwargs:
            logger.warning("Ignoring the following arguments: %r", kwargs)
        self.size = size
        if layers:
            self.layers = Selectable(layers)
        else:
            self.layers = Selectable([Layer(size=self.size)])
        self.palette = palette if palette else Palette(transparency=0)

        # Animation related things
        self.frame = 0
        self.n_frames = max(1, *(len(l.frames) for l in self.layers))
        self.framerate = framerate
        self.playing_animation = False
        
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

    @property
    def locked(self):
        "Whether the drawing is locked for editing."
        return self.playing_animation
    
    @classmethod
    def from_spec(cls, spec):
        if spec.endswith(".ora"):
            return cls.from_ora(spec)
        if spec.endswith(".png"):
            return cls.from_png(spec)
        
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
            combined = self.layers[0].get_data(self.frame).copy()
        else:
            combined = np.zeros(self.size, dtype=self.layers[0].dtype)
        for layer in self.layers[1:]:
            if layer.visible:
                data = layer.get_data(self.frame)
                mask = data.astype(np.bool)
                # TODO Should be doable without copying
                combined = np.where(mask, data, combined)
        with open(path, "wb") as f:
            save_png(combined, f, palette=self.palette.colors)

    @classmethod
    def from_ora(cls, path):
        """Load a complete drawing from an ORA file."""
        layer_pics, info, kwargs = load_ora(path)
        palette = Palette(info["palette"], transparency=0)
        layers = [Layer(frames, visible=visibility)
                  for frames, visibility in layer_pics]
        return cls(size=layers[0].size, layers=layers, palette=palette, path=path, **kwargs)

    def load_ora(self, path):
        """ Replace the current data with data from an ORA file. """
        layer_pics, info, kwargs = load_ora(path)
        layers = [Layer(frames, visible=visibility)
                  for frames, visibility in layer_pics]

        def diff_colors(c1, c2):
            r1, g1, b1, a1 = c1
            r2, g2, b2, a2 = c2
            return r2 - r1, g2 - g1, b2 - b1, a2 - a1
        
        color_diffs = [(i, *diff_colors(c1, c2))
                       for i, (c1, c2) in enumerate(zip(self.palette, info["palette"]))
                       if c1 != c2]
        edit = MultiEdit([
            *(RemoveLayerEdit.create(self, l) for l in self.layers),
            *(AddLayerEdit.create(self, l, i) for i, l in enumerate(layers)),
            PaletteEdit(diffs=color_diffs)
        ])
        self._make_edit(edit)
    
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
        save_ora(self.size, self.layers, self.palette, tmp_path,
                 selection=selection, framerate=self.framerate)
        shutil.move(tmp_path, path)

    def autosave(self):
        path = self.path or self.uuid
        auto_filename = get_autosave_filename(path)
        self.save_ora(str(auto_filename), auto=True)
        return auto_filename

    def get_autosaves(self):
        return list(get_autosaves(self.path or self.uuid))

    def crop(self, rect):
        edit = DrawingCropEdit.create(self, rect)
        self._make_edit(edit)
        self.selection = None

    @property
    def is_animated(self):
        return self.n_frames > 1
        
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
        self._make_edit(edit)
         
        self.frame = frame
 
    def remove_frame(self, frame=None):
        frame = frame if frame is not None else self.frame
        edit = MultiEdit([
            RemoveFrameEdit.create(layer.frames[frame], self.size, i, frame)
            for i, layer in enumerate(self.layers)
        ])
        self._make_edit(edit)

    def move_frame_forward(self, layer=None, frame=None):
        layer = layer if layer is not None else self.layers.index()
        frame = frame if frame is not None else self.frame
        edit = MoveFrameForwardEdit.create(index=layer, frame=frame)
        self._make_edit(edit)
        
    def move_frame_backward(self, layer=None, frame=None):
        layer = layer if layer is not None else self.layers.index()
        frame = frame if frame is not None else self.frame
        edit = MoveFrameBackwardEdit.create(index=layer, frame=frame)
        self._make_edit(edit)
        
    def next_frame(self):
        self.frame = (self.frame + 1) % self.n_frames

    def prev_frame(self):
        self.frame = (self.frame - 1) % self.n_frames

    def first_frame(self):
        self.frame = 0

    def last_frame(self):
        self.frame = self.n_frames - 1

    def start_animation(self):
        clock.schedule_interval(self._next_frame_callback, 1 / self.framerate)
        self.playing_animation = True

    def stop_animation(self):
        clock.unschedule(self._next_frame_callback)
        self.playing_animation = False

    def set_framerate(self, framerate):
        self.framerate = framerate
        self.stop_animation()
        self.start_animation()

    def _next_frame_callback(self, dt):
        self.next_frame()
        
    def add_layer(self, index=None, layer=None):
        layer = layer or Layer(size=self.size)
        index = (index if index is not None else self.layers.get_current_index()) + 1

        edit = AddLayerEdit.create(self, layer, index)
        self._make_edit(edit)
        self.layers.select_index(index)

    def remove_layer(self, index=None):
        if len(self.layers) == 1:
            return
        index = index or self.layers.get_current_index()
        layer = self.layers[index]
        edit = RemoveLayerEdit.create(self, layer)
        self._make_edit(edit)

    def next_layer(self):
        self.layers.cycle_forward()

    def prev_layer(self):
        self.layers.cycle_backward()

    def move_layer_up(self):
        index1 = self.layers.get_current_index()
        if index1 < (len(self.layers) - 1):
            index2 = index1 + 1
            edit = SwapLayersEdit(index1, index2)
            self._make_edit(edit)

    def move_layer_down(self):
        index1 = self.layers.get_current_index()
        if 0 < index1:
            index1 = self.layers.get_current_index()
            index2 = index1 - 1
            edit = SwapLayersEdit(index1, index2)
            self._make_edit(edit)

    def clear_layer(self, layer=None, color=0, frame=None):
        layer = layer or self.current
        frame = frame if frame is not None else self.frame
        edit = LayerClearEdit.create(self, layer, frame, color=color)
        self._make_edit(edit)

    @try_except_log
    def merge_layers(self, layer1, layer2, frame):
        edit = MergeLayersEdit.create(self, layer1, layer2, frame)
        self._make_edit(edit)

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
        self._make_edit(edit)
        
    def flip_horizontal(self):
        self.flip(True)
        
    def flip_vertical(self):
        self.flip(False)

    def flip_layer(self, layer, horizontal):
        "Mirror a single layer."
        layer = layer or self.current
        edit = LayerFlipEdit(self.layers.index(layer), horizontal)
        self._make_edit(edit)
        
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
        self._make_edit(edit)

    @try_except_log
    def change_colors(self, *colors):
        """ Change any number of colors in the palette at once, as a single undoable edit. """
        diffs = []
        for i, (r1, g1, b1, a1) in colors:
            r0, g0, b0, a0 = self.palette[i]
            delta = r1-r0, g1-g0, b1-b0, a1-a0
            diffs.append((i, *delta))
        edit = PaletteEdit(diffs)
        self._make_edit(edit)

    def swap_colors(self, index1, index2, image_only=False):
        """ Change places between two colors in the palette. """
        if image_only:
            edit = SwapColorsImageEdit(index1, index2)
        else:
            edit = SwapColorsPaletteEdit.create(index1=index1, index2=index2)
        self._make_edit(edit)

    def make_brush(self, frame=None, rect=None, layer=None, clear=False):
        "Create a brush from part of the given layer."
        rect = rect or self.selection
        frame = frame if frame is not None else self.frame
        if rect.area() == 0:
            return
        layer = self.layers[layer] if layer is not None else self.current
        rect = layer.rect.intersect(rect)
        subimage = layer.get_subimage(rect, frame=frame)
        if clear:
            edit = LayerClearEdit.create(self, layer, frame, rect,
                                         color=self.palette.background)
            self._make_edit(edit)
        brush = PicBrush(data=subimage)
        self.brushes.append(brush)

    def copy_layer(self, frame=None, layer=None):
        frame = frame if frame is not None else self.frame
        layer = layer or self.current
        return layer.get_subimage(layer.rect, frame)
    
    def _make_edit(self, edit):
        """ Perform an edit and insert it into the history, keeping track of things """
        edit.perform(self)
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
        else:
            logger.info("No more edits to undo!")

    @try_except_log
    def redo(self):
        "Restore the drawing to the state it was in after the current edit was made."
        if self._edits_index < -1:
            self._edits_index += 1
            edit = self._edits[self._edits_index]
            edit.perform(self)
        else:
            logger.info("No more edits to redo!")

    # Drawing helpers, for scripting/plugin use

    @contextmanager
    def edit(self):
        maker = EditMaker(self)
        yield maker
        maker.finish()
        self._make_edit(MultiEdit(maker.edits))

    def __repr__(self):
        return f"Drawing(size={self.size}, layers={self.layers}, current={self.layers.index()})"

    def __iter__(self):
        return iter(self.layers)

    def __del__(self):
        self.stop_animation()


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
