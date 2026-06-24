"""Scheduler backed by the Qt event loop (PySide6).

Off-device counterpart to ``scheduler.KivyScheduler``: the presenter and hardware
layer depend only on ``scheduler.Scheduler``, so the Qt entry point injects this.
``schedule_once`` is safe to call from a background thread (the footswitch poll
loop) -- it marshals the work onto the GUI thread via a queued signal, mirroring
KivyScheduler's thread-safety.
"""

from PySide6.QtCore import QObject, QTimer, Signal, Qt, QCoreApplication, QThread

from scheduler import Scheduler


class _MainThreadInvoker(QObject):
    """Run a callable on the thread that owns this object (the GUI thread)."""

    _post = Signal(object)

    def __init__(self):
        super().__init__()
        # Queued: emitting from any thread runs _run on this object's thread.
        self._post.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def _run(self, fn):
        fn()

    def invoke(self, fn):
        self._post.emit(fn)


class QtScheduler(Scheduler):
    """``Scheduler`` over Qt timers. Construct on the GUI thread."""

    def __init__(self):
        # Must be built on the GUI thread: the queued marshaling binds to this
        # object's thread, and a wrong binding makes QTimers silently never fire.
        app = QCoreApplication.instance()
        if app is not None and QThread.currentThread() is not app.thread():
            raise RuntimeError("QtScheduler must be constructed on the GUI thread")
        self._invoker = _MainThreadInvoker()
        self._intervals = {}
        self._seq = 0

    def schedule_once(self, callback, timeout=0):
        # callback(dt). Marshal onto the GUI thread so the QTimer starts there
        # even when called from the footswitch poll thread.
        self._invoker.invoke(
            lambda: QTimer.singleShot(max(0, int(timeout * 1000)), lambda: callback(0)))
        return None

    def schedule_interval(self, callback, interval):
        self._seq += 1
        handle = self._seq

        def start():
            t = QTimer()
            t.setInterval(max(1, int(interval * 1000)))
            t.timeout.connect(lambda: callback(0))
            t.start()
            self._intervals[handle] = t

        self._invoker.invoke(start)
        return handle

    def unschedule(self, handle):
        t = self._intervals.pop(handle, None)
        if t is not None:
            t.stop()
            t.deleteLater()
