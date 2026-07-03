"""reflex — the box's foot-pedal MIDI device (volume + expression axes).

Named for the spinal reflex arc: foot input acts without passing through the
brain (the Synapse GUI). This process is an independent systemd service, so the
pedals keep working when the app is down — and vice versa.

It is modeled as an outboard MIDI controller that happens to live inside the
GCaMP6s box:

- *Playing* signals leave on ONE MIDI cable: both axes are sent as CC into the
  ``GAAD67`` amidithru port, which the OS feeds into the box's MIDI input
  (mod-midi-merger -> mod-host / synapse-volume). Volume rides CC 102 and
  expression CC 103 by default — deliberately in the MIDI *undefined* CC range,
  because reserved CCs (7/11) on the shared bus can trigger native handling in
  channel-listening plugins without any explicit binding. Undefined CCs bind
  only where the user maps them (mod-ui MIDI-learn, synapse-volume's listen CC).
- *Hardware management* (calibration, per-axis channel/CC assignment) happens
  over a Unix socket — the "editor app" side channel every hardware controller
  has. Synapse is the only intended client; reflex works fine without it.

Calibration and mapping are owned HERE (not by the app): a real MIDI pedal
remembers its own endpoints. Files live under ~/.modep/ (same location the old
app-owned calibration used, so existing measurements carry over).
"""
import json
import logging
import os
import socket
import threading
import time

log = logging.getLogger("reflex")

PROTOCOL_VERSION = 1

STORAGE_DIR  = os.path.expanduser("~/.modep")
CAL_PATH     = os.path.join(STORAGE_DIR, "pedal_calibration.json")
MAPPING_PATH = os.path.join(STORAGE_DIR, "reflex.json")
SOCKET_PATH  = os.path.join(STORAGE_DIR, "reflex.sock")

# amidithru virtual MIDI port created at OS level (legacy name — see docs;
# matched as a substring, so an eventual GAD67 rename stays compatible).
MIDI_PORT_NAME = "GAAD67"

# ADS1115 channel -> axis role. ch0 = volume pedal, ch1 = expression pedal.
AXES = {0: "volume", 1: "expression"}
DEFAULT_MAPPING = {
    "volume":     {"channel": 0, "cc": 102},
    "expression": {"channel": 0, "cc": 103},
}

# Measured endpoints @±4.096V FSR: toe(pressed)~17940, heel(released)~0.
DEFAULT_CAL = {0: {"in_min": 150, "in_max": 17700},
               1: {"in_min": 150, "in_max": 17700}}

POLL_INTERVAL  = 0.05   # 20 Hz pedal scan
STARTUP_MUTE_S = 3.0    # settle time before the first CC may be sent
CAPTURE_MARGIN = 0.02   # inward margin on captured span so 0/127 are reachable


# --------------------------------------------------------------- persistence
def load_calibration(path=CAL_PATH):
    """Per-channel ADS1115 calibration (in_min/in_max raw counts), stored per
    channel so each jack can hold a different pedal model without code changes.
    Missing/corrupt file falls back to the measured defaults."""
    cal = {ch: dict(v) for ch, v in DEFAULT_CAL.items()}
    if not os.path.exists(path):
        return cal
    try:
        with open(path, "r") as f:
            data = json.load(f).get("calibration", {})
        for ch, v in data.items():
            cal[int(ch)] = {"in_min": int(v["in_min"]), "in_max": int(v["in_max"])}
        return cal
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return {ch: dict(v) for ch, v in DEFAULT_CAL.items()}


def save_calibration(cal, path=CAL_PATH):
    """Persist calibration, preserving any unrelated keys in the file."""
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}
    data["calibration"] = {str(ch): v for ch, v in cal.items()}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_mapping(path=MAPPING_PATH):
    """Per-axis MIDI assignment {channel, cc}. Falls back to defaults."""
    mapping = {axis: dict(v) for axis, v in DEFAULT_MAPPING.items()}
    if not os.path.exists(path):
        return mapping
    try:
        with open(path, "r") as f:
            data = json.load(f).get("mapping", {})
        for axis, v in data.items():
            if axis in mapping:
                mapping[axis] = {"channel": int(v["channel"]), "cc": int(v["cc"])}
        return mapping
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return {axis: dict(v) for axis, v in DEFAULT_MAPPING.items()}


