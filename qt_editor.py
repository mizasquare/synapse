#!/usr/bin/env python3
"""Pedalboard Editor mock — standalone PyQt6 + QML entry (800×480).

A self-contained mock of the Claude Design "Concept A" pedalboard maker, ported to the
repo's real Qt stack (PyQt6 6.4.2 + Qt Quick), driven by ``EditorBridge`` (the brain) and
fed by the live installed-effects catalog (``resources/effects-catalog.json``). This is a
UX prototype, NOT wired to MODEP — it runs anywhere (Pi or Windows dev).

Run (Pi):
    /home/miza/synapse-venv/bin/python qt_editor.py
Run (off-device dev venv):
    .venv\\Scripts\\python qt_editor.py
Screenshot one frame and quit:
    python qt_editor.py --shot editor.png
"""
import os
import sys

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QGuiApplication, QFontDatabase

from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtQuick import QQuickWindow  # noqa: F401  (registers the type so the QML root casts)

from editor_bridge import EditorBridge

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    argv = sys.argv
    shot = None
    if "--shot" in argv:
        i = argv.index("--shot")
        shot = os.path.abspath(argv[i + 1]) if i + 1 < len(argv) else os.path.join(BASE, "editor.png")

    app = QGuiApplication(argv)

    fid = QFontDatabase.addApplicationFont(os.path.join(BASE, "resources", "fonts", "VT323-Regular.ttf"))
    fams = QFontDatabase.applicationFontFamilies(fid)
    ui_font = fams[0] if fams else "monospace"

    editor = EditorBridge()

    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("editor", editor)
    ctx.setContextProperty("uiFont", ui_font)
    engine.load(QUrl.fromLocalFile(os.path.join(BASE, "qml", "PedalboardEditor.qml")))
    if not engine.rootObjects():
        print("[qt_editor] QML failed to load")
        return 1

    if shot:
        win = engine.rootObjects()[0]

        def grab():
            try:
                img = win.grabWindow()
                ok = img.save(shot)
                print("[qt_editor] screenshot %s -> %s (%dx%d)" % (
                    "ok" if ok else "FAILED", shot, img.width(), img.height()))
            except Exception as e:  # noqa: BLE001
                print("[qt_editor] grab failed:", e)
            finally:
                app.quit()

        QTimer.singleShot(800, grab)
    else:
        # On the Pi the title bar + taskbar steal ~40px and clip the bottom of the
        # 800x480 layout — go true fullscreen so the device area maps 1:1 to the screen.
        win = engine.rootObjects()[0]
        win.showFullScreen()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
