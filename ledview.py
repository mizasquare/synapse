"""The footswitch-LED rendering surface -- the LED equivalent of QtView.

The Presenter drives TWO output surfaces: the touchscreen (``self.view`` = a rich
QtView with semantic methods like ``update_effect``) and the four footswitch LEDs.
Historically only the screen had a view object; the LEDs were poked pin-by-pin
(``hwi.LED[i] = state``) from all over the presenter -- so colour decisions, the
tuner strobe, the metronome and the boot ceremony all leaked into app logic.

``LedView`` closes that asymmetry. The presenter hands it SEMANTIC facts ("STOMP
slot 0 is engaged", "here's the latest tuner reading", "beat downbeat") and the
view owns everything visual: the colour vocabulary, blink/strobe timing, and --
crucially -- which renderer currently OWNS the surface, so a background binding
refresh can never fight the tuner strobe.

Surface owners (mutually exclusive): 'binding' (default resting colours),
'tuner', 'metronome', 'boot'. A takeover stores nothing of the binding layer --
it just suspends it; when the takeover ends the stored bindings are re-rendered.

Resting vs overlay: resting colours go through ``LED.set_resting`` so a transient
``blink`` settles back onto them (see hardwares/fsledctrl.LED). Takeovers drive
pins directly and leave _resting_state untouched, so restore is a re-render.

Colour mapping (the ONLY place LED colour taste lives): see ``_RESTING`` and the
tuner/metronome/boot code below. Per-LED state ints are 0=off 1=blue 2=red
3=purple (fsledctrl.LED.set_state).

Hardware-optional: constructed with the LED container (``hwi.LED``) which may be
absent (a fake/headless backend without LEDs) -- then every method is a no-op.
"""

import time

# Tuner LED feedback (the 4 footswitch LEDs strobe while tuning, so you can tune
# eyes-off the screen): off-pitch = a red strobe that speeds up as the note nears
# pitch; the moment it lands = a short blue flourish, then steady blue. Silence
# (engine gates on volume/confidence) = LEDs off.
TUNER_IN_TUNE_CENTS = 3.0
TUNER_FAR_CENTS = 50.0
TUNER_LED_TICK_HZ = 30.0
TUNER_BLINK_SLOW_HZ = 2.0     # far from pitch -> slow red blink
TUNER_BLINK_FAST_HZ = 10.0    # near pitch -> fast, "nervous" red blink
TUNER_CEREMONY_SEC = 0.5      # length of the blue flourish on hitting pitch

# Boot LED ceremony: a scripted ~3s light show over the 4 footswitch LEDs.
# Each frame is (delay_seconds, [s0, s1, s2, s3]) with per-LED state
# 0=off 1=blue 2=red 3=purple. Runs on the event loop (non-blocking) so the
# splash->overview handoff isn't frozen. (The SHUTDOWN show is its blocking
# mirror and lives in fsledctrl.Controller -- the event loop is gone by then.)
_BOOT_FRAMES = [
    # blue Knight-Rider sweep out and back
    (0.00, [1, 0, 0, 0]), (0.10, [0, 1, 0, 0]), (0.20, [0, 0, 1, 0]),
    (0.30, [0, 0, 0, 1]), (0.40, [0, 0, 1, 0]), (0.50, [0, 1, 0, 0]),
    (0.60, [1, 0, 0, 0]),
    # red sweep back the other way
    (0.70, [0, 0, 0, 2]), (0.80, [0, 0, 2, 0]), (0.90, [0, 2, 0, 0]),
    (1.00, [2, 0, 0, 0]),
    # purple wipe filling left->right
    (1.15, [3, 0, 0, 0]), (1.25, [3, 3, 0, 0]), (1.35, [3, 3, 3, 0]),
    (1.45, [3, 3, 3, 3]),
    # red/blue sparkle alternation
    (1.60, [1, 2, 1, 2]), (1.72, [2, 1, 2, 1]), (1.84, [1, 2, 1, 2]),
    (1.96, [2, 1, 2, 1]),
    # triple purple finale, then dark
    (2.10, [3, 3, 3, 3]), (2.25, [0, 0, 0, 0]), (2.40, [3, 3, 3, 3]),
    (2.55, [0, 0, 0, 0]), (2.70, [3, 3, 3, 3]), (2.85, [0, 0, 0, 0]),
]


