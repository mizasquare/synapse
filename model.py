"""Pedalboard domain model + assembler (the in-app proxy of the MODEP host).

Split out of ``modepctrl`` so the *transport* (``ModepController``, the REST
gateway) and the *model* (the dataclasses below + the builder that hydrates
them) live in separate files. The two are still one logical layer -- the local
stand-in for the host's truth -- but now have one reason to change each.

``initialize_modep_pedalboard(backend)`` takes the MODEP host seam as a required
argument and threads it through the whole assembler chain. Library code never
reaches the global ``modepctrl.get_backend()`` -- only the ``__main__`` entry
resolves it. An off-device entry point injects a fake (the presenter's
``self.backend``, ultimately ``set_backend(fake)``), serving fixtures with no Pi
hardware. Default backend is the real ``ModepController``.

The dataclasses below (EffectPort, EffectPatch, Pedalboard) are now PURE DATA --
they hold state, never reach the host. The assembler hydrates them at build time;
the presenter does live host I/O through its injected backend (parameter_set,
patch_set, ...). Out-of-band changes (web UI / HMI / snapshot recall) reach the
view via the synapsin reverse channel -> refresh_pedalboard(), not per-read polling.
"""

import configs
import os
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from modepctrl import get_backend


# Tier-2 hardcode registry (see docs/focus-control-rendering.md §4): (plugin_uri,
# symbol) -> widget kind, for monitors the heuristic gets wrong or that need a
# bespoke widget. "skip" means tier-3 (don't render). Data, not code: the
# classifier itself never names a plugin -- it only consults this map.
MONITOR_WIDGET_OVERRIDES: Dict[Tuple[str, str], str] = {}


@dataclass
class EffectPort:
	"""Represents a single port (parameter) of an Effect.

	``is_output`` flags a monitor (LV2 output control port) vs an interactive
	input control. ``widget_kind`` is the *interpretation* layer the view reads
	to pick a widget without hardcoding -- derived from LV2 properties (inputs)
	or (type/units/range) (monitors). See docs/focus-control-rendering.md."""
	instance: str
	name: str
	symbol: str
	value: float  # Current value
	min_value: Optional[float] = None
	max_value: Optional[float] = None
	default_value: Optional[float] = None
	units: Optional[str] = ""
	is_toggle: bool = False
	port_properties: List[str] = field(default_factory=list)
	range_steps: Optional[int] = None
	scale_points: Optional[List[Tuple[float, float]]] = None
	is_output: bool = False          # monitor port (output control) vs input control
	forced_kind: Optional[str] = None  # tier-2 registry override (None = use heuristic)

	@property
	def widget_kind(self) -> str:
		"""How the view should render this port (no per-plugin hardcoding here)."""
		if self.forced_kind:
			return self.forced_kind
		props = self.port_properties or []
		if self.is_output:
			return self._monitor_kind(props)
		# input control: mirror mod-ui's getTemplateData property branching
		if "enumeration" in props:
			return "enum"
		if "trigger" in props:      # check before toggled: triggers are often also toggled
			return "trigger"
		if "toggled" in props:
			return "toggle"
		if "logarithmic" in props:
			return "knob_log"
		if "integer" in props:
			return "knob_int"
		return "knob"

	def _monitor_kind(self, props) -> str:
		mn, mx = self.min_value, self.max_value
		unit = (self.units or "").strip().lower()
		if ("toggled" in props or "integer" in props) and mn == 0 and mx == 1:
			return "clip"                       # boolean-ish indicator (clip LED)
		if mn is not None and mx is not None and mn < 0 < mx:
			return "gauge"                      # symmetric around 0 (e.g. cent ±50)
		if mn == 0 and mx == 1:
			return "meter"                      # 0..1 level bar
		if unit:
			return "numeric"                    # has a real unit -> number readout
		return "numeric"                        # graceful fallback


@dataclass
class EffectPatch:
	"""Represents a patch-based parameter (e.g., IR files, NAM models)."""
	instance: str
	uri: str
	label: str
	file_types: List[str]
	file_path: str = ""
	value: str = ""
	property: str = ""

