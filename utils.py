import json
import os
from configs import LOCAL_STORAGE


def _read_app_state():
    """app_state.json as a dict. Any unreadable/invalid content — including
    valid-JSON-but-not-a-dict (``null``, a bare list from a hand edit) — folds
    to {}: load_board_order runs on EVERY footswitch NAVIGATE press, so an
    uncaught AttributeError here would kill live navigation."""
    path = os.path.join(LOCAL_STORAGE, "app_state.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (ValueError, OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_app_state(key, value):
    """Set one key in app_state.json, preserving any other keys (a non-dict
    top level is discarded rather than crashing the writer with TypeError)."""
    path = os.path.join(LOCAL_STORAGE, "app_state.json")
    data = _read_app_state()
    data[key] = value
    os.makedirs(LOCAL_STORAGE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_last_bank():
    """The bank index mode-2 last mapped to, held across restarts. MOD's HMI
    (Dwarf/Duo) keeps the active bank as device state; MODEP strips that layer,
    so the app owns it here (banks.json has no 'current bank' notion)."""
    try:
        return int(_read_app_state().get("last_bank", 0))
    except (TypeError, ValueError):
        return 0

def save_last_bank(idx):
    """Persist the active bank index, preserving any other app_state keys."""
    _write_app_state("last_bank", int(idx))


def load_board_order():
    """User-controlled pedalboard order (list of bundle paths). mod-ui's
    pedalboard/list is hard-sorted by bundle path in the native layer (the app
    can't reorder it host-side), so the ordering lives here as a local overlay
    in the same app_state.json as last_bank. [] = no custom order yet."""
    order = _read_app_state().get("board_order", [])
    return [str(b) for b in order] if isinstance(order, list) else []


def save_board_order(bundles):
    """Persist the board-order overlay (the FULL bundle list, not a delta),
    preserving any other app_state keys."""
    _write_app_state("board_order", [str(b) for b in bundles])


def apply_board_order(entries):
    """Reorder pedalboard entries (``[{'bundle',...}]``) to the saved
    board_order overlay: saved bundles first in saved order (bundles that no
    longer exist are silently skipped), then any bundle NOT in the overlay
    appended in its incoming host (ASCII) order — so a freshly saved board
    shows up at the end instead of vanishing."""
    order = load_board_order()
    if not order:
        return list(entries)
    rank = {b.rstrip("/"): i for i, b in enumerate(order)}
    known = sorted((e for e in entries if e["bundle"].rstrip("/") in rank),
                   key=lambda e: rank[e["bundle"].rstrip("/")])
    unknown = [e for e in entries if e["bundle"].rstrip("/") not in rank]
    return known + unknown
