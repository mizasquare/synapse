"""Live GecoBackend over the real synapse stack — the swap-in for FakeGeco that
the ``--live`` entry injects (decisions.md A/N). Reads map synapse's ``model``
Pedalboard to geco node/knob dicts; graph mutations go through the shared
``geco_routing`` core (the ported pedalboard-editor logic). Talks to the same
``modepctrl.ModepController`` that mod-ui drives, so it edits the live pisound
graph. No Qt, no synapse-core edits (pure-layer reuse).

Conform-on-load (user decision 2026-07-06): a board is normalised to quick-
representable shape the moment it becomes current (launch + every ``select_board``)
— cheap validate, destructive rebuild only if needed — so the app never renders a
non-representable board. Mass pre-flight over the whole library was rejected.

State ownership stays model (a): the host is the source of truth. This adapter
holds a cached ``Pedalboard`` as the read projection, refreshed after graph
mutations and updated in place after param/bypass tweaks (so a knob turn is one
host call, not a full graph re-fetch).
"""

import os
import re

from ganglion.geco_backend import GecoBackend, load_whitelist
from ganglion import geco_conform
from ganglion import geco_routing

# synapse widget_kind (model.EffectPort.widget_kind) -> geco knob kind
_KIND = {"enum": "enum", "trigger": "toggle", "toggle": "toggle",
         "knob_log": "dial", "knob_int": "dial", "knob": "dial"}


def _scale(sp):
    """mod-ui scalePoints -> label list for enum/file knobs (None if unavailable;
    ganglion.fmt then falls back to the numeric value)."""
    if not sp:
        return None
    out = [str(x["label"]) for x in sp if isinstance(x, dict) and "label" in x]
    return out or None


