from .util import try_except_log


@try_except_log
def make_stroke(layer, event_queue, tool):

    """
    This function will consume events on the given queue until it receives
    a mouse_up event. It's expected to be running in a thread.
    """

    if layer.dirty:
        layer.clear(layer.dirty)

    while True:
        event_type, args = event_queue.get()
        while not event_queue.empty():
            # In case something gets slow, let's skip any accumulated events
            event_type, args = event_queue.get()

        if event_type == "mouse_drag":
            tool.draw(*args)
        elif event_type == "mouse_up":
            tool.finish(*args)
            break

    return tool
