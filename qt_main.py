#!/usr/bin/env python3
"""On-device entry: PyQt6 + QML driving the REAL MODEP host and REAL I2C hardware.

The Raspberry Pi entry point. Unlike ``qt_dev.py`` (off-device dev: fake backend
+ fake hardware), this injects NO fakes -- the ``Presenter`` defaults to the real
MODEP host (``ModepController``, HTTP to localhost) and the footswitch/LED
controller is the real I2C ``fsledctrl.Controller``. It also binds the reverse-
channel socket (``/tmp/synapsin.sock``) so web-UI / HMI changes stay in sync.

Fails loud if the host or hardware is absent -- a dead footswitch must surface on
a live stage box, never be silently faked.

Run (only one Synapse process may run at a time -- it alone binds the socket and
holds the I2C bus):
    python qt_main.py
"""
import logging
import os
import socket
import sys
import threading
import time

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QFontDatabase, QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtQuick import QQuickWindow  # noqa: F401  registers QtQuick types for QML

import modepctrl
from configs import SOCKET_PATH
from editor_bridge import EditorBridge
from hardwares import fsledctrl
from levelmeter import LevelMeter
from monitorfeed import MonitorFeed
from presenter import Presenter
from qtscheduler import QtScheduler
from qtview import QtView
from theme_qml import ThemeProvider
from strings_qml import I18nProvider

BASE = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(level=logging.INFO)


def _modep_ready():
    """Has the MODEP host actually answered?

    ``get_current_pedalboard`` can't be the probe: it returns ``DEFAULT_PEDALBOARD``
    (truthy) when the host is down, so it would report ready immediately on a cold
    boot. Probe the raw HTTP layer instead -- a refused/timed-out request yields
    ``None`` from ``_request``.
    """
    backend = modepctrl.get_backend()
    probe = getattr(backend, "_request", None)
    if probe is None:
        # Fake backend (off-device dev) has no HTTP layer -> a board means ready.
        return bool(backend.get_current_pedalboard())
    return probe("get", "pedalboard/current") is not None


def _wait_for_modep(interval=0.5, log_every=10.0):
    """Block until the MODEP host answers, polling every ``interval`` seconds.

    Waits indefinitely: a stage box is useless without the host, and the QML
    splash ("MODEP 대기 중…") is already on screen, so blocking here is safe and
    preferable to constructing a broken first paint. The Presenter pulls the
    pedalboard once in __init__, so it must only be built after this returns.
    Logs every ``log_every`` seconds so a hung host is visible in the journal.
    """
    waited = 0.0
    next_log = log_every
    while not _modep_ready():
        time.sleep(interval)
        waited += interval
        if waited >= next_log:
            logging.info("waiting for MODEP host to start... (%.0fs)", waited)
            next_log += log_every


def _start_reverse_listener(scheduler, presenter):
    """Bind ``/tmp/synapsin.sock`` and forward mod-ui's reverse-channel datagrams
    to the presenter on the GUI thread (the reverse-channel → GUI-thread handoff)."""
    try:
        os.unlink(SOCKET_PATH)
    except OSError:
        if os.path.exists(SOCKET_PATH):
            raise
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o666)

    def loop():
        while True:
            try:
                data, _ = sock.recvfrom(1024)
                msg = data.decode("utf-8")
                # Marshal onto the GUI thread (QtScheduler callback signature: fn(dt)).
                scheduler.schedule_once(lambda dt, m=msg: presenter.handle_reverse_event(m))
            except Exception as e:
                logging.error("reverse listener stopped: %s", e)
                break

    threading.Thread(target=loop, daemon=True, name="reverse-sock").start()
    return sock


SHOT_TRIGGER = "/tmp/synapse-shot.trigger"
SHOT_OUT = "/tmp/synapse-shot.png"
_SHOT_HOOK = []                            # keeps the hook's QTimer wrapper alive (see below)


def _start_screenshot_hook(window):
    """Save a PNG of the live window whenever the trigger file appears.

    Remote eyeballing channel: under labwc this merely duplicates grim, but on
    the eglfs (no-compositor) boot there is no Wayland to screenshot -- the app
    itself is the only thing that can see its pixels. Over SSH:
        touch /tmp/synapse-shot.trigger   ->   /tmp/synapse-shot.png
    A stat() twice a second is free (cf. the footswitch polling doctrine); an
    inotify watcher isn't worth the moving parts.
    """
    def check():
        if not os.path.exists(SHOT_TRIGGER):
            return
        try:
            os.unlink(SHOT_TRIGGER)
        except OSError:
            pass
        img = window.grabWindow()          # QTimer fires on the GUI thread
        if img.save(SHOT_OUT):
            logging.info("screenshot -> %s", SHOT_OUT)
        else:
            logging.error("screenshot save failed: %s", SHOT_OUT)

    timer = QTimer(window)
    timer.timeout.connect(check)
    timer.start(500)
    # Pin the Python wrapper + closure for the process lifetime. Without this
    # the C++ timer (parented to the window) keeps firing after the GC collects
    # the sip wrapper -> segfault inside the interpreter on the next timeout
    # (reproduced twice, gdb: QTimer::timeout -> _PyEval_EvalFrameDefault SEGV).
    _SHOT_HOOK.append((timer, check))
    return timer


