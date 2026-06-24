# Config TODO — user-settable options

Running wishlist of things that are currently **hard-coded** but should become
user-configurable. Today config lives as flat constants in [`configs.py`](../configs.py);
a future settings layer (persisted JSON under `LOCAL_STORAGE`, editable from the
UI) is the eventual home. Until then, defaults are baked into the call sites noted
below.

## Tap tempo (`taptempo.TapTempoEngine`)

The engine already takes every one of these as a constructor kwarg, so wiring a
config just means passing values at construction (`presenter.__init__`).

| Option | Default | Notes |
|---|---|---|
| `snap_multiple` | `4` | BPM snap grid. **User asked for 4 by default; 5 / 10 selectable via config.** |
| snap grid set + priority | n/a | Stretch: allow *multiple* grids at once (e.g. 10 > 5 > 4) — snap to the coarsest grid whose nearest value is within tolerance. Needs a list + priority, not a single int. |
| `snap_tolerance` | `1.5` BPM | How close to a grid value before it snaps. |
| `snap_enabled` | `True` | Master on/off for snapping (precise entry when off). |
| `window` | `4` intervals (= 5 taps) | Moving-average length. |
| `reset_timeout` | `2.0` s | Gap that starts a fresh tap sequence. |
| `min_bpm` / `max_bpm` | `40` / `300` | Clamp range. |
| `flash_max` | `0.08` s | Beat-flash duration cap (auto-shorter at fast tempi). |
| downbeat / off-beat colors | red / blue | Hard-coded in `presenter._tap_on_beat` (LED states `0b10` / `0b01`). Could be a palette. |
| metronome LED enable | always on | Option to run tap-tempo with **no** LED metronome (silent set). |
| exit target mode | previous mode | Currently restores the mode active before entry; could be "always NAVIGATE". |

## Footswitch / modes (general)

| Option | Today | Notes |
|---|---|---|
| combo → action map | hard-coded in `presenter.handle_multiple_footswitches` | A+B=modechange, B+C=tuner(stub), C+D=tap-tempo. Make remappable. |
| `FOOTSWITCH_POLL_HZ` | `100` | Poll rate. |
| `DEBOUNCE_SAMPLES` | `3` | Debounce window (≈30 ms @100 Hz). |
| long-press / hold actions | none | Possible alternative to chords for entering modes. |

## Tuner (not built yet)

- B+C chord is reserved for a tuner mode (`handle_multiple_footswitches` stub).
  When built, give it its own config block here.
