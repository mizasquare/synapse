import configs
import requests
from collections import defaultdict, deque
from urllib.parse import quote
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import os
import logging

logging.basicConfig(level=logging.INFO)

class ModepController:
	TESTMODE = False
	SERVER_URI = configs.SERVER_URI if not TESTMODE else "http://mishiro.pro:8082/"
	LOCAL_STORAGE = configs.LOCAL_STORAGE
	LAST_PEDALBOARD = configs.LAST_PEDALBOARD
	DEFAULT_PEDALBOARD = configs.DEFAULT_PEDALBOARD
	DEFAULT_BANK = configs.DEFAULT_BANK
	session = requests.Session()  # persistent session instance

	def __init__(self):
		os.makedirs(ModepController.LOCAL_STORAGE, exist_ok=True)

	@staticmethod
	def _request(method: str, endpoint: str, **kwargs):
		url = ModepController.SERVER_URI + endpoint
		try:
			response = getattr(ModepController.session, method)(url, **kwargs)
			response.raise_for_status()
			return response
		except requests.RequestException as e:
			logging.error(f"HTTP {method.upper()} failed for {url}: {e}")
			return None

	@staticmethod
	def get_all_pedalboards():
		try:
			r = ModepController._request("get", "pedalboard/list")
			if r is not None:
				return [i["bundle"] for i in r.json()]

		except Exception as e:
			logging.error(f"Error fetching pedalboards: {e}")
		return []

	@staticmethod
	def get_pedalboards_in_bank(bank_id=DEFAULT_BANK):
		result = []
		try:
			r = ModepController._request("get", "banks/")
			if r.status_code == 200:
				j = r.json()
				for i in j[bank_id]["pedalboards"]:
					result.append(i["bundle"])
		finally:
			return result

	@staticmethod
	def get_current_pedalboard():
		try:
			r = ModepController._request("get", "pedalboard/current")
			if r is not None:
				return r.content.decode('utf-8')
		except Exception as e:
			logging.error(f"Error fetching current pedalboard: {e}")
		return DEFAULT_PEDALBOARD

	@staticmethod
	def get_pedalboard_info(pbpath=DEFAULT_PEDALBOARD):
		try:
			r = ModepController._request("get", "pedalboard/info/?bundlepath=" + quote(pbpath, safe=''))
			return r.json()
		except Exception as e:
			logging.error(f"An error occurred: {e}")
			return {}

	@staticmethod
	def set_pedalboard(board):
		try:
			ModepController._request("get", "reset")
			ModepController._request("post", "pedalboard/load_bundle/?bundlepath=" + quote(board, safe=''))
		except Exception as e:
			logging.error(f"Failed to set pedalboard: {e}")

	@staticmethod
	def get_last_pedalboard():
		try:
			return open(ModepController.LAST_PEDALBOARD, "rt").read()
		except FileNotFoundError:
			logging.error("Last pedalboard file not found.")
			return Default_PEDALBOARD

	@staticmethod
	def set_last_pedalboard(board):
		try:
			with open(ModepController.LAST_PEDALBOARD, "wt") as f:
				f.write(board)
		except Exception as e:
			logging.error(f"Failed to set last pedalboard: {e}")

	@staticmethod
	def set_next_pedalboard():
		boards = ModepController.get_pedalboards_in_bank()
		if len(boards) == 0:
			print("No banks or pedalboards!")
			return
		currentName = ModepController.get_current_pedalboard()
		try:
			current_idx = boards.index(currentName)
		except ValueError:
			logging.error("Current pedalboard not in current bank, falling back to 0th pedalboard.")
			ModepController.set_pedalboard(boards[0])
			return
		next_idx = (current_idx + 1) % len(boards)
		print("Switching %s -> %s" % (boards[current_idx], boards[next_idx]))
		ModepController.set_pedalboard(boards[next_idx])

	@staticmethod
	def set_prev_pedalboard():
		boards = ModepController.get_pedalboards_in_bank()
		if len(boards) == 0:
			print("No banks or pedalboards!")
			return
		currentName = ModepController.get_current_pedalboard()

		try:
			current_idx = boards.index(currentName)
		except ValueError:
			print("Current pedalboard not in current bank, falling back to 0th pedalboard.")
			ModepController.set_pedalboard(boards[0])
			return

		if current_idx == 0:
			prev_idx = 0
		else:
			prev_idx = (current_idx - 1) % len(boards)
		print("Switching %s -> %s" % (currentName, boards[prev_idx]))
		ModepController.set_pedalboard(boards[prev_idx])

	@staticmethod
	def snapshot_current_idx():
		snapshotlist = ModepController.get_snapshot_list()   # {"0":"Default", ...} (dict)
		if not snapshotlist:
			return -1
		try:
			current = ModepController.get_current_snapshot()  # 현재 스냅샷 '이름'
			for k, v in snapshotlist.items():
				if v == current:
					return int(k)
		except Exception as e:
			logging.error(f"An error occurred: {e}")
		return -1


	@staticmethod
	def get_current_snapshot():
		try:
			r = ModepController._request("get", "snapshot/current")
			if r.status_code == 200:
				return r.content.decode('utf-8')
		except Exception as e:
			logging.error(f"Error fetching current pedalboard: {e}")
		return ""

	@staticmethod
	def get_snapshot_list():
		try:
			r = requests.get(ModepController.SERVER_URI + "snapshot/list")
			if r.status_code == 200:
				return r.json()
		except:
			pass
		return []

	@staticmethod
	def load_next_snapshot():
		currentidx = ModepController.snapshot_current_idx()
		snapshots = ModepController.get_snapshot_list()
		if len(snapshots) == 1:
			print("No another snapshot!")
			return currentidx

		next_ss = (currentidx + 1) % len(snapshots)
		print("Switching %s -> %s" % (currentidx, next_ss))
		ModepController.load_snapshot(next_ss)
		return next_ss

	@staticmethod
	def load_prev_snapshot():
		currentidx = ModepController.snapshot_current_idx()
		snapshots = ModepController.get_snapshot_list()
		if len(snapshots) == 1:
			print("No another snapshot!")
			return currentidx

		prev_ss = (currentidx - 1) % len(snapshots)
		print("Switching %s -> %s" % (currentidx, prev_ss))
		ModepController.load_snapshot(prev_ss)
		return prev_ss

	@staticmethod
	def load_snapshot(idx):
		if idx < 0:
			idx = 0 #fallback to the first snapshot
		try:
			url = f"{ModepController.SERVER_URI}snapshot/load"
			r = requests.get(url, params={'id': idx})
			if r.status_code == 200:
				return r.json()
			else:
				print("Failed to save new snapshot.", r.text)
		except Exception as e:
			print(f"An error occurred: {e}")

	@staticmethod
	def get_snapshot_name(snapshot_id=0):
		try:
			r = ModepController._request("get", "snapshot/name?id=%d" % snapshot_id)
			if r.status_code == 200:
				return r.json()
		except:
			return ""


	@staticmethod
	def snapshot_save(save_pb_also=True):
		try:
			# Send the POST request with the formatted value as payload
			r = ModepController._request("post", "snapshot/save")
			if r.status_code == 200:
				print("Snapshot saved successfully.", r.text)
				if save_pb_also:
					ModepController.save_current_pedalboard()
				return True

			else:
				print("Failed to set parameter.", r.text)

				return False

		except Exception as e:
			print(f"An error occurred: {e}")

			return False

	@staticmethod
	def snapshot_save_as(new_name="New Snapshot", save_pb_also=True):
		try:
			r = ModepController._request("get", "snapshot/saveas", params={'title': new_name})
			if r.status_code == 200:
				newindex = len(ModepController.get_snapshot_list()) - 1
				ModepController.load_snapshot(newindex) #Nessessary?
				if save_pb_also:
					ModepController.save_current_pedalboard()
				return r.json()
			else:
				logging.error("Failed to save new snapshot.", r.text)
		except Exception as e:
			logging.error(f"An error occurred: {e}")

		return

	@staticmethod
	def save_current_pedalboard():
		try:
			current_bundlepath = ModepController.get_current_pedalboard()
			title = ModepController.get_pedalboard_info(current_bundlepath)['title']
			url = f"{ModepController.SERVER_URI}pedalboard/save"
			# Send the POST request with the formatted value as payload
			r = ModepController._request("post", url, json={'title': title, 'asNew': 0})

			if r.status_code == 200:
				print("Pedalboard saved successfully.", r.text)
				return True

			else:
				logging.error("Failed to save pedalboard.", r.text)

				return False
		except:
			logging.error("Failed to save current pedalboard.")

			return False

	@staticmethod
	def effect_get_information(uri=""):
		try:
			r = ModepController._request("get", "effect/get?uri=" + quote(uri, safe=''))
			if r.status_code == 200:
				return r.json()
		except Exception as e:
			logging(f"An error occurred: {e}")
			return {}

	@staticmethod
	def bypass_effect(instance, value):
		try:
			r = ModepController._request(
				"post",
				f"effect/parameter/syn_set/graph/{quote(instance, safe='')}/:bypass",
				json={"value": bool(value)})
			if r.status_code == 200:
				return None
			else:
				return r.text
		except Exception as e:
			return f"An error occurred: {e}"

	@staticmethod
	def parameter_set(instance_id, symbol, value):
		try:
			encoded_instance_id = quote(instance_id, safe='')
			encoded_symbol = quote(symbol, safe=':')
			url = f"{ModepController.SERVER_URI}effect/parameter/syn_set/graph/{encoded_instance_id}/{encoded_symbol}"

			r = requests.post(url, json={"value": value})
			if r.status_code == 200:
				return None  # Success
			else:
				return r.text  # Error message
		except Exception as e:
			return f"An error occurred: {e}"

	@staticmethod
	def parameter_get(instance_id, symbol):
		try:
			encoded_instance_id = quote(instance_id, safe='')
			encoded_symbol = quote(symbol, safe=':')
			url = f"{ModepController.SERVER_URI}effect/parameter/syn_get/graph/{encoded_instance_id}/{encoded_symbol}"
			r = requests.get(url)
			if r.status_code == 200:
				value = r.json()

				# Special handling for bypass parameter
				if symbol == ":bypass":
					return bool(value)  # Ensure it returns a boolean

				return value  # Convert everything else to float
			else:
				print("Failed to retrieve parameter.", r.text)
		except Exception as e:
			print(f"An error occurred: {e}")

	@staticmethod
	def patch_set(instance, uri, value):
		try:
			encoded_instance = quote(instance, safe='')
			url = f"{ModepController.SERVER_URI}effect/parameter/syn_patch_set/{encoded_instance}"
			payload = {'instance': '/graph/' + instance,
					   'uri': uri,
					   'value_type': 'p', # not sure but presumably 'p'ath of lv2atom#Path
					   'value_data': value}
			r = requests.post(url, json=payload)
			if r.status_code == 200:
				return None
			else:
				return r.text
		except Exception as e:
			return f"An error occurred: {e}"

	@staticmethod
	def patch_get(instance, uri):
		try:
			url = f"{ModepController.SERVER_URI}effect/parameter/syn_get//graph/{instance}/:patch"

			r = requests.get(url)
			if r.status_code == 200:
				return r.json()[uri]
			else:
				print("Failed to retrieve patch.", r.text)
		except Exception as e:
			print(f"An error occurred: {e}")

	@staticmethod
	def set_bpm(value):
		try:
			# Construct the URL with the instance and symbol as part of the path
			url = f"{ModepController.SERVER_URI}general/"
			# Format the value similarly to the server-side logic
			formatted_value = "%.1f" % value

			# Send the POST request with the formatted value as payload
			r = requests.post(url, json={"cmd": "transport-bpm", "value": formatted_value})

			if r.status_code == 200:
				return None
			else:
				return r.text
		except Exception as e:
			return f"An error occurred: {e}"

	@staticmethod
	def set_bpb(value):
		try:
			# Construct the URL with the instance and symbol as part of the path
			url = f"{ModepController.SERVER_URI}general/"
			# Format the value similarly to the server-side logic
			formatted_value = "%.1f" % value

			# Send the POST request with the formatted value as payload
			r = requests.post(url, json={"cmd": "transport-bpb", "value": formatted_value})

			if r.status_code == 200:
				return None
			else:
				return r.text
		except Exception as e:
			return f"An error occurred: {e}"


