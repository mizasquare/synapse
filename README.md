# Synapse

**Synapse** is the on-device touchscreen control app for **GCaMP6s**, a Raspberry Pi-based
multi-effects guitar processor. It runs on top of [blokas](https://blokas.io/) **pisound** +
**Patchbox OS** + **MODEP**, and turns the unit's touchscreen plus its physical I/O
(footswitches, ring LEDs, expression/volume pedals) into a self-contained pedalboard
controller — no laptop or phone needed to play.

- **GCaMP6s** — the whole finished multi-effects box (the product).
- **Synapse** — this repo: the Kivy app that drives MODEP from the box's touchscreen.

> Naming note: the codebase still carries the old name in places (the Kivy window title /
> `GCaMP6sApp` class in [`app.py`](app.py), the `gcamp6s-venv` virtualenv). The intended
> end state is **Synapse = app**, **GCaMP6s = box**; a rename refactor is on the roadmap.

---

## What it does

MODEP ([mod-ui](https://github.com/moddevices/mod-ui) + [mod-host](https://github.com/moddevices/mod-host))
provides the audio engine and the LV2 plugin host. Out of the box you drive it from a web UI.
Synapse replaces that with a **purpose-built touchscreen front end** and wires in the box's
**analog I/O** so it behaves like a real stomp-box:

- Browse / switch **pedalboards** and **snapshots** from the touchscreen.
- **4 footswitches** with multiple modes (pedalboard navigation, parameter assignment,
  snapshot assignment).
- **8 ring LEDs** (4 × red/blue pairs) around the footswitches for state feedback.
- **2 pedals** (volume + expression potentiometers) mapped to MIDI CC.
- On-screen **plugin parameter** editing, **bypass** toggles, a **tuner**, and **BPM/transport** control.
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

Synapse follows a **Model–View–Presenter**-ish split, talking to MODEP over its local HTTP API:

```
                         touchscreen / footswitches / pedals
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        │                                ▼                                │
   view.py / view_widgets.py  ◄──►  presenter.py  ◄──►  modepctrl.py      │
   (Kivy UI, on-screen        (app logic, state,    (ModepController:     │
    controls, popups)          footswitch polling,   HTTP client + the    │
        ▲                       hardware glue)        pedalboard model)    │
        │                                                    │            │
        │                                                    ▼            │
   app.py  (Kivy App entry + reverse-channel socket)    mod-ui / mod-host │
        ▲                                                  (MODEP)        │
        │                                                    │            │
        └──────────── /tmp/synapsin.sock (unix dgram) ◄──────┘            │
              reverse channel: web UI / HMI changes → app sync            │
        └─────────────────────────────────────────────────────────────────┘
```

- **`app.py`** — Kivy `App` entry point. Also binds a unix-datagram socket
  (`/tmp/synapsin.sock`) and forwards MODEP's reverse-channel messages to the presenter, so
  changes made in the web UI or via HMI stay in sync with the touchscreen.
- **`presenter.py`** — application logic: footswitch polling (background thread @100 Hz),
  footswitch modes, snapshot/pedalboard state, LED feedback, and the bridge to hardware.
- **`modepctrl.py`** — `ModepController`, an HTTP client for mod-ui, plus the in-memory
  pedalboard/plugin data model. `TESTMODE` can point it at a remote MODEP for off-device dev.
- **`hardwares/`** — low-level I²C drivers (`MCP23017`, `ADS1115`, `Adafruit_I2C`) and
  `fsledctrl` (footswitch + LED controller).
- **`mywidget/` / `view_widgets.py`** — custom Kivy widgets (buttons, labels, sliders,
  toggles, file/save-as popups).
- **`volumepedal.py`** — a **standalone** process (not imported by the app) that polls the
  two pedals on the ADS1115 and emits MIDI CC to the `GAAD67` port.

### Footswitch modes
`presenter.footswitch_mode`: `0` = pedalboard navigation · `1` = parameter assign ·
`2` = pedalboard-snapshot assign.

---

## Repository layout

```
synapse/
├── app.py              # Kivy App entry + reverse-channel socket listener
├── view.py             # top-level Kivy UI (bezel, layout)
├── view_widgets.py     # composite UI widgets (patch file, param slider, toggles)
├── presenter.py        # application logic, state, footswitch polling, HW glue
├── modepctrl.py        # ModepController (mod-ui HTTP client) + pedalboard model
├── tunerpopup.py       # tuner popup UI
├── volumepedal.py      # standalone pedal → MIDI CC bridge (separate process)
├── configs.py          # paths, scale factor, fonts, socket path
├── utils.py            # helpers
├── run_synapsepy.sh    # launch script (activate venv → python app.py)
├── hardwares/          # I²C drivers + footswitch/LED controller
├── mywidget/           # custom Kivy widgets
├── mod-tweaks/         # patched mod-ui source + deploy.sh (see below)
├── resources/          # images, fonts, icons
├── docs/               # design / diagnosis notes
├── REFERENCES.md       # external + live-system references
└── *test.py            # ADStest / hwitest / test — hardware & scratch scripts
```

---

## Running

On the device (Patchbox OS), the app is launched via:

```bash
./run_synapsepy.sh          # source the venv, then: python app.py
```

Auto-start chain on boot:

```
~/.config/labwc/autostart  →  ~/run_synapsepy.sh  →  venv activate  →  python app.py
```

The repo's [`run_synapsepy.sh`](run_synapsepy.sh) is a copy of the device's original launch
script; paths (`/home/miza/...`, the `gcamp6s-venv` virtualenv) are device-specific.

**Off-device development:** set `ModepController.TESTMODE = True` in
[`modepctrl.py`](modepctrl.py) to aim the HTTP client at a remote MODEP instead of `localhost`.
Hardware-dependent paths (the I²C devices, the unix socket) still expect the real box.

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
  patch/deploy details, and known issues.
- [`docs/snapshot-sync-diagnosis.md`](docs/snapshot-sync-diagnosis.md) — snapshot sync investigation.
- [`docs/ui-migration-review.md`](docs/ui-migration-review.md) — new-UI migration review (Claude Design ↔ current bitmap UI gaps).

---

## Roadmap / known rough edges

- **Naming refactor** — converge the code on *Synapse* (app) vs *GCaMP6s* (box).
- Reverse-channel and web/HMI desync issues, plus a Wayland-incompatible `xdotool` call in
  the web-UI close path, are tracked in [`REFERENCES.md`](REFERENCES.md#알려진-이슈-세션-0-정찰).
