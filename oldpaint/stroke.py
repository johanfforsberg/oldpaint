import logging
from queue import Queue
from time import sleep

from .util import try_except_log


logger = logging.getLogger(__name__)


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

        logger.debug("Start stroke: %s", type(self.tool).__name__)
        
        layer = self.drawing.backup

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
                sleep(self.tool.period)
                while not self._event_queue.empty():
                    if event_type == "mouse_up":
                        self.tool.finish(layer, *args)
                        finished = True
                        
                    event_type, *args = self._event_queue.get()
                if event_type is None:
                    continue

            if event_type == "abort":
                finished = False

            # Now use the tool appropriately
            elif event_type == "mouse_drag":
                with layer.lock:
                    # By taking the lock here we can prevent flickering.
                    if self.tool.ephemeral and self.tool.rect:
                        self.drawing.make_backup(self.tool.rect)
                        # self.layer.clear(self.tool.rect)
                    self.tool.draw(layer, *args)
            elif event_type == "mouse_up":
                self.tool.finish(layer, *args)
                finished = True

        logger.debug("End stroke: %s", type(self.tool).__name__)                
        return finished