def save_mapping(mapping, path=MAPPING_PATH):
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}
    data["mapping"] = mapping
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ------------------------------------------------------------------ mapping
def map_value(value, in_min=150, in_max=17700, out_min=0, out_max=127):
    """Maps 16-bit ADS1115 range to 7-bit MIDI CC range with dead zones."""
    if value < in_min:
        return out_min
    elif value > in_max:
        return out_max
    return int((value - in_min) / (in_max - in_min) * (out_max - out_min) + out_min)


class ReflexState:
    """Shared state between the pedal read loop and the management socket.

    The read loop is the only writer of ``raw``/``midi``; the socket threads
    write ``pending``/``mapping``/``cal``. A single lock keeps snapshots
    consistent (all touches are trivial dict ops, contention is nil).
    """

    def __init__(self, cal_path=CAL_PATH, mapping_path=MAPPING_PATH):
        self.lock = threading.Lock()
        self.cal_path = cal_path
        self.mapping_path = mapping_path
        self.cal = load_calibration(cal_path)
        self.mapping = load_mapping(mapping_path)
        self.raw = {ch: None for ch in AXES}                 # last ADS counts
        self.midi = {axis: None for axis in AXES.values()}   # last CC value sent
        self.pending = {}    # ch -> {"heel": raw and/or "toe": raw} awaiting save
        self.midi_port = None   # resolved port name once opened, for status

    # ---- socket-side operations -------------------------------------------
    def status(self):
        with self.lock:
            return {
                "ok": True,
                "version": PROTOCOL_VERSION,
                "raw": {str(ch): self.raw[ch] for ch in self.raw},
                "midi": dict(self.midi),
                "mapping": {a: dict(v) for a, v in self.mapping.items()},
                "calibration": {str(ch): dict(v) for ch, v in self.cal.items()},
                "pending": {str(ch): dict(v) for ch, v in self.pending.items()},
                "midi_port": self.midi_port,
            }

    def capture(self, channel, end):
        """Record the current raw reading as a pending heel/toe endpoint."""
        if channel not in AXES:
            return {"ok": False, "error": f"unknown channel {channel}"}
        with self.lock:
            raw = self.raw[channel]
            if raw is None:
                return {"ok": False, "error": "no reading yet"}
            self.pending.setdefault(channel, {})[end] = raw
            return {"ok": True, "channel": channel, "end": end, "raw": raw}

    def save(self):
        """Fold pending captures into the calibration (with an inward margin so
        the ends reliably clamp to 0/127) and persist. Partial captures reuse
        the existing opposite bound."""
        with self.lock:
            if not self.pending:
                return {"ok": False, "error": "nothing captured"}
            for ch, ends in self.pending.items():
                heel = ends.get("heel", self.cal[ch]["in_min"])
                toe = ends.get("toe", self.cal[ch]["in_max"])
                lo, hi = min(heel, toe), max(heel, toe)
                margin = int((hi - lo) * CAPTURE_MARGIN)
                self.cal[ch] = {"in_min": lo + margin, "in_max": hi - margin}
            self.pending = {}
            save_calibration(self.cal, self.cal_path)
            return {"ok": True,
                    "calibration": {str(ch): dict(v) for ch, v in self.cal.items()}}

    def set_mapping(self, axis, channel, cc):
        if axis not in self.mapping:
            return {"ok": False, "error": f"unknown axis {axis!r}"}
        try:
            channel, cc = int(channel), int(cc)
        except (ValueError, TypeError):
            return {"ok": False, "error": "channel/cc must be integers"}
        if not (0 <= channel <= 15 and 0 <= cc <= 127):
            return {"ok": False, "error": "channel must be 0-15, cc 0-127"}
        with self.lock:
            self.mapping[axis] = {"channel": channel, "cc": cc}
            save_mapping(self.mapping, self.mapping_path)
            return {"ok": True, "mapping": {a: dict(v) for a, v in self.mapping.items()}}