# ── Backend seam ─────────────────────────────────────────────────────────────
# The model classes (EffectPort/EffectPatch/Pedalboard) and the module-level
# builder `initialize_modep_pedalboard` below reach the MODEP host through
# `get_backend()` instead of naming `ModepController` directly. That lets an
# off-device entry point (e.g. qt_app.py) `set_backend(fake)` to serve fixtures
# with no Pi hardware. The default is `ModepController` itself, so the on-device
# (Kivy/Pi) path is byte-for-byte unchanged — same staticmethods, no extra
# indirection. Same inject-at-the-seam pattern as scheduler.py.
_backend = None


def set_backend(backend):
	"""Install the active backend. Call once at startup, before building the
	Presenter. Pass ``None`` to fall back to the real ``ModepController``."""
	global _backend
	_backend = backend


def get_backend():
	"""Return the active backend; defaults to ``ModepController`` (real host)."""
	return _backend if _backend is not None else ModepController


@dataclass
class EffectPort:
	"""Represents a single port (parameter) of an Effect."""
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

	def get_value(self):
		"""Fetch the latest value from MODEP."""
		new_value = get_backend().parameter_get(self.instance, self.symbol)
		if new_value is not None:
			self.value = new_value
			return new_value

	def set_value(self, effect_instance: str, new_value: float):
		print('wow')
		"""Update parameter in MODEP, and sync only if the request succeeds."""
		error_msg = get_backend().parameter_set(effect_instance, self.symbol, new_value)
		if error_msg is None:  # Only update if MODEP successfully applied the change
			self.value = new_value
		else:
			print(f"⚠️ Failed to update {self.name} ({self.symbol}): {error_msg}")


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
		"""Load a new patch into MODEP and update UI if successful."""
		error_msg = get_backend().patch_set(self.instance, self.uri, new_patch)
		if error_msg is None:  # Only update local data if request was successful
			self.file_path = new_patch
		else:
			print(f"⚠️ Failed to load patch for {self.instance}: {error_msg}")


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



		# 🔥 Step 5: Identify if the effect has **patch parameters** (`parameters` section)
		for param in detailed_info.get("parameters", []):
			if param.get("valid"):
				patch_uri = param["uri"]
				patch_label = param["label"]
				file_types = param.get("fileTypes", [])
				file_path = configs.PATCH_FILE_DIR_MAP.get(patch_uri, configs.PATCH_FILE_DIR_MAP.get("defaultpath"))
				print(patch_uri)
				print(file_path)
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
			if current_value:
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
			patches=patches  # ✅ Now correctly stores patch information
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
	# Create pedalboard object
	# ModepController.set_next_pedalboard()
	# r = ModepController.set_next_pedalboard()
	# pedalboard = initialize_modep_pedalboard()
	# pedalboard.print_info()
	r = ModepController.snapshot_save()
	print(r)
	# r=pedalboard.current_pb_path
	# print(r)
	# 	# print(r)
	# 	print(pedalboard.list_of_snapshots)
	# for i in pedalboard.effects:
	# 	lala=build_view_effect(i)
	# 	print(lala)
	#
	# # Print all effects and their parameters
	# if pedalboard:
