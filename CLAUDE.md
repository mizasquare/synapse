# CLAUDE.md

Guidance for AI assistants working in this repository. Read this first, then
consult [`README.md`](README.md) for the full narrative and
[`REFERENCES.md`](REFERENCES.md) for the live-system ground truth.

## What this is

**Synapse** is the on-device PyQt6 + QML touchscreen control app for **GCaMP6s**,
a Raspberry Pi 5 based multi-effects guitar processor built on
**pisound + Patchbox OS + MODEP** (mod-ui / mod-host). It replaces MODEP's web UI
with a purpose-built touchscreen front end and wires in the box's analog I/O
(4 footswitches, 8 ring LEDs, volume + expression pedals).

- **GCaMP6s** = the finished box (the product).
- **Synapse** = this repo (the app).
- Naming is mid-refactor: old identifiers (`GCaMP6s`, `GAAD67` MIDI port) still
  appear in host/MIDI wiring. Don't "fix" these casually — a rename refactor is a
  tracked roadmap item, not a drive-by change.

## Architecture in one breath

Model–View–Presenter with **object seams**. The logic layers are toolkit- and
host-agnostic and reach MODEP and the I²C hardware only through swappable seams,
so the **same `Presenter` runs on the Pi (real host + real hardware) and on a dev
PC (fakes injected)** — no separate UI fork.

```
qml/ (UI)  ─►  qtview.py / editor_bridge.py (QML↔presenter bridges)
                          │
                          ▼
                   presenter.py  (app logic, footswitch poll @100Hz, modes, LED)
                    │                      │
          backend.py seam          hardware.py seam
          ├ modepctrl (HTTP real)  ├ hardwares/fsledctrl (I²C real)
          └ fakemodep (fixtures)   └ fakehardware (no-op)
                    │
                    ▼         /tmp/synapsin.sock (reverse channel: web-UI/HMI edits → presenter)
             mod-ui / mod-host (MODEP)
```

### Key files (all flat at repo root)

| File | Role |
|---|---|
| `qt_main.py` | **On-device entry** — real `ModepController` (HTTP) + real I²C `fsledctrl`, binds reverse socket, starts monitor feed + level meter. |
| `qt_dev.py` | **Off-device dev entry** — fakes injected. `--shot out.png` (render one frame + quit), `--focus <inst>`, `--tap`, `--tuner`, `--real` (read-only against live MODEP). |
| `presenter.py` | Toolkit-agnostic application logic: footswitch polling thread, modes, snapshot/board state, LED feedback, reverse-channel handling. |
| `model.py` / `plugincatalog.py` | Pedalboard domain model + assembler (in-app host proxy); live plugin-catalog normaliser. |
| `backend.py` | **Host seam** (`Backend` surface). Real = `modepctrl`, fake = `fakemodep`. Swap via `modepctrl.get_backend` / `set_backend`. |
| `hardware.py` | **Control seam** (`HardwareController`). Real = `hardwares/fsledctrl`, fake = `fakehardware`. |
| `qtview.py` / `editor_bridge.py` / `qtscheduler.py` | Qt view: `view` + `editor` QML context bridges; GUI-thread scheduler (`Scheduler` seam impl). |
| `monitorfeed.py` / `levelmeter.py` | Live feeds: passive mod-ui websocket → focus meters; own JACK client → overview IN/OUT meters. |
| `cochlea/` | Guitar-tuner DSP package (dual NSDF+HPS pitch detection, hum notch, threaded engine). Pure numpy, own JACK client. `python -m cochlea jack` runs standalone. |
| `taptempo.py` | Tap-tempo engine (timing + LED metronome, no GUI/hardware imports). |
| `volumepedal.py` | **Standalone process** (not imported by the app) — polls pedals on ADS1115 → MIDI CC. |
| `configs.py` | Paths, socket path (`/tmp/synapsin.sock`), patch-file dir/type maps. |
| `qml/` | UI: `main.qml`, `ControlWidget.qml`, `MonitorWidget.qml`, `PatchPicker.qml`, `PedalboardEditorView.qml`. |
| `hardwares/` | I²C drivers (MCP23017, ADS1115, Adafruit_I2C) + `fsledctrl` (footswitch/LED). |

Footswitch modes (`presenter.footswitch_mode`): `0` nav · `1` STOMP · `2` BANK ·
`3` web UI · `4` tap tempo.

## Working conventions

