"""Pedalboard domain model + assembler (the in-app proxy of the MODEP host).

Split out of ``modepctrl`` so the *transport* (``ModepController``, the REST
gateway) and the *model* (the dataclasses below + the builder that hydrates
them) live in separate files. The two are still one logical layer -- the local
stand-in for the host's truth -- but now have one reason to change each.

The model objects and ``initialize_modep_pedalboard`` reach the MODEP host
through ``modepctrl.get_backend()`` (never naming ``ModepController``
directly), so an off-device entry point can ``set_backend(fake)`` to serve
fixtures with no Pi hardware. Default backend is the real ``ModepController``.

NOTE: these dataclasses are *active* (EffectPort.get_value/set_value,
EffectPatch.get_patch, Pedalboard._get_list_of_snapshots reach the backend),
i.e. closer to Active Record than pure data -- a known wart, left as-is here.
"""

import configs
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

	def get_value(self):
		"""Fetch the latest value from MODEP."""
		new_value = get_backend().parameter_get(self.instance, self.symbol)
		if new_value is not None:
			self.value = new_value
			return new_value

	def set_value(self, effect_instance: str, new_value: float):
		"""Update parameter in MODEP, and sync only if the request succeeds.
		Returns the backend error string (None on success) so callers can branch."""
		error_msg = get_backend().parameter_set(effect_instance, self.symbol, new_value)
		if error_msg is None:  # Only update if MODEP successfully applied the change
			self.value = new_value
		else:
			print(f"⚠️ Failed to update {self.name} ({self.symbol}): {error_msg}")
		return error_msg


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

	def get_patch(self):
		"""Fetch the latest patch from MODEP."""
		new_patch = get_backend().patch_get(self.instance, self.uri)
		if new_patch is not None:
			self.value = new_patch
			return new_patch

	def set_patch(self, new_patch: str):
		"""Load a new patch into MODEP and update UI if successful.
		Returns the backend error string (None on success) so the presenter can
		branch — mirrors EffectPort.set_value. On success updates ``value`` (the
		loaded file); ``file_path`` stays the picker's base directory."""
		error_msg = get_backend().patch_set(self.instance, self.uri, new_patch)
		if error_msg is None:  # Only update local data if request was successful
			self.value = new_patch
		else:
			print(f"⚠️ Failed to load patch for {self.instance}: {error_msg}")
		return error_msg


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
		self._order_instances()
		self._reorder_effects()
		self._get_current_snapshot_idx()
		self._get_list_of_snapshots()

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
		"""Reorders the effects list based on the instance order in ordered_instances."""
		instance_map = {effect.instance: effect for effect in self.effects}
		self.effects = [instance_map[instance] for instance in self.ordered_instances if instance in instance_map]

	def _get_current_snapshot_idx(self):
		"""Fetches the current snapshot index from the pedalboard."""
		self.current_snapshot_idx = get_backend().snapshot_current_idx()

	def _get_list_of_snapshots(self):
		"""Fetches the list of snapshots available in the pedalboard."""
		self.list_of_snapshots = get_backend().get_snapshot_list()
		pass

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


