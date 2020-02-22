from functools import lru_cache
from itertools import chain, islice


DEFAULT_COLORS = [
    (170,170,170,0),(255,255,255,255),(101,101,101,255),(223,223,223,255),(207,48,69,255),
    (223,138,69,255),(207,223,69,255),(138,138,48,255),(48,138,69,255),(69,223,69,255),
    (69,223,207,255),(48,138,207,255),(138,138,223,255),(69,48,207,255),(207,48,207,255),
    (223,138,207,255),(227,227,227,255),(223,223,223,255),(223,223,223,255),(195,195,195,255),
    (178,178,178,255),(170,170,170,255),(146,146,146,255),(130,130,130,255),(113,113,113,255),
    (113,113,113,255),(101,101,101,255),(81,81,81,255),(65,65,65,255),(48,48,48,255),
    (32,32,32,255),(32,32,32,255),(243,0,0,255)
];


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
        self.foreground = 1
        self.background = 0

        self.overlay = {}

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
            self.overlayed_color.cache_clear()
            self.as_tuple.cache_clear()

    @lru_cache(maxsize=1)
    def as_tuple(self):
        return tuple(self.overlayed_color(i) for i in range(self.size))

    def __getitem__(self, index):
        return self.colors[index]

    def __iter__(self):
        # return islice(self.get_rgba(), 0, self.size)
        return islice(self.colors, 0, self.size)

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
