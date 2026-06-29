# Synapse

**Synapse** is the on-device touchscreen control app for **GCaMP6s**, a Raspberry Pi-based
multi-effects guitar processor. It runs on top of [blokas](https://blokas.io/) **pisound** +
**Patchbox OS** + **MODEP**, and turns the unit's touchscreen plus its physical I/O
(footswitches, ring LEDs, expression/volume pedals) into a self-contained pedalboard
controller — no laptop or phone needed to play.

- **GCaMP6s** — the whole finished multi-effects box (the product).
- **Synapse** — this repo: the PyQt6 + QML app that drives MODEP from the box's touchscreen.

> Naming note: the codebase still carries the old name in places (e.g. the `GAAD67` /
> `GCaMP6s` identifiers in the MIDI/host wiring). The intended end state is
> **Synapse = app**, **GCaMP6s = box**; a rename refactor is on the roadmap.

---

## What it does

MODEP ([mod-ui](https://github.com/moddevices/mod-ui) + [mod-host](https://github.com/moddevices/mod-host))
provides the audio engine and the LV2 plugin host. Out of the box you drive it from a web UI.
Synapse replaces that with a **purpose-built touchscreen front end** and wires in the box's
**analog I/O** so it behaves like a real stomp-box:

- Browse / switch **pedalboards** and **snapshots** from the touchscreen.
- **4 footswitches** with multiple modes (pedalboard navigation, STOMP effect toggles,
  BANK board select, tap tempo).
- **8 ring LEDs** (4 × red/blue pairs) around the footswitches for state feedback.
- **2 pedals** (volume + expression potentiometers) mapped to MIDI CC.
- On-screen **plugin parameter** editing, **bypass** toggles, a **tuner**, real-time
  **level meters**, **BPM/transport** control, and a touch **pedalboard editor**.
- On-demand launch of the original MODEP **web UI** for deeper editing.

---

## Hardware

| Component | Count | Interface | Address / pins | Notes |
|---|---|---|---|---|
| Footswitches | 4 | MCP23017 (I²C bus 1) | `0x27`, port A pins 0–3 | Active-low, internal pull-up; pressed → reads 1 |
| Ring LEDs | 4× red/blue pair (8) | MCP23017 (I²C bus 1) | `0x27`, port B pins 8–15 | Active-low; red/blue pins paired high→low |
| Volume pedal | 1 | ADS1115 (I²C bus 1) | `0x49`, channel 0 | Potentiometer → MIDI CC 7 |
| Expression pedal | 1 | ADS1115 (I²C bus 1) | `0x49`, channel 1 | Potentiometer → MIDI CC 11 |
| Touchscreen | 1 | `ft5x06` | `/dev/input/event9` | 7" capacitive |

*(All wiring above is derived from the code — see [`hardwares/fsledctrl.py`](hardwares/fsledctrl.py)
and [`volumepedal.py`](volumepedal.py) — not from a separate hardware spec.)*

**Platform:** Raspberry Pi 5 (RP1, `pinctrl-rp1`), 8 GB RAM · Patchbox OS · system Python 3.11 ·
MODEP 1.13.0 · labwc (Wayland) compositor · MIDI via pisound / `amidithru GAAD67`.
See [`REFERENCES.md`](REFERENCES.md) for the full live-system reference.

---

## Architecture

Synapse follows a **Model–View–Presenter**-ish split. The logic layers are toolkit- and
host-agnostic: they reach MODEP and the I²C hardware only through small **object seams**, so
the same `Presenter` runs on the Pi (real host + real hardware) and on a dev PC (fakes
injected at the seams — no separate UI fork).

```
              touchscreen / footswitches / pedals
                              │
   ┌───────────────────────────┼─────────────────────────────────┐
   │   qml/  ◄──────────►  qtview.py · editor_bridge.py           │
   │ (PyQt6+QML UI)        (QML↔presenter bridges: `view`,`editor`)│
   │                                │                             │
   │                                ▼                             │
   │                          presenter.py                        │
   │             (app logic · footswitch poll @100Hz · modes ·    │
   │              snapshot/board state · LED feedback)            │
   │                     │                       │                │
   │          backend.py seam            hardware.py seam         │
   │          ├ modepctrl  (HTTP, real)  ├ hardwares/fsledctrl(I²C)│
   │          └ fakemodep  (fixtures)    └ fakehardware (no-op)    │
   │                     │                                        │
   │                     ▼                                        │
   │            mod-ui / mod-host  (MODEP)                        │
   └───────────────────┬──────────────────────────────────────────┘
                       │  /tmp/synapsin.sock  (reverse channel)
                       ▼  web-UI / HMI edits → presenter stays in sync
```

- **Entry points** — `qt_main.py` (on-device: real `ModepController` over HTTP + real I²C
  `fsledctrl`, binds the reverse socket, starts the monitor feed + level meter) and
  `qt_dev.py` (off-device dev: fakes injected; `--shot` / `--focus` / `--real`).
  (The legacy Kivy app was removed; the Qt entries are the only path. For rollback,
  `run_synapsepy.sh.kivy-bak` + git history hold the old entry.)
- **`presenter.py`** — toolkit-agnostic application logic: footswitch polling (background
  thread @100 Hz), footswitch modes, snapshot/pedalboard state, LED feedback, and
  reverse-channel handling.
- **`model.py` / `plugincatalog.py`** — the pedalboard domain model + assembler (in-app
  proxy of the host: effects, ports, `EffectPort.widget_kind`) and the live plugin-catalog
  normaliser.
- **`backend.py`** — the **host seam**: the `Backend` surface the logic depends on. Real =
  `modepctrl.ModepController` (HTTP to mod-ui/mod-host); fake = `fakemodep` (fixtures).
  Swapped via `modepctrl.get_backend` / `set_backend`.
- **`hardware.py`** — the **control seam**: the `HardwareController` surface (footswitches +
  ring LEDs). Real = `hardwares/fsledctrl.Controller` (MCP23017 over I²C); fake =
  `fakehardware`. Selection is explicit at the entry point, never auto-fallback — a dead
  footswitch on a live stage box must surface, not pass silently.
- **`qtview.py` / `editor_bridge.py` / `qtscheduler.py`** — the Qt view: the `view` and
  `editor` QML context-property bridges, plus the GUI-thread scheduler (`QtScheduler`, the
  Qt-event-loop implementation of the `scheduler.Scheduler` seam).
- **`qml/`** — the UI: `main.qml` (overview, focus/inspector, footswitch strip, tap-tempo,
  board manager), `ControlWidget.qml` (knob/toggle/trigger/enum), `MonitorWidget.qml`
  (output-port meters + tuner), `PatchPicker.qml` (NAM/IR/cabsim file picker),
  `PedalboardEditorView.qml` (EDIT screen).
- **`monitorfeed.py` / `levelmeter.py`** — live value feeds: a passive mod-ui websocket
  listener (output/monitor ports → focus-card meters) and an own JACK client tapping
  capture/playback (overview IN/OUT level meters).
- **`taptempo.py`** — tap-tempo engine (timing math + LED metronome, no GUI/hardware imports).
- **`volumepedal.py`** — a **standalone** process (not imported by the app) that polls the
  two pedals on the ADS1115 and emits MIDI CC to the `GAAD67` port.

### Footswitch modes
`presenter.footswitch_mode`: `0` = pedalboard navigation · `1` = STOMP (4 category-filtered
effects → FS0–3) · `2` = BANK (the active bank's first 4 boards → FS0–3) · `3` = web UI ·
`4` = tap tempo.

---

## Repository layout

```
synapse/
├── qt_main.py          # on-device entry: PyQt6+QML, real MODEP + real I²C, reverse socket
├── qt_dev.py           # off-device dev entry: fake backend + fake hardware (--shot/--focus/--real)
├── qtview.py           # QtView — QML↔presenter bridge (`view` context property)
├── editor_bridge.py    # EditorBridge — pedalboard EDIT-screen brain (`editor` context property)
├── qtscheduler.py      # QtScheduler — GUI-thread scheduler on the Qt event loop
├── presenter.py        # application logic, state, footswitch polling, mode handling
├── model.py            # pedalboard domain model + assembler (in-app host proxy)
├── plugincatalog.py    # live plugin-catalog normaliser
├── backend.py          # Backend seam (host) — real = modepctrl, fake = fakemodep
├── modepctrl.py        # ModepController — mod-ui/mod-host HTTP client (real backend)
├── fakemodep.py        # in-memory MODEP backend for off-device dev
├── hardware.py         # HardwareController seam (footswitch/LED)
├── fakehardware.py     # no-op footswitch/LED controller for off-device dev
├── scheduler.py        # Scheduler seam — event-loop timer abstraction
├── monitorfeed.py      # passive mod-ui websocket → output-port meters
├── levelmeter.py       # own JACK client → overview IN/OUT level meters
├── taptempo.py         # tap-tempo engine (timing + LED metronome)
├── volumepedal.py      # standalone pedal → MIDI CC bridge (separate process)
├── configs.py          # paths, scale factor, fonts, socket path
├── utils.py            # helpers
├── run_synapsepy.sh    # launch script (activate venv → python qt_main.py)
├── qml/                # QML UI (main · ControlWidget · MonitorWidget · PatchPicker · PedalboardEditorView)
├── hardwares/          # I²C drivers (MCP23017, ADS1115, Adafruit_I2C) + fsledctrl (footswitch/LED)
├── fixtures/           # off-device dev fixtures (fake-backend JSON)
├── resources/          # images, fonts (VT323), icons
├── mod-tweaks/         # patched mod-ui source + deploy.sh (see below)
├── tests/              # qt_smoke · taptempo_selftest · stress_add_test (run from repo root)
├── tools/              # dev/bring-up scripts: dump_effects · hwitest · ADStest · test (wvkbd toggle)
├── docs/               # design / diagnosis / roadmap notes
├── REFERENCES.md       # external + live-system references
└── (untracked snapshots, not on the Qt path)
    archived/ · under_vsersion1/                     # older snapshots
```

---

## Running

On the device (Patchbox OS), the app is launched via:

```bash
./run_synapsepy.sh          # source the venv, then: python qt_main.py
```

Auto-start chain on boot:

```
~/.config/labwc/autostart  →  ~/run_synapsepy.sh  →  venv activate  →  python qt_main.py
```

The repo's [`run_synapsepy.sh`](run_synapsepy.sh) is a copy of the device's original launch
script; paths (`/home/miza/...`, the `synapse-venv` virtualenv) are device-specific. (The old
Kivy entry [`app.py`](app.py) + `gcamp6s-venv` are kept for rollback.)

**Off-device development:** the Qt mock [`qt_dev.py`](qt_dev.py) runs headless on a PC with a
fake backend + fake hardware injected at the seams — see [`requirements-dev.txt`](requirements-dev.txt).
`--shot out.png` renders one frame and quits; `--real` aims the (read-only) backend at the live
MODEP host to screenshot the actual loaded board. (Alternatively, `ModepController.TESTMODE = True`
in [`modepctrl.py`](modepctrl.py) aims the HTTP client at a remote MODEP.) Hardware-dependent
paths (the I²C devices, the unix socket) expect the real box.

---

## MODEP patches (`mod-tweaks/`)

Synapse relies on a few additions to MODEP's own Python source (custom HTTP endpoints and a
reverse-notification channel back to the app). Because editing a live instrument is risky,
the strategy is **whole-file copy**, not diff-patching:

- `mod-tweaks/{host,session,webserver}.py` are the **patched complete files**, kept
  byte-identical to the live `/usr/lib/python3/dist-packages/mod/`.
- `mod-tweaks/org/` holds the upstream originals + `.diff`s.
- [`mod-tweaks/deploy.sh`](mod-tweaks/deploy.sh) deploys them: py_compile check → timestamped
  backup → `cp` → diff verify → restart `modep-mod-ui`. Use `--check` (no sudo) to see live vs
  source drift, `--dry-run` / `--no-restart` for safer runs.
- ⚠️ `sudo ./deploy.sh` must be run by a human in the Pi's terminal (non-interactive shells
  can't sudo).

Custom endpoints added by the patches (see [`REFERENCES.md`](REFERENCES.md) for details):
`syn_set` / `syn_get` parameter routes, `syn_patch_set` / `syn_patch_get`, transport
(`/general/`), and the `notify_synapsin()` reverse notification over the unix socket.

---

## Documentation

- [`REFERENCES.md`](REFERENCES.md) — external dependencies, the live Pi as ground truth,
  and patch/deploy details.
- [`docs/qt-roadmap.md`](docs/qt-roadmap.md) — Qt app roadmap (remaining features / reliability / cleanup / boot).
- [`docs/qt-migration-FINISHED.md`](docs/qt-migration-FINISHED.md) — Qt migration archive (completed stack work: PyQt6+QML+eglfs).

---

## Roadmap / known rough edges

- **Naming refactor** — converge the code on *Synapse* (app) vs *GCaMP6s* (box).
- Dead web-UI path (`open_webui`/`close_webui` + the X11 `xdotool` call) is slated for removal in
  [`docs/qt-roadmap.md`](docs/qt-roadmap.md) Tier 3 (unused on the Qt path; obsoleted by the compositor bypass).
</content>
</invoke>