# ------------------------------------------------------------ socket server
def handle_request(state, req):
    """One JSON request -> one JSON response. Kept apart from the socket
    plumbing so the protocol is unit-testable without sockets."""
    cmd = req.get("cmd")
    if cmd == "get_status":
        return state.status()
    if cmd == "capture_heel":
        return state.capture(int(req.get("channel", -1)), "heel")
    if cmd == "capture_toe":
        return state.capture(int(req.get("channel", -1)), "toe")
    if cmd == "save":
        return state.save()
    if cmd == "get_mapping":
        with state.lock:
            return {"ok": True, "mapping": {a: dict(v) for a, v in state.mapping.items()}}
    if cmd == "set_mapping":
        return state.set_mapping(req.get("axis"), req.get("channel", -1), req.get("cc", -1))
    return {"ok": False, "error": f"unknown cmd {cmd!r}"}


def _serve_connection(state, conn):
    try:
        buf = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    req = json.loads(line)
                    resp = handle_request(state, req)
                except (ValueError, TypeError) as exc:
                    resp = {"ok": False, "error": f"bad request: {exc}"}
                conn.sendall((json.dumps(resp) + "\n").encode())
    except OSError:
        pass   # client went away mid-exchange; nothing to clean up
    finally:
        conn.close()


def start_socket_server(state, path=SOCKET_PATH):
    """Line-oriented JSON management socket, one daemon thread per client."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        os.unlink(path)          # stale socket from a previous run
    except FileNotFoundError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(2)

    def _accept_loop():
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=_serve_connection, args=(state, conn),
                             daemon=True, name="reflex-sock").start()

    threading.Thread(target=_accept_loop, daemon=True, name="reflex-accept").start()
    log.info("management socket at %s", path)
    return srv


# -------------------------------------------------------------------- main
def _open_midi_output(mido):
    """Open the GAAD67 output if present. Returns None (retry later) when the
    amidithru port isn't up yet — calibration over the socket still works."""
    matching = [p for p in mido.get_output_names() if MIDI_PORT_NAME in p]
    if not matching:
        return None
    port = mido.open_output(matching[0])
    log.info("connected to MIDI port: %s", matching[0])
    return port


def main():
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    # Hardware/MIDI imports live here so the calibration/mapping/protocol code
    # above stays importable off-device (tests, the app's socket client).
    import mido
    from hardwares.ADS1115 import ADS1115

    ads = ADS1115(1, 0x49)
    ads.setGain(ads.PGA_4_096V)  # FSR ±4.096V: 25K TRS 분배기 상단(~2.36V)이 2.048V를 넘어 클리핑되는 것 방지
    ads.setDataRate(ads.DR_128SPS)  # 페달엔 860SPS가 과함. 느릴수록 내부평균으로 노이즈↓·입력임피던스↑ (50ms 루프에 7.8ms 변환은 여유)

    state = ReflexState()
    start_socket_server(state)

    midiout = None
    midi_retry_at = 0.0
    start_time = time.time()

    try:
        while True:
            now = time.time()
            if midiout is None and now >= midi_retry_at:
                midiout = _open_midi_output(mido)
                if midiout is None:
                    midi_retry_at = now + 2.0
                else:
                    with state.lock:
                        state.midi_port = midiout.name

            for ch, axis in AXES.items():
                raw = ads.readChannel(ch)
                with state.lock:
                    state.raw[ch] = raw
                    value = map_value(raw, **state.cal[ch])
                    assign = dict(state.mapping[axis])
                    changed = value != state.midi[axis]
                    if changed:
                        state.midi[axis] = value
                # Startup grace: seed values without sending, so a pedal that
                # rests mid-travel doesn't blast a CC the moment we boot.
                if changed and midiout and now - start_time >= STARTUP_MUTE_S:
                    try:
                        midiout.send(mido.Message(
                            'control_change', channel=assign["channel"],
                            control=assign["cc"], value=value))
                    except OSError:
                        log.warning("MIDI port lost; will reconnect")
                        midiout = None
                        with state.lock:
                            state.midi_port = None

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log.info("stopping")
        if midiout:
            midiout.close()


if __name__ == "__main__":
    main()
