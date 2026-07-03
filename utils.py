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
