import json
import os
from configs import LOCAL_STORAGE


def load_last_bank():
    """The bank index mode-2 last mapped to, held across restarts. MOD's HMI
    (Dwarf/Duo) keeps the active bank as device state; MODEP strips that layer,
    so the app owns it here (banks.json has no 'current bank' notion)."""
    path = os.path.join(LOCAL_STORAGE, "app_state.json")
    if not os.path.exists(path):
        return 0
    try:
        with open(path, "r") as f:
            return int(json.load(f).get("last_bank", 0))
    except (ValueError, OSError, json.JSONDecodeError):
        return 0

def save_last_bank(idx):
    """Persist the active bank index, preserving any other app_state keys."""
    path = os.path.join(LOCAL_STORAGE, "app_state.json")
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}
    data["last_bank"] = int(idx)
    os.makedirs(LOCAL_STORAGE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_board_order():
    """User-controlled pedalboard order (list of bundle paths). mod-ui's
    pedalboard/list is hard-sorted by bundle path in the native layer (the app
    can't reorder it host-side), so the ordering lives here as a local overlay
    in the same app_state.json as last_bank. [] = no custom order yet."""
    path = os.path.join(LOCAL_STORAGE, "app_state.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            order = json.load(f).get("board_order", [])
        return [str(b) for b in order] if isinstance(order, list) else []
    except (ValueError, OSError, json.JSONDecodeError):
        return []


def save_board_order(bundles):
    """Persist the board-order overlay (the FULL bundle list, not a delta),
    preserving any other app_state keys."""
    path = os.path.join(LOCAL_STORAGE, "app_state.json")
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}
    data["board_order"] = [str(b) for b in bundles]
    os.makedirs(LOCAL_STORAGE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


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
