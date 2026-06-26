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
        self._load_fixtures()

        self._current_path = self._pb_order[0]
        self._seed_current()

    # -- fixture loading -------------------------------------------------------
    def _load_fixtures(self):
        paths = sorted(glob.glob(os.path.join(self._fixtures_dir, "*.json")))
        if not paths:
            raise FileNotFoundError(
                "No pedalboard fixtures (*.json) in %r" % self._fixtures_dir)
        for fp in paths:
            with open(fp, "rt", encoding="utf-8") as f:
                data = json.load(f)
            path = data["current_pedalboard"]
            self._pb_by_path[path] = data
            self._pb_order.append(path)
            # effect metadata is keyed by uri and may be shared across boards
            self._effects_by_uri.update(data.get("effects", {}))

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
        return None

    def set_next_pedalboard(self):
        i = self._pb_order.index(self._current_path)
        self._current_path = self._pb_order[(i + 1) % len(self._pb_order)]
        self._seed_current()

    def set_prev_pedalboard(self):
        i = self._pb_order.index(self._current_path)
        self._current_path = self._pb_order[(i - 1) % len(self._pb_order)]
        self._seed_current()

    # -- Effect / parameter ----------------------------------------------------
    def effect_get_information(self, uri):
        return self._effects_by_uri.get(uri, {})

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

    # -- Snapshot --------------------------------------------------------------
    def snapshot_current_idx(self):
        return self._snapshot_idx

    def get_snapshot_list(self):
        return self._snapshots

    def load_snapshot(self, idx):
        if idx is not None and int(idx) >= 0:
            self._snapshot_idx = int(idx)
        return {}

    def set_snapshot(self, idx):
        # The real ModepController has no set_snapshot (latent bug in
        # presenter.recall_pb_ss); the fake provides a working stub so
        # footswitch mode 2 is exercisable off-device.
        return self.load_snapshot(idx)

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
        return None
