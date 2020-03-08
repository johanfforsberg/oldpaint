"""
Utilities for working with OpenRaster files, as specified by https://www.openraster.org/
ORA is a simple, open format that can be loaded by some other graphics software,
e.g. Krita.
"""

from typing import List, Tuple
import io
import json
import zipfile
from xml.etree import ElementTree as ET

from .picture import LongPicture, load_png, save_png


def save_ora(size: Tuple[int, int], layers: List[LongPicture], palette, path, **kwargs):
    w, h = size
    image_el = ET.Element("image", version="0.0.3", w=str(w), h=str(h))
    stack_el = ET.SubElement(image_el, "stack")
    for i, layer in enumerate(reversed(layers), 1):
        ET.SubElement(stack_el, "layer", name=f"layer{i}", src=f"data/layer{i}.png")
    stack_xml = b"<?xml version='1.0' encoding='UTF-8'?>" + ET.tostring(image_el)

    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as orafile:
        orafile.writestr("mimetype", "image/openraster", compress_type=zipfile.ZIP_STORED)
        orafile.writestr("stack.xml", stack_xml)
        for i, layer in enumerate(reversed(layers), 1):
            with io.BytesIO() as f:
                save_png(layer.pic, f, palette=palette.colors)
                f.seek(0)
                orafile.writestr(f"data/layer{i}.png", f.read())

        # Other data
        orafile.writestr("oldpaint.json", json.dumps(kwargs))
                

def load_ora(path):
    # TODO we should not allow loading arbitrary ORA, only those
    # conforming to what oldpaint can handle.
    with zipfile.ZipFile(path, mode="r") as orafile:
        stack_xml = orafile.read("stack.xml")
        image_el = ET.fromstring(stack_xml)
        stack_el = image_el[0]
        layers = []
        for layer_el in stack_el:
            path = layer_el.attrib["src"]
            with orafile.open(path) as imgf:
                pic, palette = load_png(imgf)
                layers.append(pic)
        try:
            other_data = json.loads(orafile.read("oldpaint.json"))
        except KeyError:
            other_data = {}
    return layers, palette, other_data