@dataclass
class Effect:
	"""Represents an effect in the pedalboard with parameters and patches."""
	instance: str  # Unique instance name
	uri: str  # Effect URI
	name: str  # Plugin name
	bypassed: bool = False
	category: List[str] = field(default_factory=list)
	brand: Optional[str] = None
	x: float = 0.0  # UI position X
	y: float = 0.0  # UI position Y
	ports: Dict[str, EffectPort] = field(default_factory=dict)
	patches: Dict[str, EffectPatch] = field(default_factory=dict)
	monitors: Dict[str, EffectPort] = field(default_factory=dict)  # output (monitor) ports
	# Ordered audio port SYMBOLS (not control ports) — the jack-side names the
	# editor needs to address cables ('/graph/<inst>/<symbol>'). Filled from the
	# plugin definition during the build; the catalog carries only ai/ao counts.
	audio_inputs: List[str] = field(default_factory=list)
	audio_outputs: List[str] = field(default_factory=list)

	@property
	def is_model_effect(self) -> bool:
		"""Model/file-based effect (NAM amp, IR cab, ...): it has at least one
		patch-file parameter, i.e. its sound comes from a loaded file rather
		than control ports alone. Category is deliberately ignored."""
		return bool(self.patches)

	@property
	def loaded_model_name(self) -> str:
		"""Basename of the first loaded patch file ('' if nothing is loaded)."""
		for patch in self.patches.values():
			if patch.value:
				return os.path.basename(patch.value)
		return ""

@dataclass
class Connection:
	"""Represents a connection between two effect ports."""
	source: str
	target: str


@dataclass
class Pedalboard:
	"""Represents a pedalboard with effects and connections."""
	title: str
	current_pb_path: str
	width: int
	height: int
	bpm: float = 999.0
	bpb: int = 99
	midi_separated_mode: bool = False
	midi_loopback: bool = False
	midi_cc_mappings: Dict[str, Tuple[int, int]] = field(default_factory=dict)  # (channel, control)
	effects: List[Effect] = field(default_factory=list)
	connections: List[Connection] = field(default_factory=list)
	audio_ins: int = 2
	audio_outs: int = 2
	cv_ins: int = 0
	cv_outs: int = 0
	ordered_instances: List[str] = field(default_factory=list)
	current_snapshot_idx: int = 0
	list_of_snapshots: List[str] = field(default_factory=list)

	def __post_init__(self):
		# Pure, in-object derivations only (connection ordering). Snapshot state is
		# supplied by the assembler as ctor args — constructing a Pedalboard no
		# longer reaches the host.
		self._order_instances()
		self._reorder_effects()

	def _order_instances(self):
		"""Orders effect instances based on their connections while treating ports correctly."""
		# Create adjacency lists
		graph = defaultdict(set)
		reverse_graph = defaultdict(set)
		nodes = set()

		def normalize_node(node):
			"""Extracts effect instance name from port-based node names."""
			return node.split('/')[0]  # Example: "Noisegate/in" -> "Noisegate"

		# Build the effect-level graph
		for conn in self.connections:
			source = normalize_node(conn.source)
			target = normalize_node(conn.target)

			if source != target:  # Avoid self-connections
				graph[source].add(target)
				reverse_graph[target].add(source)

			nodes.update([source, target])

		# Seed every effect instance, not just those that appear in a connection —
		# a plugin with no cables yet (e.g. a node just added in the editor, before
		# it's wired) must still survive ordering. Otherwise it falls out of
		# ordered_instances and _reorder_effects silently drops a real host plugin.
		nodes.update(effect.instance for effect in self.effects)

		# Identify starting nodes (audio inputs)
		start_nodes = [n for n in ["capture_1", "capture_2"] if n in nodes]
		if not start_nodes:
			start_nodes = sorted(nodes)  # Default to sorted list if no clear start

		# BFS for topological sorting
		ordered_nodes = []
		visited = set()
		queue = deque(start_nodes)

		while queue:
			node = queue.popleft()
			if node not in visited:
				visited.add(node)
				ordered_nodes.append(node)
				for neighbor in sorted(graph[node]):  # Maintain alphabetical order
					if neighbor not in visited:
						queue.append(neighbor)

		# Find orphan nodes (not visited in BFS)
		orphan_nodes = sorted(nodes - visited)

		# Store final ordered instance list (excluding standard I/O nodes)
		self.ordered_instances = [
			node for node in (ordered_nodes + orphan_nodes)
			if node not in {"capture_1", "capture_2", "playback_1", "playback_2"}
		]

	def _reorder_effects(self):
		"""Reorders the effects list based on the instance order in ordered_instances.
		Any effect not captured by the ordering (defensive — should not happen now
		that _order_instances seeds all instances) is preserved at the end so a real
		plugin is never silently dropped."""
		instance_map = {effect.instance: effect for effect in self.effects}
		ordered = [instance_map[i] for i in self.ordered_instances if i in instance_map]
		seen = set(self.ordered_instances)
		leftovers = [e for e in self.effects if e.instance not in seen]
		self.effects = ordered + leftovers

	def print_info(self):
		"""Prints detailed pedalboard information."""
		print(f"🎛️ Pedalboard: {self.title} (BPM: {self.bpm}, BPB: {self.bpb})")
		print(f"💾 Pedalboard Path: {self.current_pb_path}")
		print(f"📏 Dimensions: {self.width}x{self.height}")
		print(f"📂 Snapshots: {self.current_snapshot_idx}/{len(self.list_of_snapshots)}")
		print(f"🎚️ Effects:")
		for effect in self.effects:
			print(f"  * {effect.instance} ({effect.name}) [{effect.category}]")
			print(f"    - Bypassed: {effect.bypassed}")
			for port in effect.ports.values() if effect.ports else []:
				print(f"      * {port.name} [{port.symbol}]: {port.value} (parameter)" if not port.port_properties
					  else f"      * {port.name} [{port.symbol}]: {port.value} ({' '.join(port.port_properties)})")

			for patch in effect.patches.values() if effect.patches else []:
				print(f"      * {patch.label}: {patch.value} (Patch)")
		print("\n🔗 Connections:")
		for conn in self.connections:
			print(f"  {conn.source} ➡️ {conn.target}")

	def get_effect_by_instance(self, instance_name: str) -> Optional[Effect]:
		"""Returns the Effect object matching the given instance name."""
		return next(
			(effect for effect in self.effects if effect.instance.lower() == instance_name.lower()),
			None
		)