### The seam contract (most important rule)
- The `Presenter` / `model` / `taptempo` layers must **never** import PyQt, HTTP,
  or I²C directly. They talk to `Backend`, `HardwareController`, and `Scheduler`
  seams. When adding logic, decide which side of the seam it belongs on and keep
  the abstraction intact — this is what makes off-device dev and the self-tests work.
- Seam selection (real vs fake) is **explicit at the entry point, never
  auto-fallback**. A dead footswitch on a live stage box must surface loudly, not
  silently degrade.

### Running & developing
- **On device:** `./run_synapsepy.sh` (sources `synapse-venv`, runs `python qt_main.py`). Auto-starts via `~/.config/labwc/autostart`.
- **Off device:** `python qt_dev.py` (see flags above). Deps in
  [`requirements-dev.txt`](requirements-dev.txt).
- **Qt version is pinned to 6.4.2** (`PyQt6==6.4.2` **and** `PyQt6-Qt6==6.4.2`) to
  match the Pi's apt Qt. Do **not** bump past what the Pi ships — the mock could
  start relying on QML APIs that don't exist on device. Both pins are required
  because PyQt6's own dep is unpinned `>=`.

### Tests
There is **no pytest / test runner**. Tests are self-contained scripts run from
the repo root:
- `python tests/taptempo_selftest.py` — headless, deterministic (fake scheduler + manual clock). No Qt/hardware.
- `python tests/cochlea_selftest.py` — numpy-synthesised signals assert the tuner DSP. No JACK/guitar.
- `tests/qt_smoke.py` — Qt render/touch smoke test; **runs on the Pi** (windowed or eglfs), not off-device.

When you change `taptempo.py` or `cochlea/`, run the matching self-test. When you
change presenter/view/model logic, verify with `qt_dev.py --shot` and eyeball the frame.

### MODEP patches (`mod-tweaks/`) — handle with care
Synapse depends on additions to MODEP's Python source (custom `syn_*` endpoints +
the `notify_synapsin()` reverse channel). Strategy is **whole-file copy**, not
diff-patching: `mod-tweaks/{host,session,webserver}.py` are complete files kept
byte-identical to the live `/usr/lib/python3/dist-packages/mod/`.
- `mod-tweaks/deploy.sh` deploys (py_compile → timestamped backup → cp → diff verify
  → restart `modep-mod-ui`). Use `--check` (no sudo) to see live-vs-source drift.
- ⚠️ `sudo ./deploy.sh` **must be run by a human in the Pi's terminal** — never
  attempt it from a non-interactive shell.

### Git conventions
- Commit subjects use **Conventional Commits prefixes** (`feat`, `chore`, `docs`,
  `tune`, …) with **Korean descriptions**. Match the existing style.
- Feature work lands via merge commits from short-lived branches
  (`feat/…`, `docs/…`, `chore/…`).
- Ignored/untracked by design: `.venv/`, `logs/`, `*.sock`, `archived/`,
  `under_vsersion1/`, `pedal/`, `gcamp6s-venv/` (see `.gitignore`).

## Docs map
- [`README.md`](README.md) — full overview, hardware table, repo layout.
- [`REFERENCES.md`](REFERENCES.md) — external deps, live Pi as ground truth, patch/deploy details.
- [`docs/qt-roadmap.md`](docs/qt-roadmap.md) — remaining features / reliability / cleanup / boot.
- [`docs/qt-migration-FINISHED.md`](docs/qt-migration-FINISHED.md) — completed Qt stack migration (PyQt6+QML+eglfs).
- `docs/` also holds design/diagnosis notes (save-corruption postmortem, snapshot-sync diagnosis, ui-design-rules, hardware, etc.).

## Gotchas
- The legacy **Kivy** app was removed; the Qt entries are the only path. Old refs
  (`run_synapsepy.sh.kivy-bak`, git history) exist only for rollback — don't wire
  them back in.
- The **web-UI path** (`open_webui`/`close_webui`, X11 `xdotool`) is dead on the Qt
  path and slated for removal — don't build on it.
- `qt_dev.py` forces `devicePixelRatio=1` (via `QT_ENABLE_HIGHDPI_SCALING=0`) so the
  mock matches the Pi's eglfs 800×480 pixel-for-pixel. Don't undo this when doing
  layout work.
- Device-specific paths (`/home/miza/...`, the venv, I²C device nodes, the unix
  socket) assume the real box. The repo's `run_synapsepy.sh` is a copy of the
  device's script.
</content>
</invoke>
