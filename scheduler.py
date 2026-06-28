"""Event-loop scheduling abstraction.

Decouples the logic layers (presenter, hardware controllers) from the GUI
framework's main-loop timer. Those layers depend only on the ``Scheduler``
interface below; the concrete implementation is wired in by the view layer
(``qtscheduler.QtScheduler``, on the Qt event loop). Swapping GUI frameworks
means writing a new ``Scheduler`` implementation, not touching the logic.
"""


class Scheduler:
    """Run callbacks on the GUI/main-loop thread.

    ``schedule_once(callback, timeout=0)`` -> handle
        Run ``callback(dt)`` once after ``timeout`` seconds (0 == next frame).
        Safe to call from a background thread to marshal work onto the main
        thread.
    ``schedule_interval(callback, interval)`` -> handle
        Run ``callback(dt)`` repeatedly every ``interval`` seconds.
    ``unschedule(handle)`` -> None
        Cancel a previously scheduled callback by the handle it returned.
    """

    def schedule_once(self, callback, timeout=0):
        raise NotImplementedError

    def schedule_interval(self, callback, interval):
        raise NotImplementedError

    def unschedule(self, handle):
        raise NotImplementedError