def _values_agree(a, b, eps: float) -> bool:
	"""Numeric-tolerant equality for a control value. Two Nones agree; a None vs a
	real value does not. Numbers compare within ``eps`` (reverse-channel values
	arrive as floats, so 0.30000001 must not read as drift); non-numerics fall
	back to ``==``."""
	if a is None or b is None:
		return a is b
	try:
		return abs(float(a) - float(b)) <= eps
	except (TypeError, ValueError):
		return a == b


def diff_live_graph(pedalboard, live, eps: float = 1e-6) -> List[str]:
	"""Compare the cached ``Pedalboard`` model against a LIVE host graph (the dict
	``backend.dump_graph()`` returns) and return human-readable drift lines —
	empty when they agree.

	This is the desync *detector*. The model is kept fresh out-of-band by the
	synapsin reverse channel (model.py module docstring); any drift here means
	that channel dropped an event (or died) and the app was holding stale state.
	We compare only what dump_graph carries: the instance set, per-instance
	bypass, control-port values, and connections. Patches (NAM/IR file state)
	aren't in the live dump, so they're out of scope here.

	Tolerant by design: a missing/None live graph yields ``[]`` (can't audit ≠
	drift) so a host hiccup never raises a false alarm. Compares only the port
	symbols present in BOTH sides — live-only ports (monitors/outputs the model
	doesn't track) are not drift."""
	if not pedalboard or not live:
		return []
	live_plugins = live.get("plugins")
	if not live_plugins:
		return []

	drift: List[str] = []

	live_by_inst: Dict[str, dict] = {}
	for p in live_plugins:
		inst = p.get("instance")
		if inst is None:
			continue
		live_by_inst[inst] = {
			"bypassed": bool(p.get("bypassed", False)),
			"ports": {pt.get("symbol"): pt.get("value")
					  for pt in p.get("ports", []) if pt.get("symbol") is not None},
		}

	model_by_inst = {e.instance: e for e in pedalboard.effects}

	# 1) instance set — structural drift (add/remove not reflected)
	for inst in sorted(set(model_by_inst) - set(live_by_inst)):
		drift.append(f"instance {inst!r} in app but not on host")
	for inst in sorted(set(live_by_inst) - set(model_by_inst)):
		drift.append(f"instance {inst!r} on host but not in app")

	# 2) bypass + 3) control-port values, for instances on both sides
	for inst in sorted(set(model_by_inst) & set(live_by_inst)):
		eff = model_by_inst[inst]
		lp = live_by_inst[inst]
		if bool(eff.bypassed) != lp["bypassed"]:
			drift.append(f"{inst}:bypass app={eff.bypassed} host={lp['bypassed']}")
		for sym, port in (eff.ports or {}).items():
			if sym not in lp["ports"]:
				continue
			if not _values_agree(port.value, lp["ports"][sym], eps):
				drift.append(f"{inst}/{sym} app={port.value} host={lp['ports'][sym]}")

	# 4) connections (bare source/target, both namespaces already normalized)
	model_conns = {(c.source, c.target) for c in pedalboard.connections}
	live_conns = {(c.get("source"), c.get("target")) for c in (live.get("connections") or [])}
	key = lambda st: (str(st[0]), str(st[1]))
	for s, t in sorted(model_conns - live_conns, key=key):
		drift.append(f"cable {s}->{t} in app but not on host")
	for s, t in sorted(live_conns - model_conns, key=key):
		drift.append(f"cable {s}->{t} on host but not in app")

	return drift