class LedView:
    """Semantic rendering layer over the 4 footswitch LEDs (see module docstring)."""

    # Binding-token -> resting colour. Distinct tokens that share a colour today
    # (active/current both blue) are kept separate so the scheme can diverge later
    # without touching the presenter.
    _RESTING = {
        'active':   0b01,   # blue  -- STOMP effect engaged
        'bypassed': 0,      # off   -- STOMP effect bypassed
        'current':  0b01,   # blue  -- BANK: this slot is the loaded board
        'other':    0,      # off   -- BANK: a selectable (non-current) board
        'nav':      0,      # off   -- NAVIGATE: momentary, no resting state
        'empty':    0,      # off   -- no binding on this slot
    }

    def __init__(self, led_container, scheduler):
        # led_container: fsledctrl.LEDContainer (or a fake of the same shape), or
        # None when the hardware has no LEDs -- then everything no-ops.
        self._c = led_container
        self._sched = scheduler
        self._bindings = ['nav', 'nav', 'nav', 'nav']
        self._owner = 'binding'
        # Tuner strobe state (owned here, was smeared across the presenter).
        self._tuner_read = None       # callable -> latest reading (or None)
        self._tuner_handle = None
        self._tuner_phase = 0.0
        self._tuner_all = None        # last all-LED state written (redundant-write skip)
        self._tuner_was_in_tune = False
        self._tuner_since = 0.0

    # ── binding / resting layer ─────────────────────────────────────────────
    def set_bindings(self, tokens):
        """Store the 4 per-slot semantic tokens (see _RESTING) and, if the surface
        is idle (owner 'binding'), paint them. During a takeover they're just
        remembered and painted when it ends."""
        self._bindings = list(tokens)
        if self._owner == 'binding':
            self._render_bindings()

    def _render_bindings(self):
        if self._c is None:
            return
        for i, tok in enumerate(self._bindings):
            self._c.get_led(i).set_resting(self._RESTING.get(tok, 0))

    # ── transient overlays (only while the surface is idle) ─────────────────
    def flash(self, slot):
        """Red single blink on one LED (a footswitch press ack). Settles back to
        the slot's resting colour. Ignored during a takeover."""
        if self._c is None or self._owner != 'binding':
            return
        self._c.get_led(slot).blink(color='red', times=1, interval=0.1)

    def flash_all(self, times=2):
        """Red blink on all four LEDs (the bypass-all 'panic' confirm)."""
        if self._c is None or self._owner != 'binding':
            return
        for i in range(4):
            self._c.get_led(i).blink(color='red', times=times, interval=0.1)

    # ── boot ceremony ───────────────────────────────────────────────────────
    def boot_show(self):
        """Play the boot light show, then hand the surface back to the binding
        layer. No-op if the hardware can't drive LEDs."""
        if self._c is None:
            return
        self._owner = 'boot'
        self._c.stop_all_blinking()

        def paint(states):
            if self._owner != 'boot':
                return
            try:
                for idx, state in enumerate(states):
                    self._c[idx] = state
            except Exception:
                pass  # fake/absent LED backend -> silently skip the show
        last = 0.0
        for delay, states in _BOOT_FRAMES:
            self._sched.schedule_once(lambda dt, s=states: paint(s), delay)
            last = max(last, delay)
        self._sched.schedule_once(lambda dt: self._end_takeover('boot'), last + 0.05)

    # ── tuner strobe ────────────────────────────────────────────────────────
    def tuner_start(self, read_fn):
        """Take the surface for the tuner. ``read_fn()`` returns the latest pitch
        reading (an object with ``.cents``) or None when the engine is gating on
        silence. The strobe timing/colour mapping is owned here."""
        if self._c is None:
            return
        self._owner = 'tuner'
        self._c.stop_all_blinking()
        self._tuner_read = read_fn
        self._tuner_phase = 0.0
        self._tuner_all = None
        self._tuner_was_in_tune = False
        self._tuner_handle = self._sched.schedule_interval(
            self._tuner_tick, 1.0 / TUNER_LED_TICK_HZ)

    def tuner_stop(self):
        """End the tuner takeover and restore the binding layer."""
        if self._tuner_handle is not None:
            self._sched.unschedule(self._tuner_handle)
            self._tuner_handle = None
        self._tuner_read = None
        self._end_takeover('tuner')

    def _tuner_tick(self, dt):
        """~30 Hz: drive all 4 LEDs from the latest reading. Off-pitch = red
        strobe that speeds up as the note nears pitch; the moment it lands = a
        short blue flourish, then steady blue; silence = LEDs off."""
        read = self._tuner_read
        r = read() if read is not None else None
        if r is None:                              # engine gates on volume/confidence
            self._tuner_was_in_tune = False
            self._tuner_phase = 0.0
            self._set_all(0)
            return
        if abs(r.cents) < TUNER_IN_TUNE_CENTS:
            now = time.monotonic()
            if not self._tuner_was_in_tune:        # just landed on pitch
                self._tuner_was_in_tune = True
                self._tuner_since = now
                self._tuner_phase = 0.0
            if now - self._tuner_since < TUNER_CEREMONY_SEC:
                self._tuner_phase = (self._tuner_phase + 12.0 / TUNER_LED_TICK_HZ) % 1.0
                self._set_all(0b01 if self._tuner_phase < 0.5 else 0)   # quick blue flourish
            else:
                self._set_all(0b01)                # steady blue = in tune
            return
        # off pitch: red strobe, faster the closer to pitch
        self._tuner_was_in_tune = False
        span = TUNER_FAR_CENTS - TUNER_IN_TUNE_CENTS
        closeness = 1.0 - min(1.0, max(0.0, (abs(r.cents) - TUNER_IN_TUNE_CENTS) / span))
        blink_hz = TUNER_BLINK_SLOW_HZ + closeness * (TUNER_BLINK_FAST_HZ - TUNER_BLINK_SLOW_HZ)
        self._tuner_phase = (self._tuner_phase + blink_hz / TUNER_LED_TICK_HZ) % 1.0
        self._set_all(0b10 if self._tuner_phase < 0.5 else 0)

    def _set_all(self, state):
        """Set all 4 LEDs to ``state``, skipping redundant I2C writes."""
        if state == self._tuner_all or self._c is None:
            return
        for i in range(4):
            self._c[i] = state
        self._tuner_all = state

    # ── tap-tempo metronome ─────────────────────────────────────────────────
    def metronome_start(self):
        """Take the surface for the metronome (clears any resting paint/blink)."""
        if self._c is None:
            return
        self._owner = 'metronome'
        self._c.stop_all_blinking()

    def metronome_beat(self, slot, is_downbeat, duration):
        """Flash one LED for a beat: red downbeat / blue off-beat, off after
        ``duration``. Ignored unless the metronome owns the surface."""
        if self._c is None or self._owner != 'metronome':
            return
        self._c[slot] = 0b10 if is_downbeat else 0b01
        self._sched.schedule_once(
            lambda dt, i=slot: self._beat_off(i), duration)

    def _beat_off(self, slot):
        if self._c is not None and self._owner == 'metronome':
            self._c[slot] = 0

    def metronome_stop(self):
        """End the metronome takeover and restore the binding layer."""
        self._end_takeover('metronome')

    # ── shared ──────────────────────────────────────────────────────────────
    def _end_takeover(self, owner):
        """Return the surface to the binding layer IF ``owner`` still holds it
        (guards a stale scheduled callback firing after another takeover began)."""
        if self._owner != owner:
            return
        self._owner = 'binding'
        self._render_bindings()
