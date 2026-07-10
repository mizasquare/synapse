"""Footswitch input state machine — debounce + release-edge combo latch.

Pure and thread-agnostic: feed it one raw sample per tick via ``poll()`` and it
returns the input events produced that tick. Lifted out of ``Presenter`` (was
inline in ``_footswitch_poll_loop``) so the debounce/combo semantics are
unit-testable without I2C or a poll thread, and so a per-switch press/release
event path exists for a future momentary (hold) mode.

Design note (see docs/pi-stomp-comparison.md §3A): this is the "meaning kept,
location moved" refactor. The release-edge combo semantics are preserved bit for
bit — a single press and a chord are still disambiguated by firing only once
every switch is released again. What is NEW is that the debounced press/release
edges are also surfaced as events; nothing consumes them yet (momentary mode is
a separate roadmap item), but the seam now exists.

Events are 2-tuples ``(kind, payload)``:
  ('press',   i)       debounced press edge on switch i        (payload = index)
  ('release', i)       debounced release edge on switch i       (payload = index)
  ('commit',  status)  every switch released again; status is the latched set
                       ([0/1]*count) of switches pressed during this cycle.
                       THIS drives actions (single press vs chord) — unchanged.
"""

# Event kinds (payload: int index for PRESS/RELEASE, list status for COMMIT).
FS_PRESS = 'press'
FS_RELEASE = 'release'
FS_COMMIT = 'commit'


class FootswitchReader:
    """Debounces a bank of momentary switches and emits input events.

    Owns exactly the state the presenter's poll loop used to carry inline:
    ``_stable`` (debounced switch states), ``_counts`` (consecutive disagreeing
    samples per switch), and ``_latched`` (the union of switches pressed since
    the last all-released edge, so a chord is captured even if its switches are
    released slightly out of sync).
    """

    def __init__(self, count=4, debounce_samples=3):
        # Consecutive identical raw samples required before a state change is
        # accepted (software debounce). At 100 Hz, 3 == ~30 ms: longer than
        # mechanical bounce (<10 ms) yet imperceptible to the player.
        self._count = count
        self._n = debounce_samples
        self._stable = [0] * count    # debounced switch states
        self._counts = [0] * count    # consecutive samples disagreeing with _stable
        self._latched = [0] * count   # union pressed since last all-released edge

    def poll(self, raw):
        """Feed one raw sample ``[0/1]*count`` (1 == pressed); return the list of
        events produced this tick (possibly empty).

        Same two-part logic as the old inline loop: (1) per-switch debounce that
        latches any debounced-pressed switch, then (2) fire a single ``commit``
        on the edge where every switch is released again. Press/release edges are
        emitted as they debounce, before the commit."""
        events = []
        for i in range(self._count):
            if raw[i] == self._stable[i]:
                self._counts[i] = 0
            else:
                self._counts[i] += 1
                if self._counts[i] >= self._n:
                    self._stable[i] = raw[i]
                    self._counts[i] = 0
                    # A debounced edge just settled -> surface it.
                    events.append((FS_PRESS if self._stable[i] == 1 else FS_RELEASE, i))
            # Latch any switch that is (debounced) pressed during this cycle, so
            # combos survive slightly out-of-sync releases.
            if self._stable[i] == 1:
                self._latched[i] = 1

        # Fire only once every switch is released again — release-edge firing is
        # what disambiguates a single press from a combo (chord).
        if not any(self._stable) and any(self._latched):
            status = list(self._latched)
            self._latched = [0] * self._count
            events.append((FS_COMMIT, status))
        return events