def initialize_modep_pedalboard() -> Optional[Pedalboard]:
	#todo: tell modep to load the last pedalboard and snapshot
	#some parameters are desynced with the current pedalboard and pb data retrived from saved pedalboard
	"""Fetches the current pedalboard, retrieves all effect details, and constructs a Pedalboard object."""
	# Step 1: Get the current pedalboard bundle path
	pb_path = get_backend().get_current_pedalboard()

	# Step 2: Retrieve the pedalboard details
	pb_data = get_backend().get_pedalboard_info(pb_path)
	if not pb_data:
		print("⚠️ Failed to retrieve pedalboard data.")
		return None
	title = pb_data["title"]
	width = pb_data["width"]
	height = pb_data["height"]
	bpm = pb_data.get("timeInfo", {}).get("bpm", 120.0)
	bpb = pb_data.get("timeInfo", {}).get("bpb", 4)
	midi_separated_mode = pb_data.get("midi_separated_mode", False)
	midi_loopback = pb_data.get("midi_loopback", False)
	connections = [Connection(conn["source"], conn["target"]) for conn in pb_data["connections"]]

	# Step 3: Extract MIDI CC mappings
	midi_cc_mappings = {
		"bpm": (pb_data["timeInfo"]["bpmCC"]["channel"], pb_data["timeInfo"]["bpmCC"]["control"]),
		"rolling": (pb_data["timeInfo"]["rollingCC"]["channel"], pb_data["timeInfo"]["rollingCC"]["control"]),
	}

	effects = []
	for effect_data in pb_data["plugins"]:
		instance_name = effect_data["instance"]
		effect_uri = effect_data["uri"]
		bypassed = effect_data["bypassed"]
		x, y = effect_data["x"], effect_data["y"]

		# Step 4: Fetch detailed effect properties
		detailed_info = get_backend().effect_get_information(effect_uri)
		if not detailed_info:
			print(f"⚠️ Failed to retrieve details for {effect_uri}")
			continue

		patches = {}
		ports = {}
		monitors = {}



		# 🔥 Step 5: Identify if the effect has **patch parameters** (`parameters` section)
		for param in detailed_info.get("parameters", []):
			if param.get("valid"):
				patch_uri = param["uri"]
				patch_label = param["label"]
				file_types = param.get("fileTypes", [])
				file_path = configs.PATCH_FILE_DIR_MAP.get(patch_uri, configs.PATCH_FILE_DIR_MAP.get("defaultpath"))
		# Fetch currently loaded patch file (if any)
				current_patch = get_backend().patch_get(instance_name, patch_uri)
				if current_patch:
					patch_value = current_patch[0]
					patch_property = current_patch[1]
				else:
					patch_value, patch_property = "", ""
				# Store the patch in the effect
				patches[patch_uri] = EffectPatch(
					instance=instance_name,
					uri=patch_uri,
					label=patch_label,
					file_types=file_types,
					file_path=file_path,
					value=patch_value,
					property=patch_property
				)

		# Step 6: Map pedalboard's current parameter values to retrieved properties
		for port_data in effect_data["ports"]:
			symbol = port_data["symbol"]
			current_value = port_data["value"]
			if current_value is not None:  # keep value-0 controls (0 dB gains, reset triggers, off toggles)
				# Find detailed port info
				detailed_ports = detailed_info.get("ports", {}).get("control", {}).get("input", [])
				matching_port = next((p for p in detailed_ports if p["symbol"] == symbol), None)
				if matching_port:
					is_toggle = "toggled" in matching_port.get("properties", [])

					ports[symbol] = EffectPort(
						instance=instance_name,
						name=matching_port["name"],
						symbol=symbol,
						value=current_value,
						min_value=matching_port["ranges"]["minimum"],
						max_value=matching_port["ranges"]["maximum"],
						default_value=matching_port["ranges"]["default"],
						units=matching_port["units"]["symbol"],
						is_toggle=is_toggle,
						port_properties=matching_port.get("properties", []),
						range_steps=matching_port.get("rangeSteps"),
						scale_points=matching_port.get("scalePoints")
					)


		# Step 6b: Monitor (output control) ports — only those the plugin flags
		# streamable (gui.monitoredOutputs), looked up in ports.control.output.
		# Atom ports (e.g. modspectre 'notify') aren't in control.output, so they
		# fall through here = tier-3 skip automatically.
		mon_syms = detailed_info.get("gui", {}).get("monitoredOutputs", []) or []
		out_ports = detailed_info.get("ports", {}).get("control", {}).get("output", [])
		out_by_sym = {p["symbol"]: p for p in out_ports}
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

		# Step 7: Create the effect instance
		effects.append(Effect(
			instance=instance_name,
			uri=effect_uri,
			name=detailed_info.get("name", instance_name),
			bypassed=bypassed,
			category=detailed_info.get("category", "Unknown"),
			brand=detailed_info.get("brand", "Unknown"),
			x=x,
			y=y,
			ports=ports,
			patches=patches,  # ✅ Now correctly stores patch information
			monitors=monitors
		))

	# Step 8: Create the Pedalboard instance
	return Pedalboard(
		title=title,
		current_pb_path=pb_path,
		width=width,
		height=height,
		bpm=bpm, bpb=bpb,
		midi_separated_mode=midi_separated_mode,
		midi_loopback=midi_loopback,
		midi_cc_mappings=midi_cc_mappings,
		effects=effects,
		connections=connections,
		audio_ins=pb_data["hardware"]["audio_ins"],
		audio_outs=pb_data["hardware"]["audio_outs"],
		cv_ins=pb_data["hardware"]["cv_ins"],
		cv_outs=pb_data["hardware"]["cv_outs"]
	)


if __name__ == '__main__':
	pedalboard = initialize_modep_pedalboard()
	if pedalboard:
		pedalboard.print_info()
