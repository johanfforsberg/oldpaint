from queue import Queue
from time import sleep

from .util import try_except_log


class Stroke:

    """
    Handler for a single stroke with a tool, from e.g. mouse button press
    to release. 
    """

    def __init__(self, drawing, tool):
        self.drawing = drawing
        self.tool = tool
        self._event_queue = Queue()        

    def queue_event(self, *event):
        self._event_queue.put(event)
        
    @try_except_log
    def __call__(self):

        """
        This function will consume events on the event queue until it receives
        a mouse_up event. It's expected to be running in a thread.
        """

        layer = self.drawing.current

        # self.drawing.restore()

        event_type, *start_args = self._event_queue.get()
        assert event_type == "mouse_down", "Unexpected event start type for stroke."
        self.tool.start(layer, *start_args)

        finished = None
        
        while finished is None:

            # First check for events
            if self.tool.period is None:
                event_type, *args = self._event_queue.get()
                while not self._event_queue.empty():
                    # In case something gets slow, let's skip any accumulated events
                    if event_type == "mouse_up":
                        self.tool.finish(layer, *args)
                        finished = True
                    event_type, *args = self._event_queue.get()
            else:
                sleep(tool.period)
                while not event_queue.empty():
                    if event_type == "mouse_up":
                        self.tool.finish(layer, *args)
                        finished = True
                        
                    event_type, *args = self._event_queue.get()
                if event_type is None:
                    continue

            if event_type == "abort":
                finished = False

            # Now use the tool appropriately
            if event_type == "mouse_drag":
                with layer.lock:
                    # By taking the lock here we can prevent flickering.
                    if self.tool.ephemeral and self.tool.rect:
                        #self.layer.clear(self.tool.rect)
                        self.drawing.restore(self.tool.rect)
                    self.tool.draw(layer, *args)
            elif event_type == "mouse_up":
                self.tool.finish(layer, *args)
                finished = True

        return finished
