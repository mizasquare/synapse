"""In-memory MODEP backend for off-device development (no Pi, no mod-host).

Implements the ``backend.Backend`` surface against hand-authored (or Pi-captured)
mod-ui-shaped JSON fixtures, so the *real* pedalboard builder
(``modepctrl.initialize_modep_pedalboard``) and the model classes run unchanged
-- the fake only stands in at the object seam (see ``modepctrl.set_backend``).
No HTTP/socket wire protocol is emulated.

Reads are served from the fixtures; writes mutate in-memory state so the UI
reacts (parameter/bypass/snapshot edits, pedalboard nav) with no host. This is
fixture fidelity, not DSP -- real audio/host behaviour is out of scope for the
phase-1 Windows mock.

Each ``fixtures/*.json`` file describes one pedalboard (bank order = filename
order) with keys: ``current_pedalboard`` (bundle path), ``snapshots`` (the
``{"0": name, ...}`` map), ``snapshot_current_idx``, ``pedalboard_info`` (the
``pedalboard/info`` response the builder parses), ``effects`` (uri ->
``effect/get`` response) and optional ``patches`` (instance -> uri ->
``[value, property]``).
"""

import glob
import json
import os

import configs
from backend import Backend


class FakeModepController(Backend):
    """``Backend`` backed by JSON fixtures and mutable in-memory state."""

    def __init__(self, fixtures_dir=None):
        if fixtures_dir is None:
            here = os.path.dirname(os.path.abspath(__file__))
            fixtures_dir = os.path.join(here, "fixtures")
        self._fixtures_dir = fixtures_dir

        self._pb_order = []        # pedalboard bundle paths, in bank order
        self._pb_by_path = {}      # path -> whole fixture dict
        self._effects_by_uri = {}  # plugin uri -> effect_get_information dict
        self._catalog = []         # installed plugins (native shape) for effect_list()
        self._load_fixtures()
        self._seed_default_board()

        self._current_path = self._pb_order[0]
        self._seed_current()

        # In-memory user banks (mirrors the host's banks.json list). Seed one bank
        # holding the fixture boards so the bank manager + mode-2 have something to
        # show off-device; the bank manager mutates this via save_banks.
        self._banks = [{
            "title": "My first Bank",
            "pedalboards": [{"bundle": p,
                             "title": self._pb_by_path[p]["pedalboard_info"].get("title", "")}
                            for p in self._pb_order],
        }]

    # -- fixture loading -------------------------------------------------------
    def _load_fixtures(self):
        paths = sorted(glob.glob(os.path.join(self._fixtures_dir, "*.json")))
        if not paths:
            raise FileNotFoundError(
                "No pedalboard fixtures (*.json) in %r" % self._fixtures_dir)
        for fp in paths:
            with open(fp, "rt", encoding="utf-8") as f:
                data = json.load(f)
            if "current_pedalboard" not in data:
                # catalog dump (installed-effects.json): feed effect_list(), not a board
                if "plugins" in data:
                    self._catalog = data["plugins"]
                continue
            path = data["current_pedalboard"]
            self._pb_by_path[path] = data
            self._pb_order.append(path)
            # effect metadata is keyed by uri and may be shared across boards
            self._effects_by_uri.update(data.get("effects", {}))

    def _seed_default_board(self):
        """Synthesize the empty ``default.pedalboard`` the real host always ships.

        The editor's NEW BOARD always loads ``configs.DEFAULT_PEDALBOARD`` as a
        scratch board (editor_bridge._do_new_live_board), so without it
        set_pedalboard() fails and NEW silently aborts off device. Registered in
        ``_pb_by_path`` (so set_pedalboard finds it) but deliberately NOT in
        ``_pb_order`` -- the host hides default from board lists, and so must the
        fake (get_all_pedalboard_entries walks _pb_order).

        Built by cloning a loaded fixture and emptying the graph, so every
        structural field the pedalboard builder indexes directly (``width``,
        ``height``, ``timeInfo.bpmCC``/``rollingCC``, ...) is present -- a
        hand-authored dict would miss them (model.initialize_modep_pedalboard)."""
        import copy
        path = configs.DEFAULT_PEDALBOARD
        if path in self._pb_by_path:
            return
        data = copy.deepcopy(self._pb_by_path[self._pb_order[0]])
        data["current_pedalboard"] = path
        info = data["pedalboard_info"]
        info["title"] = "Default"
        info["plugins"] = []
        info["connections"] = []
        data["snapshots"] = {}
        data["snapshot_current_idx"] = 0
        data["patches"] = {}
        self._pb_by_path[path] = data

    def _seed_current(self):
        """(Re)build mutable state from the current pedalboard fixture. Called
        on construction and on every pedalboard switch so writes start from the
        board's stored values, mirroring a fresh host load."""
        data = self._pb_by_path[self._current_path]
        self._snapshots = dict(data.get("snapshots", {}))
        self._snapshot_idx = int(data.get("snapshot_current_idx", 0))
        # parameter + bypass stores, seeded from the board's plugin state
        self._params = {}   # (instance, symbol) -> value
        self._bypass = {}   # instance -> bool
        for plugin in data["pedalboard_info"].get("plugins", []):
            inst = plugin["instance"]
            self._bypass[inst] = bool(plugin.get("bypassed", False))
            for port in plugin.get("ports", []):
                self._params[(inst, port["symbol"])] = port["value"]
        # patch store: {instance: {uri: [value, property]}}
        self._patches = {
            inst: dict(uris) for inst, uris in data.get("patches", {}).items()
        }

    # -- Pedalboard / bank -----------------------------------------------------
    def get_current_pedalboard(self):
        return self._current_path

    def get_pedalboard_info(self, pbpath):
        data = self._pb_by_path.get(pbpath) or self._pb_by_path[self._current_path]
        return data["pedalboard_info"]

    def set_pedalboard(self, board):
        if board in self._pb_by_path:
            self._current_path = board
            self._seed_current()
            return True
        return False   # unknown bundle -> load failed (mirrors host verify)

    def get_all_pedalboard_entries(self):
        return [{"bundle": p, "title": self._pb_by_path[p]["pedalboard_info"].get("title", "")}
                for p in self._pb_order]

    def save_current_pedalboard(self):
        return True   # fixtures are in-memory; an in-place save is a no-op success

    def save_pedalboard_as(self, title):
        """Clone the current board under a new title/path and switch to it —
        mirrors the host's asNew=1 (new bundle becomes current)."""
        import copy, re
        sym = (re.sub('[^A-Za-z0-9]+', '_', title).strip('_')[:16]) or 'board'
        newpath = '/fake/%s.pedalboard' % sym
        data = copy.deepcopy(self._pb_by_path[self._current_path])
        data['current_pedalboard'] = newpath
        data['pedalboard_info']['title'] = title
        self._pb_by_path[newpath] = data
        if newpath not in self._pb_order:
            self._pb_order.append(newpath)
        self._current_path = newpath
        self._seed_current()
        return {'bundlepath': newpath, 'title': title}

    def set_next_pedalboard(self):
        i = self._pb_order.index(self._current_path)
        self._current_path = self._pb_order[(i + 1) % len(self._pb_order)]
        self._seed_current()

    def set_prev_pedalboard(self):
        i = self._pb_order.index(self._current_path)
        self._current_path = self._pb_order[(i - 1) % len(self._pb_order)]
        self._seed_current()

    def get_bank_pedalboard_entries(self, bank_id=0):
        if 0 <= bank_id < len(self._banks):
            return [{"bundle": p["bundle"], "title": p.get("title", "")}
                    for p in self._banks[bank_id].get("pedalboards", [])]
        return []

    def get_banks(self):
        import copy
        return copy.deepcopy(self._banks)

    def save_banks(self, banks):
        import copy
        self._banks = copy.deepcopy(banks)
        return True

    # -- Effect / parameter ----------------------------------------------------
    def effect_list(self):
        return self._catalog

    def effect_get_information(self, uri):
        info = self._effects_by_uri.get(uri, {})
        if info and "uri" not in info:
            # Fixture effects entries are keyed by uri and omit it inside, but the
            # real host's effect/get always carries it -- and the editor's catalog
            # self-heal (normalize_plugin) rejects an info without one, leaving the
            # fake board's nodes off the editor canvas. Fold the key back in.
            info = dict(info, uri=uri)
        return info

    def parameter_get(self, instance_id, symbol):
        if symbol == ":bypass":
            return bool(self._bypass.get(instance_id, False))
        return self._params.get((instance_id, symbol))

    def parameter_set(self, instance_id, symbol, value):
        self._params[(instance_id, symbol)] = value
        return None

    def bypass_effect(self, instance, value):
        self._bypass[instance] = bool(value)
        return None

    def patch_get(self, instance, uri):
        return self._patches.get(instance, {}).get(uri)

    def patch_set(self, instance, uri, value):
        self._patches.setdefault(instance, {})[uri] = [value, "path"]
        return None

    def preset_load(self, instance, preset_uri):
        """Apply an LV2 preset: rewrite the instance's control inputs to values
        deterministically derived from (preset uri, symbol), so different presets
        give different-but-repeatable knob positions and a subsequent
        dump_graph()/rebuild reads them back (mirrors the real host, where a
        preset is a multi-parameter change). Unknown instance/preset -> error
        string, like the host's ``false`` reply."""
        import zlib
        info = self.get_pedalboard_info(self._current_path)
        plug = next((p for p in info.get("plugins", [])
                     if p["instance"] == instance), None)
        if plug is None:
            return "no such instance: %s" % instance
        eff = self._effects_by_uri.get(plug["uri"]) or {}
        presets = eff.get("presets") or []
        if not any(pr.get("uri") == preset_uri for pr in presets):
            return "unknown preset: %s" % preset_uri
        ctrl_in = ((eff.get("ports") or {}).get("control") or {}).get("input") or []
        for c in ctrl_in:
            rng = c.get("ranges") or {}
            lo = float(rng.get("minimum", 0.0))
            hi = float(rng.get("maximum", 1.0))
            frac = (zlib.crc32(("%s|%s" % (preset_uri, c["symbol"])).encode()) % 1000) / 999.0
            self._params[(instance, c["symbol"])] = lo + frac * (hi - lo)
        return None

    # -- Live graph ------------------------------------------------------------
    def dump_graph(self):
        """Fixture-backed live graph: the current pedalboard's plugins +
        connections, with in-memory bypass/param mutations overlaid so the
        build matches what the real fork's syn_dump_graph would return."""
        info = self.get_pedalboard_info(self._current_path)
        plugins = []
        for p in info.get("plugins", []):
            inst = p["instance"]
            ports = [{"symbol": pt["symbol"],
                      "value": self._params.get((inst, pt["symbol"]), pt.get("value"))}
                     for pt in p.get("ports", [])]
            plugins.append({
                "instance": inst,
                "uri"     : p["uri"],
                "bypassed": bool(self._bypass.get(inst, p.get("bypassed", False))),
                "x"       : p.get("x", 0),
                "y"       : p.get("y", 0),
                "ports"   : ports,
            })
        return {"plugins": plugins, "connections": info.get("connections", [])}

    # -- Graph mutation --------------------------------------------------------
    # Mutate the current fixture's pedalboard_info in place so a subsequent
    # dump_graph() (and rebuild) reflects the edit -- this is what makes the
    # full add/connect/remove loop exercisable off device. get_pedalboard_info
    # returns the live dict (not a copy), so these mutations persist for the
    # session. Connection endpoints are stored bare (no '/graph/'), matching the
    # on-disk form the real host's syn_dump_graph normalizes to.
    @staticmethod
    def _bare(port):
        return port[7:] if port.startswith("/graph/") else port

    def add_effect(self, instance, uri, x=0.0, y=0.0):
        info = self.get_pedalboard_info(self._current_path)
        if not any(p["instance"] == instance for p in info["plugins"]):
            info["plugins"].append({
                "instance": instance, "uri": uri, "bypassed": False,
                "x": float(x), "y": float(y), "ports": [],
            })
            self._bypass[instance] = False
        return None

    def remove_effect(self, instance):
        info = self.get_pedalboard_info(self._current_path)
        info["plugins"] = [p for p in info["plugins"] if p["instance"] != instance]
        info["connections"] = [c for c in info["connections"]
                               if c["source"].split("/")[0] != instance
                               and c["target"].split("/")[0] != instance]
        self._bypass.pop(instance, None)
        return None

    def connect(self, port_from, port_to):
        info = self.get_pedalboard_info(self._current_path)
        c = {"source": self._bare(port_from), "target": self._bare(port_to)}
        if c not in info["connections"]:
            info["connections"].append(c)
        return None

    def disconnect(self, port_from, port_to):
        info = self.get_pedalboard_info(self._current_path)
        c = {"source": self._bare(port_from), "target": self._bare(port_to)}
        info["connections"] = [x for x in info["connections"] if x != c]
        return None

    # -- Snapshot --------------------------------------------------------------
    def snapshot_current_idx(self):
        return self._snapshot_idx

    def get_snapshot_list(self):
        return self._snapshots

    def load_snapshot(self, idx):
        if idx is not None and int(idx) >= 0:
            self._snapshot_idx = int(idx)
        return {}

    def snapshot_save(self, save_pb_also=True):
        return True

    def snapshot_save_as(self, new_name="New Snapshot", save_pb_also=True):
        new_idx = len(self._snapshots)
        self._snapshots[str(new_idx)] = new_name
        self._snapshot_idx = new_idx
        return {"ok": True, "id": new_idx}

    # -- Transport -------------------------------------------------------------
    def set_bpm(self, value):
        return None

    def set_bpb(self, value):
        # Persist into the board's timeInfo so refresh_pedalboard reads it back
        # (mirrors the host, where transport-bpb sticks to the loaded board).
        info = self._pb_by_path[self._current_path]["pedalboard_info"]
        info.setdefault("timeInfo", {})["bpb"] = int(value)
        return None
