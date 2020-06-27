"""
Utilities for working with OpenRaster files, as specified by https://www.openraster.org/
ORA is a simple, open format that can be loaded by some other graphics software,
e.g. Krita. Don't expect the opposite to be true in general though, as we have very
specific requirements.
"""

from typing import List, Tuple
import io
import json
import zipfile
from xml.etree import ElementTree as ET

import numpy as np
import png


def save_png(data, dest, palette=None):
    w, h = data.shape
    writer = png.Writer(w, h, bitdepth=8, alpha=False, palette=palette)
    rows = (data[:, i].tobytes() for i in range(data.shape[1]))
    writer.write(dest, rows)


def load_png(f):
    reader = png.Reader(f)
    w, h, image_data, info = reader.read(f)
    assert info.get("palette"), "Sorry, can't load non palette based PNGs."
    return np.vstack(list(map(np.uint8, image_data))).T, info

    
def save_ora(size: Tuple[int, int], layers: List["Layer"], palette, path, **kwargs):
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
                        save_png(frame, f, palette=palette.colors)
                        f.seek(0)
                        orafile.writestr(f"data/layer{i}_frame{j}.png", f.read())
        if has_empty_frame:
            empty_frame = np.zeros(size, dtype=np.uint8)
            with io.BytesIO() as f:
                save_png(empty_frame, f, palette=palette.colors)
                f.seek(0)
                orafile.writestr(f"data/empty.png", f.read())

        # Other data
        orafile.writestr("oldpaint.json", json.dumps(kwargs))
    # TODO thumbnail, mergedimage (to conform to the spec)
                

def load_ora(path):
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
