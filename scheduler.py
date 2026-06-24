"""Event-loop scheduling abstraction.

Decouples the logic layers (presenter, hardware controllers) from the GUI
framework's main-loop timer. Those layers depend only on the ``Scheduler``
interface below; the concrete ``KivyScheduler`` wraps ``kivy.clock.Clock`` and
is wired in by the view layer. Swapping GUI frameworks means writing a new
``Scheduler`` implementation, not touching the logic.

Method signatures intentionally mirror ``kivy.clock.Clock`` so the wrapper is a
thin pass-through and call sites change in name only.
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


class KivyScheduler(Scheduler):
    """Scheduler backed by ``kivy.clock.Clock`` — the only Kivy-aware piece.

    Imports Kivy lazily so this module stays importable (e.g. for headless
    logic tests that inject a fake Scheduler) on machines without Kivy.
    """

    def __init__(self):
        from kivy.clock import Clock
        self._clock = Clock

    def schedule_once(self, callback, timeout=0):
        return self._clock.schedule_once(callback, timeout)

    def schedule_interval(self, callback, interval):
        return self._clock.schedule_interval(callback, interval)

    def unschedule(self, handle):
        self._clock.unschedule(handle)
