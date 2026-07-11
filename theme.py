"""Theme token accessors — the Python half of the single source of truth.

Loads ``theme/tokens.json`` (the language-neutral source read by BOTH this module
and QML via the injected ``Theme`` object) and exposes typed lookups. Pure: no Qt
import, so token consistency is unit-testable and this module can be imported
anywhere (editor_bridge / qtview bake resolved hex into the payloads they send to
QML, so both sides resolve from the same file — see docs/theme-tokenization-plan.md).

Color tokens are dotted names -> hex. ``port``/``bucket``/``led`` are *indirection*
maps: role -> color-token-name, resolved here so a role can point at a shared hue
yet be repointed in one place. ``scale`` is tier-name -> px; ``type`` is role ->
{scale, weight, [noFamily]} for the font hierarchy.
"""

import json
import pathlib

_PATH = pathlib.Path(__file__).parent / "theme" / "tokens.json"
_raw = json.loads(_PATH.read_text(encoding="utf-8"))

# Resolved color table: dotted token name -> hex string. Direct, no indirection.
C = {k: v for k, v in _raw["color"].items() if not k.startswith("_")}

SCALE = dict(_raw["scale"])     # tier name -> pixel size (int)
TYPE = dict(_raw["type"])       # role name -> {scale, weight, noFamily?}

_MISSING = "#ff00ff"            # loud magenta: an unmapped token should be obvious


def color(name):
    """Hex for a color token (e.g. ``"accent.green"``). Magenta if unknown."""
    return C.get(name, _MISSING)


def _resolve(indirect_map, key, default_token):
    """Resolve a role via an indirection map (role -> color-token-name) to hex."""
    token = indirect_map.get(key, default_token)
    return C.get(token, _MISSING)


def port_color(port_type):
    """Hex for a signal port type ('audio'|'midi'|'cv')."""
    return _resolve(_raw["port"], port_type, "text.secondary")


def bucket_color(bucket):
    """Hex for an effect-category bucket (e.g. 'Drive'). Falls back to mutedAlt."""
    return _resolve(_raw["bucket"], bucket, "text.mutedAlt")


def bucket_abbr(bucket):
    """3-letter badge abbreviation for a bucket (kept separate from its color)."""
    return _raw["bucketAbbr"].get(bucket, (bucket[:3].upper() if bucket else "?"))


def led_color(kind):
    """Hex for a footswitch/graph LED role ('active'|'on'|'danger'|'off')."""
    return _resolve(_raw["led"], kind, "led.off")


def alpha(name_or_hex, a):
    """A token (or raw '#rrggbb') at opacity ``a`` (0..1) as '#aarrggbb' (Qt ARGB).

    Collapses the app's alpha-derived literals (e.g. '#1f5fd0a0', 'rgba(...,0.12)')
    to one helper over the base hue, matching QML's ``Theme.alpha(...)``.
    """
    hx = C.get(name_or_hex, name_or_hex).lstrip("#")
    if len(hx) == 8:            # already has an alpha channel -> take rgb tail
        hx = hx[2:]
    aa = max(0, min(255, round(a * 255)))
    return "#{:02x}{}".format(aa, hx)


def type_spec(role):
    """Font spec dict for a type role: {'size': px, 'weight': str, 'noFamily': bool}.

    ``size`` is resolved from the role's scale tier. ``noFamily`` marks glyph roles
    that must NOT get the UI font injected (symbol Texts render with the system
    font); callers omit ``font.family`` for those.
    """
    spec = TYPE.get(role, {})
    scale = spec.get("scale", "body")
    return {
        "size": SCALE.get(scale, SCALE["body"]),
        "weight": spec.get("weight", "Normal"),
        "noFamily": bool(spec.get("noFamily", False)),
    }
