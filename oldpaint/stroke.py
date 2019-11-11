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
            with layer.lock:
                if tool.ephemeral and tool.rect:
                    # By keeping the lock here, we can prevent some flickering.
                    layer.clear(tool.rect)
                tool.draw(layer, *args)
        elif event_type == "mouse_up":
            with layer.lock:
                tool.finish(layer, *args)
            break

    return tool
