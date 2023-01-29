import pyglet


class TabletStateHandler:

    def __init__(self, window):
        self.data = {
            "x": 0,
            "y": 0,
            "pressure": 0,
        }
        self.active = False
        tablets = pyglet.input.get_tablets()
        if tablets:
            self.tablet = tablets[0]
            canvas = self.tablet.open(window)

            @canvas.event
            def on_enter(cursor):
                self.active = True

            @canvas.event
            def on_leave(cursor):
                self.active = False
            
            @canvas.event
            def on_motion(cursor, x, y, pressure, tilt_x, tilt_y, *_):
                self.data["x"] = x
                self.data["y"] = y
                self.data["pressure"] = pressure
                self.active = True

        else:
            self.tablet = None

    def __getitem__(self, key):
        return self.data.get(key, False)
            
