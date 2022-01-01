from time import sleep

from .util import try_except_log


@try_except_log
def make_stroke(layer, event_queue, tool):

    """
    This function will consume events on the given queue until it receives
    a mouse_up event. It's expected to be running in a thread.
    """

    if layer.dirty:
        layer.clear(layer.dirty[0], frame=0)

    event_type = None

    event_type, *start_args = event_queue.get()
    assert event_type == "mouse_down"
    tool.start(layer, *start_args)

    while True:

        # First check for events
        if tool.period is None:
            event_type, *args = event_queue.get()
            if args[1] is None:
                args[1] = start_args[1]
            if args[2] is None:
                args[2] = start_args[2]
            while not event_queue.empty():
                # In case something gets slow, let's skip any accumulated events
                event_type, *args = event_queue.get()
        else:
            sleep(tool.period)
            while not event_queue.empty():
                event_type, *args = event_queue.get()

            if event_type is None:
                continue

        if event_type == "abort":
            return None

        # Now use the tool appropriately
        if event_type == "mouse_drag":
            with layer.lock:
                # By taking the lock here we can prevent flickering.
                if tool.ephemeral and tool.rect:
                    layer.clear(tool.rect)
                tool.draw(layer, *args)
        elif event_type == "mouse_up":
            tool.finish(layer, *args)
            break

    return tool