def _fetch_and_merge_graph(backend) -> Tuple[Optional[str], Optional[dict]]:
	"""Fetch the current pedalboard bundle + its on-disk info, then overlay the
	LIVE in-memory graph on top.

	Prefer the LIVE in-memory graph for plugins + connections: those are the only
	parts that diverge from disk after a live edit (add/remove/connect).
	Board-level scaffolding (title/size/hardware/timeInfo/midi) is stable, so keep
	it from the .ttl. Fall back to disk silently if the fork lacks the
	syn_dump_graph endpoint or the host is unreachable. See backend.dump_graph.

	Returns (pb_path, pb_data); pb_data is None if info retrieval failed.
	"""
	pb_path = backend.get_current_pedalboard()
	pb_data = backend.get_pedalboard_info(pb_path)
	if not pb_data:
		print("⚠️ Failed to retrieve pedalboard data.")
		return pb_path, None

	try:
		live = backend.dump_graph()
	except Exception as e:
		print(f"⚠️ dump_graph failed, using disk graph: {e}")
		live = None
	if live and live.get("plugins") is not None:
		pb_data["plugins"] = live["plugins"]
		pb_data["connections"] = live.get("connections", pb_data.get("connections", []))
	return pb_path, pb_data


def _parse_midi_cc_mappings(time_info: dict) -> Dict[str, Tuple[int, int]]:
	"""(channel, control) for the transport CCs that exist. An absent CC block is
	skipped rather than KeyError-ing the whole board load."""
	mappings: Dict[str, Tuple[int, int]] = {}
	for key, cc_key in (("bpm", "bpmCC"), ("rolling", "rollingCC")):
		cc = time_info.get(cc_key)
		if cc and "channel" in cc and "control" in cc:
			mappings[key] = (cc["channel"], cc["control"])
	return mappings


def _make_effect_info_fetcher(backend):
	"""Returns a get_effect_information(uri) that memoises per URI for the span of
	one board load — a board that uses the same plugin twice would otherwise hit
	the host (a serial socket round-trip) once per instance. Caches misses (None)
	too, so a broken plugin isn't re-queried."""
	cache: Dict[str, Optional[dict]] = {}

	def fetch(uri: str) -> Optional[dict]:
		if uri not in cache:
			cache[uri] = backend.effect_get_information(uri)
		return cache[uri]

	return fetch