def main():
    # SIGUSR1 -> dump all thread stacks (kill -USR1 <pid>); ptrace-free live debug.
    import faulthandler
    import signal
    faulthandler.enable()
    try:
        # chain=False: dump stacks and KEEP RUNNING (chain=True would re-raise to
        # SIGUSR1's default action = terminate the process).
        faulthandler.register(signal.SIGUSR1, all_threads=True, chain=False)
    except (AttributeError, ValueError):
        pass

    app = QGuiApplication(sys.argv)

    # Bundle VT323 (OFL) and hand its real family name to QML.
    fid = QFontDatabase.addApplicationFont(
        os.path.join(BASE, "resources", "fonts", "VT323-Regular.ttf"))
    fams = QFontDatabase.applicationFontFamilies(fid)
    ui_font = fams[0] if fams else "monospace"

    view = QtView()
    view.show_booting()                          # splash until the MODEP host is ready
    scheduler = QtScheduler()                    # GUI thread (QtScheduler asserts this)
    # Pedalboard EDIT screen brain. Built up front so its `editor` context property
    # exists at QML load; the presenter is injected later (in _bring_up) once MODEP
    # is ready, after which entering EDIT seeds it from the live board.
    editor = EditorBridge()

    # Built only after the host answers (see _bring_up). Held here so aboutToQuit
    # cleanup can reach them whether or not bring-up has run yet.
    rt = {"presenter": None, "hardware": None, "sock": None, "feed": None, "meter": None}

    def _bring_up():
        # GUI thread (marshalled from the wait thread) once MODEP is ready: build
        # the real hardware + presenter, wire the reverse channel and monitor feed,
        # then flip the splash to the live overview.
        hardware = fsledctrl.Controller(scheduler)   # real I2C @ 0x27; raises loud if absent
        # No backend= -> Presenter uses get_backend()'s default: the real ModepController.
        presenter = Presenter(view, scheduler, hardware=hardware)
        view.set_presenter(presenter)
        editor.set_presenter(presenter)              # EDIT screen seeds from the live board
        presenter.editor = editor                    # so footswitch board nav can warn on unsaved edits
        presenter.initiate_view()
        sock = _start_reverse_listener(scheduler, presenter)
        # Live monitor feed: passive mod-ui websocket -> output_set -> meters.
        # SYNAPSE_NOFEED=1 disables it (isolation lever while debugging the feed).
        feed = None if os.environ.get("SYNAPSE_NOFEED") else MonitorFeed(presenter.update_monitor, scheduler)
        # OVERVIEW IN/OUT level meter: own JACK client tapping capture/playback.
        # SYNAPSE_NOMETER=1 disables it (isolation lever). Stays silent if JACK is absent.
        meter = None if os.environ.get("SYNAPSE_NOMETER") else LevelMeter()
        if meter and meter.ok:
            view.set_level_source(meter)
        rt.update(presenter=presenter, hardware=hardware, sock=sock, feed=feed, meter=meter)
        view.goOverview()                            # splash -> overview

    def _wait_then_bring_up():
        _wait_for_modep()
        # schedule_once is thread-safe: it marshals _bring_up onto the GUI thread.
        scheduler.schedule_once(lambda dt: _bring_up())

    def _cleanup():
        # Order matters: stop the poll thread before tearing down the hardware it reads.
        if rt["presenter"]:
            rt["presenter"].stop_footswitch_polling()
        if rt["feed"]:
            rt["feed"].stop()
        if rt["meter"]:
            rt["meter"].stop()
        if rt["hardware"]:
            try:
                rt["hardware"].lightshow_shutdown()   # ~1.5s farewell blink before pins reset
            except Exception as e:
                logging.error("shutdown lightshow failed: %s", e)
            try:
                rt["hardware"].cleanup()
            except Exception as e:
                logging.error("hardware cleanup failed: %s", e)
        if rt["sock"]:
            try:
                rt["sock"].close()
                if os.path.exists(SOCKET_PATH):
                    os.unlink(SOCKET_PATH)
            except OSError:
                pass

    app.aboutToQuit.connect(_cleanup)

    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("view", view)
    ctx.setContextProperty("editor", editor)
    ctx.setContextProperty("uiFont", ui_font)
    # Theme tokens (colors + type hierarchy) from theme/tokens.json — the same file
    # theme.py resolves on the Python side. `theme_provider` is kept alive by this
    # function's scope for the life of the event loop. See docs/theme-tokenization-plan.md.
    theme_provider = ThemeProvider(ui_font)
    ctx.setContextProperty("Theme", theme_provider)
    # User-facing strings from resources/strings/<lang>.json — the same files
    # strings.py resolves on the Python side (editor_bridge/qtview/presenter bake
    # text into payloads). English is the default language. `i18n_provider` is kept
    # alive by this function's scope. See docs/string-i18n-plan.md.
    i18n_provider = I18nProvider()
    ctx.setContextProperty("Tr", i18n_provider)
    engine.load(QUrl.fromLocalFile(os.path.join(BASE, "qml", "main.qml")))
    if not engine.rootObjects():
        print("[qt_main] QML failed to load")
        return 1

    # True fullscreen: on the Pi a title bar + taskbar otherwise steal ~40px and clip
    # the bottom of the 800x480 layout. Ctrl+Q (QML Shortcut) quits the dev instance.
    engine.rootObjects()[0].showFullScreen()
    _start_screenshot_hook(engine.rootObjects()[0])

    # Splash is up; wait for the host off the GUI thread, then bring up the app.
    threading.Thread(target=_wait_then_bring_up, daemon=True, name="modep-wait").start()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
