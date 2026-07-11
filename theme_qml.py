"""QML-facing theme provider — the QML half of the single source of truth.

Wraps ``theme.py`` (which owns ``theme/tokens.json``) in a QObject whose slots QML
calls: ``Theme.color("accent.green")`` for colors and ``Theme.typeFont("button")``
for a ready-built QFont (family+size+weight in one binding). Injected as the
``Theme`` context property in qt_main.py, mirroring the existing ``uiFont`` injection
so both languages resolve from the same file. See docs/theme-tokenization-plan.md.
"""

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtGui import QFont

import theme

_WEIGHTS = {
    "Thin": QFont.Weight.Thin, "Light": QFont.Weight.Light,
    "Normal": QFont.Weight.Normal, "Medium": QFont.Weight.Medium,
    "DemiBold": QFont.Weight.DemiBold, "Bold": QFont.Weight.Bold,
    "Black": QFont.Weight.Black,
}


class ThemeProvider(QObject):
    """Read-only bridge from the token file to QML. Holds the resolved UI font
    family so ``typeFont`` can stamp it onto every non-glyph role."""

    def __init__(self, ui_font, parent=None):
        super().__init__(parent)
        self._ui_font = ui_font

    # --- colors (dotted token name -> hex string) ---
    @pyqtSlot(str, result=str)
    def color(self, name):
        return theme.color(name)

    @pyqtSlot(str, float, result=str)
    def alpha(self, name, a):
        return theme.alpha(name, a)

    # --- role indirection maps ---
    @pyqtSlot(str, result=str)
    def port(self, port_type):
        return theme.port_color(port_type)

    @pyqtSlot(str, result=str)
    def bucket(self, name):
        return theme.bucket_color(name)

    @pyqtSlot(str, result=str)
    def bucketAbbr(self, name):
        return theme.bucket_abbr(name)

    @pyqtSlot(str, result=str)
    def led(self, kind):
        return theme.led_color(kind)

    @pyqtSlot(str, result="QVariant")
    def fx(self, name):
        return theme.fx(name)

    # --- type hierarchy: a ready QFont for `font: Theme.typeFont("role")` ---
    @pyqtSlot(str, result="QVariant")
    def typeFont(self, role):
        spec = theme.type_spec(role)
        f = QFont()
        if not spec["noFamily"]:                 # glyph roles keep the system font
            f.setFamily(self._ui_font)
        f.setPixelSize(int(spec["size"]))
        f.setWeight(_WEIGHTS.get(spec["weight"], QFont.Weight.Normal))
        return f

    # --- bare pixel size, for the few places that only need a number ---
    @pyqtSlot(str, result=int)
    def typeSize(self, role):
        return int(theme.type_spec(role)["size"])
