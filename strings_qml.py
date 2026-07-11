"""QML-facing string provider — the QML half of the string single source.

Wraps ``strings.py`` (which owns ``resources/strings/<lang>.json``) in a QObject
whose slots QML calls: ``Tr.tr("chrome.save")`` for a static label and
``Tr.trf("overview.hostBoards", [n])`` for a parameterized one (formatting runs
through the same Python ``str.format`` path, so QML and Python never diverge on
placeholder rules). Injected as the ``Tr`` context property in qt_main.py next to
``Theme``; kept alive by that function's scope. See docs/string-i18n-plan.md.
"""

from PyQt6.QtCore import QObject, pyqtSlot

import strings


class I18nProvider(QObject):
    """Read-only bridge from the string files to QML."""

    @pyqtSlot(str, result=str)
    def tr(self, key):
        return strings.tr(key)

    @pyqtSlot(str, "QVariantList", result=str)
    def trf(self, key, args):
        return strings.trf(key, *list(args))

    @pyqtSlot(result=str)
    def lang(self):
        return strings.lang()

    @pyqtSlot(str)
    def setLang(self, lang):
        strings.set_lang(lang)
