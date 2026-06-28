#!/usr/bin/env python3
"""Minimal PyQt6 smoke test for the Synapse Qt migration.

Validates the Qt render + touch path on this Pi. Runs both windowed (under the
current labwc compositor) and on eglfs (no compositor), unchanged.

Windowed (under the running desktop):
    /home/miza/synapse-venv/bin/python tests/qt_smoke.py

No-compositor (eglfs) — run over SSH so you keep a shell while the GUI is down:
    sudo systemctl stop lightdm
    QT_QPA_PLATFORM=eglfs /home/miza/synapse-venv/bin/python tests/qt_smoke.py
    # ...tap around the touchscreen, then tap QUIT (or press Esc)...
    sudo systemctl start lightdm
    # if touch is dead under eglfs, retry with QT_QPA_EGLFS_NO_LIBINPUT=1 prepended
"""
import sys
from PyQt6.QtCore import Qt, QT_VERSION_STR
from PyQt6.QtGui import QPainter, QColor, QFont
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton


class SmokeWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.taps = []          # recent tap points (x, y)
        self.tap_count = 0
        self.setWindowTitle("Synapse Qt smoke")
        # Big QUIT button — eglfs has no window manager, so we need a touch exit.
        self.quit_btn = QPushButton("QUIT", self)
        self.quit_btn.clicked.connect(QApplication.instance().quit)
        self.quit_btn.setStyleSheet(
            "background:#c0392b; color:white; font-size:26px;"
            "font-weight:bold; border:none; border-radius:8px;")

    def resizeEvent(self, _):
        self.quit_btn.setGeometry(self.width() - 170, 24, 150, 84)

    def _lines(self):
        app = QApplication.instance()
        scr = app.primaryScreen()
        g = scr.geometry()
        return [
            "Synapse  ·  PyQt6 smoke test",
            f"platform : {app.platformName()}",
            f"Qt       : {QT_VERSION_STR}",
            f"screen   : {g.width()} x {g.height()}  ({scr.devicePixelRatio():.2f}x)",
            f"taps     : {self.tap_count}",
            "",
            "Tap anywhere to test touch.   QUIT or Esc to exit.",
        ]

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#102027"))
        p.setPen(QColor("#e0f7fa"))
        p.setFont(QFont("sans-serif", 18))
        y = 70
        for line in self._lines():
            p.drawText(44, y, line)
            y += 46
        for (x, ty) in self.taps[-25:]:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#26c6da"))
            p.drawEllipse(int(x) - 16, int(ty) - 16, 32, 32)
            p.setPen(QColor("#ffffff"))
            p.setFont(QFont("monospace", 11))
            p.drawText(int(x) + 22, int(ty) + 4, f"{int(x)},{int(ty)}")

    def mousePressEvent(self, e):       # Qt synthesizes mouse from single touch
        pos = e.position()
        self.tap_count += 1
        self.taps.append((pos.x(), pos.y()))
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            QApplication.instance().quit()


def main():
    app = QApplication(sys.argv)
    w = SmokeWidget()
    w.showFullScreen()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
