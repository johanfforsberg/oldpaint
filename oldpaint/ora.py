"""
Utilities for working with OpenRaster files, as specified by https://www.openraster.org/
"""

from typing import List, Tuple
import io
import zipfile
from xml.etree import ElementTree as ET

from .picture import Picture, load_png, save_png


def save_ora(size: Tuple[int, int], layers: List[Picture], palette, path: str):
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


def load_ora(path):
    with zipfile.ZipFile(path, mode="r") as orafile:
        stack_xml = orafile.read("stack.xml")
        image_el = ET.fromstring(stack_xml)
        stack_el = image_el[0]
        layers = []
        for layer_el in stack_el:
            path = layer_el.attrib["src"]
            with orafile.open(path) as imgf:
                pic = load_png(imgf)
                layers.append(pic)
    return list(reversed(layers))
