from functools import lru_cache
from inspect import isgeneratorfunction
from pathlib import Path

import imgui


def stateful(f):

    """
    This decorates a function that is expected to be a generator function. Basically it
    allows the function to be called repeatedly like a normal function, while it actually
    just keeps iterating over the generator.

    This enables a weird idiom which seems pretty useful for imgui use. The idea is that a
    function decorated with this can keep its own state over time, initialized on the first
    call, and then just loop forever or until it's done (the latter useful for dialogs and
    things that have limited lifetime.) The point is that this way we can keep "local" state
    such as open dialogs where appropriate and don't need to keep sending global state around.

    This way, functions that keep state and functions that don't can be used the same.
    """

    assert isgeneratorfunction(f), "Sorry, only accepts generator functions!"

    gens = {}

    def inner(*args, **kwargs):
        t = (args, tuple(kwargs.items()))
        if t not in gens:
            gen = f(*args, **kwargs)
            gens[t] = gen
            return next(gen)
        else:
            gen = gens[t]
        try:
            return gen.send(args)
        except StopIteration:
            del gens[t]  # TODO reinitialize directly instead?
            return False

    return inner


@lru_cache(0)
def list_dir(path):
    return [
        (entry,
         entry.is_dir(),
         entry.is_file() and entry.stat().st_size or None)
        for entry in sorted(path.iterdir(), key=lambda p: p.name.lower())
        if not entry.name.startswith(".")
    ]


@stateful
def render_file_browser(window, name, edit_filename=False):

    current_path = None
    filename = ""

    while True:

        result = None

        if imgui.begin_popup_modal(name, None, imgui.WINDOW_NO_COLLAPSE)[0]:
            w = imgui.get_window_width()
            if current_path is None:
                current_path = Path(window.get_latest_dir())
            imgui.text(str(current_path))
            imgui.same_line(w - 50)
            if imgui.button(".."):
                current_path = current_path.parent
            imgui.begin_child("Current dir", border=True, height=-25)
            imgui.columns(2)
            imgui.set_column_width(0, w * 0.8)
            for p, is_dir, size in list_dir(current_path):
                if is_dir:
                    if imgui.button(p.name):
                        current_path /= p.name
                    imgui.next_column()
                    imgui.text("<DIR>")
                else:
                    if imgui.selectable(p.name)[0]:
                        list_dir.cache_clear()
                        result = str(current_path / p.name)
                    imgui.next_column()
                    imgui.text(str(size))
                imgui.next_column()
            imgui.columns(1)
            imgui.end_child()
            if edit_filename:
                changed, filename = imgui.input_text("Filename", filename, 50,
                                                     imgui.INPUT_TEXT_ENTER_RETURNS_TRUE)
                imgui.same_line()
                if changed or imgui.button("OK"):
                    imgui.close_current_popup()
                    result = str(current_path / filename)
                    filename = ""
                imgui.same_line()
            if imgui.button("Cancel"):
                imgui.close_current_popup()
                filename = ""
            imgui.end_popup()

        yield result
