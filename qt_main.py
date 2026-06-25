#!/usr/bin/env python3
"""On-device entry: PyQt6 + QML driving the REAL MODEP host and REAL I2C hardware.

The Raspberry Pi entry point. Unlike ``qt_app.py`` (off-device dev: fake backend
+ fake hardware), this injects NO fakes -- the ``Presenter`` defaults to the real
MODEP host (``ModepController``, HTTP to localhost) and the footswitch/LED
controller is the real I2C ``fsledctrl.Controller``. It also binds the reverse-
channel socket (``/tmp/synapsin.sock``) so web-UI / HMI changes stay in sync,
mirroring ``app.py`` (the Kivy entry).

Fails loud if the host or hardware is absent -- a dead footswitch must surface on
a live stage box, never be silently faked.

Run (the Kivy app must NOT be running -- only one process may bind the socket or
hold the I2C bus):
    python qt_main.py
"""
import logging
import os
import socket
import sys
import threading
import time

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QFontDatabase, QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtQuick import QQuickWindow  # noqa: F401  registers QtQuick types for QML

import modepctrl
from configs import SOCKET_PATH
from hardwares import fsledctrl
from monitorfeed import MonitorFeed
from presenter import Presenter
from qtscheduler import QtScheduler
from qtview import QtView

BASE = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(level=logging.INFO)


def _wait_for_modep(timeout=30.0, interval=0.5):
    """Block until the MODEP host answers.

    A cold boot can autostart this entry before ``modep-mod-ui`` is serving; the
    Presenter pulls the pedalboard once in __init__, so a not-yet-ready host would
    yield ``None`` and crash on first paint. Poll until it responds (connection
    refused raises fast, so this spins cheaply). Returns ``True`` if it answered.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if modepctrl.get_backend().get_current_pedalboard():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def _start_reverse_listener(scheduler, presenter):
    """Bind ``/tmp/synapsin.sock`` and forward mod-ui's reverse-channel datagrams
    to the presenter on the GUI thread (mirrors ``app.py``'s Kivy listener)."""
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

    if not _wait_for_modep():
        logging.warning("MODEP did not respond within timeout; constructing anyway.")

    view = QtView()
    scheduler = QtScheduler()                    # GUI thread (QtScheduler asserts this)
    hardware = fsledctrl.Controller(scheduler)   # real I2C @ 0x27; raises loud if absent
    # No backend= -> Presenter uses get_backend()'s default: the real ModepController.
    presenter = Presenter(view, scheduler, hardware=hardware)
    view.set_presenter(presenter)
    presenter.initiate_view()

    sock = _start_reverse_listener(scheduler, presenter)
    # Live monitor feed: passive mod-ui websocket -> output_set -> meters.
    # SYNAPSE_NOFEED=1 disables it (isolation lever while debugging the feed).
    feed = None if os.environ.get("SYNAPSE_NOFEED") else MonitorFeed(presenter.update_monitor, scheduler)

    def _cleanup():
        # Order matters: stop the poll thread before tearing down the hardware it reads.
        presenter.stop_footswitch_polling()
        if feed:
            feed.stop()
        try:
            hardware.cleanup()
        except Exception as e:
            logging.error("hardware cleanup failed: %s", e)
        try:
            sock.close()
            if os.path.exists(SOCKET_PATH):
                os.unlink(SOCKET_PATH)
        except OSError:
            pass

    app.aboutToQuit.connect(_cleanup)

    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("view", view)
    ctx.setContextProperty("uiFont", ui_font)
    engine.load(QUrl.fromLocalFile(os.path.join(BASE, "qml", "main.qml")))
    if not engine.rootObjects():
        print("[qt_main] QML failed to load")
        return 1

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
