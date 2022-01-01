"""
Utilities for working with OpenRaster files, as specified by https://www.openraster.org/
ORA is a simple, open format that can be loaded by some other graphics software,
e.g. Krita. Don't expect the opposite to be true in general though, as we have very
specific requirements.
"""

from typing import List, Tuple
import io
import json
import os
from shutil import copyfile
from tempfile import NamedTemporaryFile
from typing import List, Tuple, BinaryIO
import zipfile
from xml.etree import ElementTree as ET

import numpy as np
import png


def save_png(data, path, colors=None):
    with NamedTemporaryFile(prefix="oldpaint", delete=False) as f:
        _save_png(data, f, colors)
    copyfile(f.name, path)
    os.remove(f.name)


def _save_png(data: np.ndarray, dest: BinaryIO, colors=None):
    w, h = data.shape
    writer = png.Writer(w, h, bitdepth=8, alpha=False, palette=colors)
    rows = (data[:, i].tobytes() for i in range(data.shape[1]))
    writer.write(dest, rows)
    

def load_png(f: BinaryIO) -> Tuple[np.ndarray, dict]:
    reader = png.Reader(f)
    w, h, image_data, info = reader.read(f)
    assert info.get("palette"), "Sorry, can't load non palette based PNGs."
    return np.vstack(list(map(np.uint8, image_data))).T, info


def scale(data: np.ndarray, w: int, h: int) -> np.ndarray:
    w0, h0 = data.shape
    # w0 = len(im)     # source number of rows 
    # h0 = len(data[0])  # source number of columns 
    return np.array([
        [
            data[int(w0 * c / w)][int(h0 * r / h)]
            for r in range(h)
        ]
        for c in range(w)
    ])


def make_rgba_image(data: np.ndarray,
                    colors: List[Tuple[int, int, int, int]]) -> np.ndarray:
    rgba_data = []
    for row in data.T:
        rgba_row = []
        for pixel in row:
            rgba_pixel = colors[pixel]
            rgba_row.extend(rgba_pixel)
        rgba_data.append(rgba_row)
    return np.array(rgba_data, dtype=np.uint8).T


def save_ora(size: Tuple[int, int],
             layers: List["Layer"],
             colors: List[Tuple[int, int, int, int]],
             merged: np.ndarray,
             path: str,
             **kwargs):
    """
    An ORA file is basically a zip archive containing an XML manifest and a bunch of PNGs.
    It can however contain any other application specific data too.
    """
    w, h = size

    # Build "stack.xml" that specifies the structure of the drawing
    image_el = ET.Element("image", version="0.0.3", w=str(w), h=str(h))
    stack_el = ET.SubElement(image_el, "stack")
    has_empty_frame = False
    for i, layer in reversed(list(enumerate(layers))):
        visibility = "visible" if layer.visible else "hidden"
        if len(layer.frames) == 1:
            # Non-animated layer
            ET.SubElement(stack_el, "layer", name=f"layer{i}_frame{0}",
                          src=f"data/layer{i}_frame{0}.png")        
        else:
            # Animated layer
            layer_el = ET.SubElement(stack_el, "stack", name=f"layer{i}",
                                     visibility=visibility)
            for j, frame in reversed(list(enumerate(layer.frames))):
                if frame is not None:
                    ET.SubElement(layer_el, "layer", name=f"layer{i}_frame{j}",
                                  src=f"data/layer{i}_frame{j}.png")
                else:
                    ET.SubElement(layer_el, "layer", name=f"layer{i}_frame{j}",
                                  src=f"data/empty.png")
                    has_empty_frame = True
                    
    stack_xml = b"<?xml version='1.0' encoding='UTF-8'?>" + ET.tostring(image_el)

    # Create ZIP archive
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as orafile:
        orafile.writestr("mimetype", "image/openraster", compress_type=zipfile.ZIP_STORED)
        orafile.writestr("stack.xml", stack_xml)
        for i, layer in reversed(list(enumerate(layers))):
            for j, frame in reversed(list(enumerate(layer.frames))):
                if frame is not None:
                    with io.BytesIO() as f:
                        _save_png(frame, f, colors=colors)
                        f.seek(0)
                        orafile.writestr(f"data/layer{i}_frame{j}.png", f.read())
        if has_empty_frame:
            empty_frame = np.zeros(size, dtype=np.uint8)
            with io.BytesIO() as f:
                _save_png(empty_frame, f, colors=colors)
                f.seek(0)
                orafile.writestr(f"data/empty.png", f.read())

        # Thumbnail
        # Can be max 256 pixels in either dimension.
        aspect = w / h
        if aspect >= 1:
            wt = min(w, 256)
            ht = int(wt / aspect)
        else:
            ht = min(h, 256)
            wt = int(ht * aspect)
        thumbnail = scale(merged, wt, ht)
        rgba_thumbnail = make_rgba_image(thumbnail, colors)
        with io.BytesIO() as f:
            writer = png.Writer(width=wt, height=ht, bitdepth=8, greyscale=False, alpha=True)
            rows = (rgba_thumbnail[:, i].tobytes() for i in range(ht))
            writer.write(f, rows)    
            f.seek(0)
            orafile.writestr(f"Thumbnails/thumbnail.png", f.read())        
                
        # Merged image
        rgba_merged = make_rgba_image(merged, colors)
        with io.BytesIO() as f:
            writer = png.Writer(width=w, height=h, bitdepth=8, greyscale=False, alpha=True)
            rows = (rgba_merged[:, i].tobytes() for i in range(h))
            writer.write(f, rows)
            f.seek(0)
            orafile.writestr(f"mergedimage.png", f.read())
        
        # Other data (not part of ORA standard)
        orafile.writestr("oldpaint.json", json.dumps(kwargs))
                

def load_ora(path: str) -> Tuple[List[np.ndarray], dict, dict]:
    with zipfile.ZipFile(path, mode="r") as orafile:
        # Check that this is an oldpaint file.
        try:
            oldpaint_data = orafile.read("oldpaint.json")
            other_data = json.loads(oldpaint_data)
        except FileNotFoundError:
            # TODO check that this is the right exception
            raise RuntimeError("Can't load ORA files saved with other applications :(")
        except KeyError:
            # TODO do some better checking here, the format should be described
            # at least, maybe versioned?
            other_data = {}

        stack_xml = orafile.read("stack.xml")
        image_el = ET.fromstring(stack_xml)
        stack_el = image_el.find("stack")
        layers = []
        for el in stack_el:
            visibility = el.attrib.get("visibility", "visible")
            frames = []
            if el.tag == "layer":
                # Non-animated layer
                path = el.attrib["src"]
                with orafile.open(path) as imgf:
                    data, info = load_png(imgf)
                    frames = [data]
            elif el.tag == "stack":
                # Animated layer
                for frame_el in el:
                    path = frame_el.attrib["src"]
                    if path.endswith("/empty.png"):
                        # To save memory an empty frame is represented by None
                        frames.append(None)
                    else:
                        with orafile.open(path) as imgf:
                            data, info = load_png(imgf)
                            frames.insert(0, data)
            layers.insert(0, (frames, visibility == "visible"))
            
    return list(layers), info, other_data


def load_ora_thumbnail(path: str) -> Tuple[Tuple[int, int], np.ndarray, dict]:
    with zipfile.ZipFile(path, mode="r") as orafile:
        with orafile.open("Thumbnails/thumbnail.png") as tf:
            reader = png.Reader(tf)
            w, h, image_data, info = reader.read(tf)
    return (w, h), image_data, info
            
