from queue import Queue
from time import sleep

from .util import try_except_log


class Stroke:

    """
    Handler for a single stroke with a tool, from e.g. mouse button press
    to release. 
    """

    def __init__(self, layer, tool):
        self.layer = layer
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

        if self.layer.dirty:
            self.layer.clear(self.layer.dirty[0], frame=0)

        event_type, *start_args = self._event_queue.get()
        assert event_type == "mouse_down", "Unexpected event start type for stroke."
        self.tool.start(self.layer, *start_args)

        while True:

            # First check for events
            if self.tool.period is None:
                event_type, *args = self._event_queue.get()
                while not self._event_queue.empty():
                    # In case something gets slow, let's skip any accumulated events
                    if event_type == "mouse_up":
                        self.tool.finish(self.layer, *args)
                        return True                
                    event_type, *args = self._event_queue.get()
            else:
                sleep(self.tool.period)
                while not self._event_queue.empty():
                    if event_type == "mouse_up":
                        self.tool.finish(self.layer, *args)
                        return True                
                    event_type, *args = self._event_queue.get()
                if event_type is None:
                    continue

            if event_type == "abort":
                return False

            # Now use the tool appropriately
            if event_type == "mouse_drag":
                with self.layer.lock:
                    # By taking the lock here we can prevent flickering.
                    if self.tool.ephemeral and self.tool.rect:
                        self.layer.clear(self.tool.rect)
                    self.tool.draw(self.layer, *args)
            elif event_type == "mouse_up":
                self.tool.finish(self.layer, *args)
                return True                
