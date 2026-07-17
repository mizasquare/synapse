"""What the *user* chose, carried across a boot.

``config.py`` holds what the **code** knows — the panel's address, which contrast
bytes are far enough apart to see. This holds what the **user** picked, which a
constant cannot be: until now SYSTEM > Brightness reset to mid on every boot,
which makes a setting a toy.

**This device is unplugged, not shut down.** It is a pedal on a power strip:
there is no clean exit to flush state in, and a write can be cut at any byte.
``docs/save-corruption-postmortem.md`` is what that costs when it goes wrong —
the lesson there is that a half-written file is not merely a lost setting, it is
a file the next boot *reads back and acts on*, and no amount of fixing the writer
afterwards repairs the disk. So this module is built around three rules:

  - **Atomic.** Write a temp file in the same directory, fsync it, ``os.replace``
    it onto the target (rename is atomic within a filesystem), then fsync the
    directory so the rename itself survives the power cut. The settings file is
    never *partially* anything: it is the old one or the new one.
  - **Forgiving.** Missing, empty, truncated, wrong-typed, or from a future
    version — none of it is an error. Each field falls back to its default on its
    own. A pedal that will not boot because a settings file has a stray byte is
    far worse than one that forgot the brightness.
  - **Immediate.** Written on the tick the value changes: not on a timer, and not
    at exit, because there is no exit. The values are few and discrete — a hand
    on a knob cannot make enough of them to trouble the card.

Seam-shaped like ``hw.oled.PanelPower``: the Runtime owns it, so the pure
controller never learns that a disk exists. ``apply(st)`` at boot, ``observe(st)``
every tick.
"""

import json
import logging
import os

from ganglion.config import BRIGHT_DEFAULT, BRIGHT_LEVELS


def _bright_ok(v):
    return isinstance(v, int) and not isinstance(v, bool) \
        and 0 <= v < len(BRIGHT_LEVELS)


# The whole schema: AppState attribute -> (default, "is this value sane?").
# Adding a setting is one line here plus the field on AppState. Each field is
# validated on its own so one bad value cannot cost the others -- a file half
# written by a newer version still yields everything this version understands.
FIELDS = {
    "bright": (BRIGHT_DEFAULT, _bright_ok),
}


def default_path():
    """``~/.modep/ganglion.json`` — beside synapse's own state.

    ``configs`` is imported lazily because this is a library module and only the
    entry point has put the repo root on ``sys.path``. Deriving from synapse's
    ``LOCAL_STORAGE`` rather than inventing a path buys the ``SYNAPSE_STATE_DIR``
    override for free — the same guard ``qt_dev`` uses so a fake-backend run can
    never write over the real device's state.
    """
    import configs
    return configs.LOCAL_STORAGE + "ganglion.json"


class Settings:
    """Load once at boot, persist on change. Never raises at the caller."""

    def __init__(self, path=None):
        self.path = path or default_path()
        self._last = None
        self._warned = False

    def apply(self, st):
        """Boot: stamp the stored choices onto the state, field by field."""
        stored = self._read()
        for k, (default, ok) in FIELDS.items():
            v = stored.get(k, default)
            if not ok(v):
                if k in stored:
                    logging.warning("ganglion settings: %s=%r rejected, using %r",
                                    k, v, default)
                v = default
            setattr(st, k, v)
        self._last = self._snapshot(st)

    def observe(self, st):
        """Every tick: write iff something the user chose actually moved."""
        cur = self._snapshot(st)
        if cur == self._last:
            return False                    # the common case: a dict compare
        self._last = cur
        self._write(cur)
        return True

    def _snapshot(self, st):
        return {k: getattr(st, k) for k in FIELDS}

    def _read(self):
        try:
            with open(self.path) as f:
                d = json.load(f)
        except FileNotFoundError:
            return {}                       # first boot: not a problem
        except (OSError, ValueError) as e:
            logging.warning("ganglion settings: %s unreadable (%s) — defaults",
                            self.path, e)
            return {}
        if not isinstance(d, dict):         # valid JSON, wrong shape — say so too
            logging.warning("ganglion settings: %s is %s, not an object — defaults",
                            self.path, type(d).__name__)
            return {}
        return d

    def _write(self, d):
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(d, f, indent=1, sort_keys=True)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())        # on the card, not in the page cache
            os.replace(tmp, self.path)      # atomic: old file or new file, never half
            fd = os.open(os.path.dirname(self.path), os.O_RDONLY)
            try:
                os.fsync(fd)                # ...and make the rename itself durable
            finally:
                os.close(fd)
        except OSError as e:
            # design.md §5 is fail-loud, but the only screen is the one the user
            # is looking at and this is a preference. A full or read-only card
            # must not take the pedal down: say so once, keep playing.
            if not self._warned:
                logging.warning("ganglion settings: cannot write %s (%s) — "
                                "settings will not survive a reboot", self.path, e)
                self._warned = True
