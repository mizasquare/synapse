"""Off-device dev entry: PyQt6 + QML mock, fake MODEP backend + fake hardware.

Wires the real ``Presenter`` to a fake MODEP backend and fake hardware, driving
the QML view -- so the whole presenter/model stack runs with no Pi (screenshots,
desktop dev). The on-device entry is ``qt_main.py`` (real ``ModepController`` +
real I2C ``fsledctrl``); this file deliberately injects fakes only.

Run:
    python qt_app.py                 # interactive window (fake backend + hardware)
    python qt_app.py --shot out.png  # render one frame, save, quit
"""

import os
import sys

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QGuiApplication, QFontDatabase
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtQuick import QQuickWindow  # registers QQuickWindow so the QML root casts correctly

import modepctrl
from fakemodep import FakeModepController
from fakehardware import FakeController
from qtscheduler import QtScheduler
from qtview import QtView
from presenter import Presenter

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    argv = sys.argv
    shot = None
    if "--shot" in argv:
        i = argv.index("--shot")
        shot = os.path.abspath(argv[i + 1]) if i + 1 < len(argv) else os.path.join(BASE, "shot.png")
    focus_inst = None
    if "--focus" in argv:
        j = argv.index("--focus")
        if j + 1 < len(argv):
            focus_inst = argv[j + 1]  # dev: open FOCUS on this effect for a screenshot

    app = QGuiApplication(argv)

    # Bundle VT323 (OFL) and pass its real family name to QML.
    fid = QFontDatabase.addApplicationFont(os.path.join(BASE, "resources", "fonts", "VT323-Regular.ttf"))
    fams = QFontDatabase.applicationFontFamilies(fid)
    ui_font = fams[0] if fams else "monospace"

    # Backend: fake fixtures by default; --real talks to the live MODEP host
    # (HTTP, read-only) to screenshot the actual loaded pedalboard. Hardware is
    # always fake here (no I2C bus grab) and there is no reverse-socket listener,
    # so --real never disturbs a running qt_main.
    view = QtView()
    scheduler = QtScheduler()
    if "--real" in argv:
        # No backend= / no set_backend -> default get_backend() = real ModepController.
        presenter = Presenter(view, scheduler, hardware=FakeController())
    else:
        backend = FakeModepController()
        modepctrl.set_backend(backend)
        presenter = Presenter(view, scheduler, backend=backend, hardware=FakeController())
    view.set_presenter(presenter)

    # Populate the view from the presenter before loading QML, so first paint is
    # already correct (the change signal then keeps it live for Stage 2+).
    presenter.initiate_view()
    if focus_inst:
        presenter.view_render_parameters(focus_inst)
    if "--tap" in argv:
        presenter.enter_tap_tempo()  # dev: open the TAP TEMPO screen for a screenshot

    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("view", view)
    ctx.setContextProperty("uiFont", ui_font)
    engine.load(QUrl.fromLocalFile(os.path.join(BASE, "qml", "main.qml")))
    if not engine.rootObjects():
        print("[qt_app] QML failed to load")
        return 1

    # Stop the footswitch poll thread cleanly on quit. Harmless now (FakeController
    # is a no-op + daemon thread), but a Stage-3 prerequisite: once real/synthetic
    # footswitch events exist, a press during shutdown must not marshal work onto a
    # torn-down view. The --shot path (app.quit() while the thread spins) needs it too.
    app.aboutToQuit.connect(presenter.stop_footswitch_polling)

    if shot:
        win = engine.rootObjects()[0]

        # --animate: drive the focused effect's monitors through the live path
        # (presenter.update_monitor -> view.monitorUpdated -> MonitorWidget) and
        # grab several frames, so meter movement is verifiable without real audio.
        if "--animate" in argv and focus_inst:
            import math
            base, ext = os.path.splitext(shot)
            eff = presenter.pedalboard.get_effect_by_instance(focus_inst) if presenter.pedalboard else None
            mons = list(eff.monitors.values()) if eff else []
            ph = {"t": 0}

            def step():
                ph["t"] += 1
                for k, mon in enumerate(mons):
                    mn = mon.min_value if mon.min_value is not None else 0.0
                    mx = mon.max_value if mon.max_value is not None else 1.0
                    frac = 0.5 + 0.5 * math.sin((ph["t"] + k * 4) * 0.5)
                    presenter.update_monitor(focus_inst, mon.symbol, mn + frac * (mx - mn))

            osc = QTimer()
            osc.timeout.connect(step)
            osc.start(60)
            n = {"i": 0}

            def grabframe():
                n["i"] += 1
                p = "%s-f%d%s" % (base, n["i"], ext)
                img = win.grabWindow()
                img.save(p)
                print("[qt_app] frame %s (%dx%d)" % (p, img.width(), img.height()))
                if n["i"] >= 3:
                    app.quit()

            for ms in (500, 1100, 1700):
                QTimer.singleShot(ms, grabframe)
            return app.exec()

        def grab():
            try:
                img = win.grabWindow()
                ok = img.save(shot)
                print("[qt_app] screenshot %s -> %s (%dx%d)" % (
                    "ok" if ok else "FAILED", shot, img.width(), img.height()))
            except Exception as e:
                print("[qt_app] grab failed:", e)
            finally:
                app.quit()

        QTimer.singleShot(800, grab)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
