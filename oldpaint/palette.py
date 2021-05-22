from copy import copy
from functools import lru_cache
from itertools import islice
import json


with open("palettes/vga_palette.json") as f:
    vga_palette = json.load(f)


DEFAULT_COLORS = [(r, g, b, 255 * (i != 0))
                  for i, (r, g, b)
                  in enumerate(vga_palette)]


class Palette:

    # TODO extend Selectable?
    "Palette storage. Keeps integer values internally but allows access as floats."

    def __init__(self, colors=None, transparency=None, size=256):
        # self.colors = (list(zip(*[map(int, colors)] * 3)) if colors
        self.size = size
        if colors:
            color0 = colors[0]
            if len(color0) == 3:
                self.colors = [c + (255,) for c in colors] + [(0, 0, 0, 255)] * (self.size - len(colors))
            else:
                self.colors = colors + [(0, 0, 0, 255)] * (self.size - len(colors))
        else:
            self.colors = DEFAULT_COLORS + [(0, 0, 0, 255)] * (self.size - len(DEFAULT_COLORS))
        assert len(self.colors) == self.size, f"Bad number of colors: {len(self.colors)}"
        # self.transparency = transparency
        self._foreground = 1
        self._background = 0

        self.overlay = {}

    @property
    def foreground(self):
        return self._foreground

    @foreground.setter
    def foreground(self, fg):
        assert 0 <= fg <= len(self.colors), f"Color index {fg} out of range!"
        self._foreground = fg
    
    @property
    def background(self):
        return self._background
    
    @background.setter
    def background(self, bg):
        assert 0 <= bg <= len(self.colors), f"Color index {bg} out of range!"
        self._background = bg
    
    def set_overlay(self, i, color):
        self.overlay[i] = color
        self.overlayed_color.cache_clear()
        self.as_tuple.cache_clear()

    @lru_cache(256)
    def overlayed_color(self, i):
        return self.overlay.get(i, self.colors[i])

    def clear_overlay(self):
        if self.overlay:
            self.overlay.clear()
            self._clear_caches()

    def _clear_caches(self):
        self.overlayed_color.cache_clear()
        self.as_tuple.cache_clear()
        self.get_color_as_float.cache_clear()

    @lru_cache(maxsize=1)
    def as_tuple(self):
        return tuple(self.overlayed_color(i) for i in range(self.size))

    def __getitem__(self, index):
        return self.colors[index]

    def __iter__(self):
        # return islice(self.get_rgba(), 0, self.size)
        return islice(self.colors, 0, self.size)

    def __len__(self):
        return len(self.colors)

    def set_color(self, index, r, g, b, a):
        if isinstance(r, int):
            self.colors[index] = r, g, b, a
        else:
            self.colors[index] = int(r*256), int(g*256), int(b*256), int(a*256)
        self.as_tuple.cache_clear()
        self.overlayed_color.cache_clear()

    def swap_colors(self, index1, index2):
        self.colors[index1], self.colors[index2] = self.colors[index2], self.colors[index1]
        self.as_tuple.cache_clear()
        self.overlayed_color.cache_clear()

    def __setitem__(self, index, value):
        self.set_color(index, *value)

    def get_color(self, i):
        overlay_color = self.overlay.get(i)
        if overlay_color is not None:
            return overlay_color
        return self.colors[i]

    @property
    def foreground_color(self):
        overlay_color = self.overlay.get(self.foreground)
        if overlay_color is not None:
            return overlay_color
        return self.colors[self.foreground]

    @foreground_color.setter
    def foreground_color(self, color):
        self.set_color(self.foreground, *color)

    @property
    def background_color(self):
        return self.colors[self.background]

    @background_color.setter
    def background_color(self, color):
        self.set_color(self.background, *color)

    @property
    def transparent_colors(self):
        return [i for i in range(len(self.colors)) if self.colors[i][3] == 0]

    def spread(self, index1, index2):
        "Make a nice smooth color ramp between the given colors."

        if index1 == index2:
            return []

        if index1 > index2:
            index1, index2 = index2, index1
        r1, g1, b1, a1 = self.colors[index1]
        r2, g2, b2, a2 = self.colors[index2]
        n_steps = index2 - index1

        dr = (r2 - r1) / n_steps
        dg = (g2 - g1) / n_steps
        db = (b2 - b1) / n_steps

        return [
            (round(r1 + dr * i), round(g1 + dg * i), round(b1 + db * i), 1)
            for i in range(1, n_steps)
        ]

    @lru_cache(256)
    def get_color_as_float(self, color):
        r, g, b, a = color
        return r / 255, g / 255, b / 255, a / 255

    def make_diff(self, colors):
        
        def diff_colors(c1, c2):
            r1, g1, b1, a1 = c1
            r2, g2, b2, a2 = c2
            return r2 - r1, g2 - g1, b2 - b1, a2 - a1
        
        return [
            (i, *diff_colors(self.colors[i], new_color))
            for i, new_color in colors
            if new_color != self.colors[i]
        ]

    def add_colors(self, colors, index=None):
        if index is None:
            self.colors.extend(colors)
        else:
            self.colors = [*self.colors[:index], *colors, * self.colors[index:]]
            if self.foreground > index:
                self.foreground += len(colors)
        self.size = len(self.colors)
        self._clear_caches()

    def remove_colors(self, n, index=None):
        if index is None:
            self.colors = self.colors[:-n]
            if self.foreground >= len(self.colors):
                self.foreground = len(self.colors) - 1
        else:
            self.colors = [*self.colors[:index], *self.colors[index+n:]]
            if self.foreground > index:
                self.foreground -= n
        self.size = len(self.colors)
        self._clear_caches()

    def clone(self):
        return Palette(copy(self.colors))
