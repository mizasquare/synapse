import json
import os
from configs import LOCAL_STORAGE


def load_pedal_calibration():
    """Per-channel ADS1115 pedal calibration (in_min/in_max raw counts), stored
    separately so each channel can hold a different pedal model without code
    changes. Missing/corrupt file falls back to the measured defaults below.
    Endpoints measured @±4.096V FSR: toe(pressed)~17940, heel(released)~0."""
    default = {0: {"in_min": 150, "in_max": 17700},
               1: {"in_min": 150, "in_max": 17700}}
    path = os.path.join(LOCAL_STORAGE, "pedal_calibration.json")
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            cal = json.load(f).get("calibration", {})
        # Overlay file values onto defaults so both channels are always present
        # even if the file only specifies one.
        for ch, v in cal.items():
            default[int(ch)] = {"in_min": int(v["in_min"]), "in_max": int(v["in_max"])}
        return default
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return default


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
