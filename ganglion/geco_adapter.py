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

    # -- graph mutations + persist (next step) ---------------------------------
    # place / remove / move go through geco_routing (reconcile); save/save_as map
    # to save_current_pedalboard / snapshot_save[_as]. Not yet wired — the read
    # side + params land first so the real board renders before edits are live.