class GecoAdapter(GecoBackend):
    def __init__(self, be=None, conform_on_load=True):
        import modepctrl
        self.be = be or modepctrl.get_backend()
        self.conform_on_load = conform_on_load
        self._keep = geco_conform.catalog_uris()
        self._catalog = load_whitelist()
        self._uri2bucket = {p["uri"]: (b["key"], b["abbr"], p["display"])
                            for b in self._catalog for p in b["plugins"]}
        self._dircache = {}
        self._pb = None
        self._load_current()

    # -- model projection ------------------------------------------------------
    def _load_current(self):
        """(Re)build the cached Pedalboard from the host, conforming first."""
        if self.conform_on_load:
            geco_conform.conform(self.be, self._keep, apply=True, log=lambda *_: None)
        import model
        self._pb = model.initialize_modep_pedalboard(self.be)

    def _bucket_of(self, uri):
        return self._uri2bucket.get(uri, ("Utils", "UTL", None))

    def _knob(self, p):
        mn = p.min_value if p.min_value is not None else 0.0
        mx = p.max_value if p.max_value is not None else 1.0
        return {"n": p.name, "v": p.value, "mn": mn, "mx": mx, "u": p.units or "",
                "k": _KIND.get(p.widget_kind, "dial"), "scale": _scale(p.scale_points)}

    def _dirlist(self, d):
        """Files in a patch dir (cached). PATCH_FILE_DIR_MAP dirs are already
        type-segregated (configs), so no fileType filter — just skip dotfiles/dirs."""
        if d not in self._dircache:
            try:
                names = sorted(n for n in os.listdir(d)
                               if not n.startswith(".") and os.path.isfile(os.path.join(d, n)))
            except OSError:
                names = []
            self._dircache[d] = names
        return self._dircache[d]

    def _patch_knob(self, p):
        """A patch (NAM model / cab IR / ...) as a ``k='file'`` knob: the value is
        the current file, rotation walks the directory listing (accel makes long
        lists usable), set writes via ``patch_set``. Shown at the top of the node."""
        files = self._dirlist(p.file_path)
        cur = os.path.basename(p.value) if p.value else ""
        idx = files.index(cur) if cur in files else 0
        return {"n": p.label, "v": float(idx), "mn": 0.0, "mx": float(max(0, len(files) - 1)),
                "u": "", "k": "file", "scale": [os.path.splitext(f)[0] for f in files]}

    def _node(self, e):
        key, abbr, disp = self._bucket_of(e.uri)
        knobs = [self._patch_knob(p) for p in e.patches.values()] + \
                [self._knob(p) for p in e.ports.values()]
        return {"name": disp or e.name, "abbr": abbr, "bucket": key,
                "bypass": bool(e.bypassed), "empty": False, "knobs": knobs}

    # -- reads -----------------------------------------------------------------
    def board(self):
        return [self._node(e) for e in self._pb.effects]

    def boards(self):
        return [x["title"] for x in self.be.get_all_pedalboard_entries()]

    def snapshots(self):
        s = self.be.get_snapshot_list()
        if isinstance(s, dict):                             # {"0": name, "1": ...}
            return [s[k] for k in sorted(s, key=int)]
        return list(s or [])

    def catalog(self):
        return self._catalog

    # -- board / snapshot navigation -------------------------------------------
    def select(self, which, idx):
        """Board: /reset + load_bundle then conform-on-load (decision: a board is
        normalised the moment it becomes current). Snap: load_snapshot, then refresh
        the param/bypass projection. Returns the now-current index."""
        if which == "board":
            entries = self.be.get_all_pedalboard_entries()
            if not (0 <= idx < len(entries)):
                return self.current("board")
            if self.be.set_pedalboard(entries[idx]["bundle"]):
                self._load_current()               # rebuild _pb + conform
                return idx
            return self.current("board")           # load failed (host graph wiped)
        snaps = self.snapshots()
        idx = max(0, min(idx, len(snaps) - 1))
        self.be.load_snapshot(idx)
        import model
        self._pb = model.initialize_modep_pedalboard(self.be)   # snap changes params/bypass
        return idx

    def current(self, which):
        if which == "board":
            cur = (self.be.get_current_pedalboard() or "").rstrip("/")
            for i, e in enumerate(self.be.get_all_pedalboard_entries()):
                if e["bundle"].rstrip("/") == cur:
                    return i
            return 0
        cur = self.be.get_current_snapshot()        # a name or an index string
        snaps = self.snapshots()
        if cur in snaps:
            return snaps.index(cur)
        try:
            i = int(cur)
            return i if 0 <= i < len(snaps) else 0
        except (TypeError, ValueError):
            return 0

    # -- param / bypass (cheap in-place cache update) --------------------------
    def set_param(self, slot, knob, value):
        e = self._pb.effects[slot]
        patches = list(e.patches.values())           # patch-knobs occupy the low indices
        if knob < len(patches):
            p = patches[knob]
            files = self._dirlist(p.file_path)
            if not files:
                return "no files"
            i = max(0, min(len(files) - 1, int(round(value))))
            full = os.path.join(p.file_path, files[i])
            err = self.be.patch_set(e.instance, p.uri, full)
            if err is None:
                p.value = full
            return err
        p = list(e.ports.values())[knob - len(patches)]
        err = self.be.parameter_set(e.instance, p.symbol, value)
        if err is None:
            p.value = value
        return err

    def set_bypass(self, slot, on):
        e = self._pb.effects[slot]
        err = self.be.bypass_effect(e.instance, on)
        if err is None:
            e.bypassed = bool(on)
        return err

    # -- graph mutations (via the shared routing core) -------------------------
    def _reconcile(self):
        """Re-wire the live host to the canonical serial chain for the current
        effect order (``self._pb.effects``). Ports the editor's diff engine:
        connect-first then disconnect. IN = mono L (capture_1) — guitar default;
        a stereo-input system setting is a future idea (decisions.md O)."""
        nodes = [{"inst": e.instance, "ain": list(e.audio_inputs or []),
                  "aout": list(e.audio_outputs or [])} for e in self._pb.effects]
        desired = geco_routing.desired_wiring(nodes, "mono")
        tracked = geco_routing.host_wiring(self.be)
        geco_routing.reconcile(self.be, desired, tracked)

    def _mint(self, display):
        """A fresh unique bare instance name (mod-host requires uniqueness)."""
        base = re.sub(r"[^A-Za-z0-9]", "", display) or "fx"
        existing = {e.instance for e in self._pb.effects}
        name, i = base, 1
        while name in existing:
            name, i = "%s_%d" % (base, i), i + 1
        return name

    def _fetch_effect(self, inst):
        import model
        for e in model.initialize_modep_pedalboard(self.be).effects:
            if e.instance == inst:
                return e
        return None

    def move(self, slot, to):
        e = self._pb.effects.pop(slot)
        self._pb.effects.insert(to, e)
        self._reconcile()                          # live re-wire per step (decision C)
        return None

    def remove(self, slot):
        e = self._pb.effects.pop(slot)
        err = self.be.remove_effect(e.instance)    # host severs the node's cables
        self._reconcile()                          # bridge the gap: A->[gone]->B => A->B
        return err

    def place(self, slot, bucket_i, plug_i):
        """Live has no empty slots, so place = REPLACE the effect at ``slot``
        (add new -> remove old -> re-wire). Net-new insertion is the deferred
        empty-slot/append fork (decisions.md)."""
        plug = self._catalog[bucket_i]["plugins"][plug_i]
        inst = self._mint(plug["display"])
        err = self.be.add_effect(inst, plug["uri"], slot * 180.0, 300.0)
        if err is not None:
            return err                             # add failed -> old untouched
        old = self._pb.effects[slot]
        self.be.remove_effect(old.instance)
        neweff = self._fetch_effect(inst)
        if neweff is not None:
            self._pb.effects[slot] = neweff
        else:                                      # fallback: full resync (rare)
            import model
            self._pb = model.initialize_modep_pedalboard(self.be)
        self._reconcile()
        return None

    # -- persist ---------------------------------------------------------------
    def save(self, which):
        """Overwrite the current board / snapshot in place."""
        if which == "board":
            self.be.save_current_pedalboard()
        else:
            self.be.snapshot_save(save_pb_also=True)
        return None

    def save_as(self, which, after_idx, name):
        """Create a new board/snapshot named ``name`` (the host mints it and
        switches current to it); return its index in the refreshed list so the
        app selects it. Names are pre-deduped by the app's namer, so ``index`` is
        unambiguous."""
        if which == "board":
            self.be.save_pedalboard_as(name)
            names = self.boards()
        else:
            self.be.snapshot_save_as(name)
            names = self.snapshots()
        return names.index(name) if name in names else min(after_idx + 1, max(0, len(names) - 1))

    def rename(self, which, idx, name):
        if which == "snap":
            self.be.snapshot_rename(idx, name)     # modepctrl wrapper (forked mod-ui)
            self.be.save_current_pedalboard()      # host rename is in-memory only -> flush (logbook ⚠️)
            return None
        # board: no host rename endpoint -> save the (loaded) graph under the new name
        # and drop the old bundle. The 2-step glance gesture guarantees idx == current,
        # so save_pedalboard_as captures the right board (decisions.md select_board).
        entries = self.be.get_all_pedalboard_entries()
        if not (0 <= idx < len(entries)):
            return None
        old = entries[idx]["bundle"]
        self.be.save_pedalboard_as(name)           # mints new bundle from current, switches to it
        self.be.remove_pedalboard(old)             # safe now: old is no longer current
        return None

    def delete(self, which, idx):
        if which == "snap":
            self.be.snapshot_remove(idx)           # host handles current-snap deletion
            self.be.save_current_pedalboard()      # volatile until board save -> flush (logbook ⚠️)
            return max(0, min(idx, len(self.snapshots()) - 1))
        # board: remove_pedalboard can't drop the loaded board -> switch to a neighbour
        # first (idx == current, guaranteed by the 2-step manage gesture), then remove.
        entries = self.be.get_all_pedalboard_entries()
        if not (0 <= idx < len(entries)) or len(entries) <= 1:
            return idx
        target = entries[idx]["bundle"]
        alt = entries[idx - 1] if idx > 0 else entries[1]
        self.be.set_pedalboard(alt["bundle"])
        self._load_current()
        self.be.remove_pedalboard(target)
        return self.current("board")               # index of the board now loaded
