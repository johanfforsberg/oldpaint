import logging
from time import time
from traceback import format_exc

import pyglet


def try_except_log(f):
    "A decorator useful for debugging event callbacks whose exceptions get eaten."
    def inner(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception:
            logging.error(format_exc())
    return inner


class Selectable:

    """
    Wrapper for a list of items where one can be selected.
    Also supports adding and removing items.
    """

    def __init__(self, items=None):
        self.items = items or []
        self.current = items[0] if items else None

    def __iter__(self):
        return iter(self.items)

    def select(self, item):
        assert item in self.items, f"No such item {item}!"
        print("select", item)
        self.current = item

    def get_current_index(self):
        if self.current is None:
            return None
        if self.current not in self.items:
            self.current = None
            return None
        return self.items.index(self.current)

    def add(self, item, index=None):
        if self.items:
            index = index if index is not None else self.get_current_index()
            self.items.insert(index, item)
        else:
            self.items.append(item)
        self.current = item

    def remove(self, item=None):
        item = item or self.current
        try:
            index = self.items.index(item)
            self.items.remove(item)
            self.current = self.items[min(index, len(self.items) - 1)]
        except (ValueError, IndexError):
            self.current = None


def throttle(interval=0.1):
    """
    A decorator that ensures that the function is not run more often
    than the given interval, no matter how often it's called.
    Uses the pyglet clock to schedule calls.
    """
    scheduled_at = None

    def wrap(f):
        def inner(*args, **kwargs):
            nonlocal scheduled_at
            now = time()
            if scheduled_at and scheduled_at > now:
                return
            scheduled_at = now + interval

            pyglet.clock.schedule_once(lambda dt: f(*args, **kwargs), interval)
        return inner

    return wrap