def _build_input_ports(instance_name: str, effect_data: dict, detailed_info: dict) -> Dict[str, EffectPort]:
	"""Map the pedalboard's current control values onto the plugin's port defs."""
	detailed_ports = detailed_info.get("ports", {}).get("control", {}).get("input", [])
	by_symbol = {p["symbol"]: p for p in detailed_ports}

	ports: Dict[str, EffectPort] = {}
	for port_data in effect_data.get("ports", []):
		symbol = port_data["symbol"]
		current_value = port_data.get("value")
		# keep value-0 controls (0 dB gains, reset triggers, off toggles); only a
		# genuinely absent value is skipped.
		if current_value is None:
			continue
		mp = by_symbol.get(symbol)
		if not mp:
			continue
		ranges = mp.get("ranges", {})
		props = mp.get("properties", [])
		ports[symbol] = EffectPort(
			instance=instance_name,
			name=mp.get("name", symbol),
			symbol=symbol,
			value=current_value,
			min_value=ranges.get("minimum"),
			max_value=ranges.get("maximum"),
			default_value=ranges.get("default"),
			units=(mp.get("units") or {}).get("symbol", ""),
			is_toggle="toggled" in props,
			port_properties=props,
			range_steps=mp.get("rangeSteps"),
			scale_points=mp.get("scalePoints"),
		)
	return ports


def _build_monitors(instance_name: str, effect_uri: str, detailed_info: dict) -> Dict[str, EffectPort]:
	"""Monitor (output control) ports — only those the plugin flags streamable
	(gui.monitoredOutputs), looked up in ports.control.output. Atom ports (e.g.
	modspectre 'notify') aren't in control.output, so they fall through here =
	tier-3 skip automatically."""
	mon_syms = detailed_info.get("gui", {}).get("monitoredOutputs", []) or []
	out_ports = detailed_info.get("ports", {}).get("control", {}).get("output", [])
	out_by_sym = {p["symbol"]: p for p in out_ports}

	monitors: Dict[str, EffectPort] = {}
	for sym in mon_syms:
		mp = out_by_sym.get(sym)
		if not mp:
			continue
		forced = MONITOR_WIDGET_OVERRIDES.get((effect_uri, sym))
		if forced == "skip":
			continue
		rng = mp.get("ranges", {})
		monitors[sym] = EffectPort(
			instance=instance_name,
			name=mp.get("name", sym),
			symbol=sym,
			value=rng.get("default", 0.0),   # seed; live value arrives via the feed (increment 2)
			min_value=rng.get("minimum"),
			max_value=rng.get("maximum"),
			default_value=rng.get("default"),
			units=(mp.get("units") or {}).get("symbol", ""),
			port_properties=mp.get("properties", []),
			range_steps=mp.get("rangeSteps"),
			scale_points=mp.get("scalePoints"),
			is_output=True,
			forced_kind=forced,
		)
	return monitors


def _build_audio_ports(detailed_info: dict) -> Tuple[List[str], List[str]]:
	"""Audio port symbols (ordered) — the jack-side names the editor needs to wire
	cables. The catalog only has ai/ao counts, so capture the real symbols here
	while detailed_info is in hand (no extra host call)."""
	audio_ports = detailed_info.get("ports", {}).get("audio", {})
	return (
		[p["symbol"] for p in audio_ports.get("input", [])],
		[p["symbol"] for p in audio_ports.get("output", [])],
	)


def _build_patches(instance_name: str, detailed_info: dict, backend) -> Dict[str, EffectPatch]:
	"""Patch-file parameters (NAM models, IR files, ...), from the plugin's
	`parameters` section. Does a patch_get host call per valid parameter to read
	the file currently loaded into that instance."""
	patches: Dict[str, EffectPatch] = {}
	for param in detailed_info.get("parameters", []):
		if not param.get("valid"):
			continue
		patch_uri = param["uri"]
		file_path = configs.PATCH_FILE_DIR_MAP.get(
			patch_uri, configs.PATCH_FILE_DIR_MAP.get("defaultpath"))
		current_patch = backend.patch_get(instance_name, patch_uri)
		if current_patch:
			patch_value, patch_property = current_patch[0], current_patch[1]
		else:
			patch_value, patch_property = "", ""
		patches[patch_uri] = EffectPatch(
			instance=instance_name,
			uri=patch_uri,
			label=param["label"],
			file_types=param.get("fileTypes", []),
			file_path=file_path,
			value=patch_value,
			property=patch_property,
		)
	return patches


