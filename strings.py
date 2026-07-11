"""User-facing string accessors — the Python half of the string single source.

Loads ``resources/strings/<lang>.json`` (the same files QML reads via the injected
``Tr`` object) and exposes ``tr(key)`` / ``trf(key, *args)``. Pure: no Qt import, so
it can be imported by editor_bridge / qtview / presenter which bake resolved text
into the payloads they push to QML — both sides resolve from the same file, exactly
like ``theme.py`` does for colors. English is the primary language; ``ko`` is a
frozen snapshot and falls back to English per missing key. See
docs/string-i18n-plan.md.
"""

import json
import pathlib

_DIR = pathlib.Path(__file__).parent / "resources" / "strings"
_LANGS = {}          # lang code -> {key: template}
_lang = "en"


def _load(lang):
    """Load and memoize a language file (drops ``_``-prefixed meta keys)."""
    if lang not in _LANGS:
        path = _DIR / "{}.json".format(lang)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        _LANGS[lang] = {k: v for k, v in data.items() if not k.startswith("_")}
    return _LANGS[lang]


# English is the base: always loaded so any language can fall back to it per-key.
_load("en")


def set_lang(lang):
    """Switch the active language ('en'|'ko'). Loads the file if not yet seen."""
    global _lang
    _load(lang)
    _lang = lang


def lang():
    """The active language code."""
    return _lang


def tr(key):
    """Template string for ``key`` in the active language.

    Falls back to English, then to a loud ``⟨key⟩`` marker so a missing key is
    obvious on screen (mirrors ``theme.py``'s magenta for unmapped colors).
    """
    cur = _LANGS.get(_lang, {})
    if key in cur:
        return cur[key]
    en = _LANGS.get("en", {})
    if key in en:
        return en[key]
    return "⟨" + key + "⟩"    # ⟨key⟩


def trf(key, *args, **kwargs):
    """``tr(key)`` formatted with ``str.format(*args, **kwargs)``.

    On a placeholder/arg mismatch, returns the raw template rather than raising —
    a garbled label is survivable, a crash mid-render is not.
    """
    try:
        return tr(key).format(*args, **kwargs)
    except (IndexError, KeyError, ValueError):
        return tr(key)
