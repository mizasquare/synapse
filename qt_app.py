"""Off-device entry point: PySide6 + QML mock UI (Windows dev).

Wires the real ``Presenter`` to a fake MODEP backend and fake hardware, then
drives a QML view -- so the whole presenter/model stack runs with no Pi. The
on-device Kivy path (app.py / view.py) is untouched.

Run:
    .venv\\Scripts\\python.exe qt_app.py            # interactive window
    .venv\\Scripts\\python.exe qt_app.py --shot out.png  # render one frame, save, quit
"""

import os
import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # registers QQuickWindow so the QML root casts correctly

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

    # Inject the fakes at their seams: backend module-level (for the shared
    # builder + model methods) and via the presenter constructor.
    backend = FakeModepController()
    modepctrl.set_backend(backend)

    view = QtView()
    scheduler = QtScheduler()
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