def _build_effect(effect_data: dict, get_effect_info, backend) -> Optional[Effect]:
	"""Build one Effect from its graph entry + the plugin's LV2 definition.

	Returns None (after logging) if the host can't describe the plugin, so the
	caller decides how to handle the gap — note this DROPS the plugin from the
	board, desyncing the editor view from the live graph, hence the loud log.
	"""
	instance_name = effect_data["instance"]
	effect_uri = effect_data["uri"]

	detailed_info = get_effect_info(effect_uri)
	if not detailed_info:
		print(f"⚠️ Failed to retrieve details for {effect_uri} — dropping instance "
			  f"'{instance_name}' from the board (editor view will desync).")
		return None

	audio_inputs, audio_outputs = _build_audio_ports(detailed_info)
	return Effect(
		instance=instance_name,
		uri=effect_uri,
		name=detailed_info.get("name", instance_name),
		bypassed=effect_data.get("bypassed", False),
		category=detailed_info.get("category", "Unknown"),
		brand=detailed_info.get("brand", "Unknown"),
		x=effect_data.get("x", 0.0),
		y=effect_data.get("y", 0.0),
		ports=_build_input_ports(instance_name, effect_data, detailed_info),
		patches=_build_patches(instance_name, detailed_info, backend),
		monitors=_build_monitors(instance_name, effect_uri, detailed_info),
		audio_inputs=audio_inputs,
		audio_outputs=audio_outputs,
	)


def initialize_modep_pedalboard(backend) -> Optional[Pedalboard]:
	#todo: tell modep to load the last pedalboard and snapshot
	#some parameters are desynced with the current pedalboard and pb data retrived from saved pedalboard
	"""Fetches the current pedalboard, retrieves all effect details, and constructs a Pedalboard object.

	``backend`` (the MODEP host seam) is REQUIRED — threaded through the whole
	assembler chain so library code never reaches the global. Callers inject it
	(the presenter passes ``self.backend``); only the ``__main__`` entry below
	resolves the global via ``get_backend()``."""
	pb_path, pb_data = _fetch_and_merge_graph(backend)
	if pb_data is None:
		return None

	time_info = pb_data.get("timeInfo", {})
	hardware = pb_data.get("hardware", {})
	connections = [Connection(c["source"], c["target"]) for c in pb_data.get("connections", [])]

	get_effect_info = _make_effect_info_fetcher(backend)
	effects = []
	for effect_data in pb_data.get("plugins", []):
		effect = _build_effect(effect_data, get_effect_info, backend)
		if effect is not None:
			effects.append(effect)

	return Pedalboard(
		title=pb_data.get("title", "Untitled"),
		current_pb_path=pb_path,
		width=pb_data.get("width", 0),
		height=pb_data.get("height", 0),
		bpm=time_info.get("bpm", 120.0),
		bpb=time_info.get("bpb", 4),
		midi_separated_mode=pb_data.get("midi_separated_mode", False),
		midi_loopback=pb_data.get("midi_loopback", False),
		midi_cc_mappings=_parse_midi_cc_mappings(time_info),
		effects=effects,
		connections=connections,
		audio_ins=hardware.get("audio_ins", 2),
		audio_outs=hardware.get("audio_outs", 2),
		cv_ins=hardware.get("cv_ins", 0),
		cv_outs=hardware.get("cv_outs", 0),
		# Snapshot state read here (was Pedalboard.__post_init__'s job) so the
		# dataclass stays pure data — no host I/O fires just by constructing it.
		current_snapshot_idx=backend.snapshot_current_idx(),
		list_of_snapshots=backend.get_snapshot_list(),
	)


if __name__ == '__main__':
	pedalboard = initialize_modep_pedalboard(get_backend())
	if pedalboard:
		pedalboard.print_info()
