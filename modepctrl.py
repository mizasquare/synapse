import configs
import requests
from urllib.parse import quote
import os
import re
import unicodedata
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
			kwargs.setdefault("timeout", 2.0)
			response = getattr(ModepController.session, method)(url, **kwargs)
			response.raise_for_status()
			return response
		except requests.RequestException as e:
			logging.error(f"HTTP {method.upper()} failed for {url}: {e}")
			return None

	@staticmethod
	def get_all_pedalboards():
		# Excludes default.pedalboard (the empty scratch template): it's never a
		# user-selectable board, so footswitch NAVIGATE must skip it (matches the
		# editor's board switcher).
		try:
			r = ModepController._request("get", "pedalboard/list")
			if r is not None:
				default = ModepController.DEFAULT_PEDALBOARD.rstrip("/")
				return [i["bundle"] for i in r.json() if i["bundle"].rstrip("/") != default]

		except Exception as e:
			logging.error(f"Error fetching pedalboards: {e}")
		return []

	@staticmethod
	def get_pedalboards_in_bank(bank_id=DEFAULT_BANK):
		result = []
		try:
			r = ModepController._request("get", "banks/")
			if r is not None and r.status_code == 200:
				j = r.json()
				for i in j[bank_id]["pedalboards"]:
					result.append(i["bundle"])
		except Exception as e:
			logging.error(f"Error fetching pedalboards in bank: {e}")
		return result

	@staticmethod
	def get_bank_pedalboard_entries(bank_id=DEFAULT_BANK):
		"""First bank's pedalboards as ``[{'bundle','title'}]`` for the mode-2 bank
		selector. Empty list if there is no such bank / it's empty / host error."""
		try:
			r = ModepController._request("get", "banks/")
			if r is not None and r.status_code == 200:
				banks = r.json()
				if 0 <= bank_id < len(banks):
					return [{"bundle": p["bundle"], "title": p.get("title", "")}
							for p in banks[bank_id].get("pedalboards", [])]
		except Exception as e:
			logging.error(f"Error fetching bank pedalboards: {e}")
		return []

	@staticmethod
	def get_current_pedalboard():
		try:
			r = ModepController._request("get", "pedalboard/current")
			if r is not None:
				return r.content.decode('utf-8')
		except Exception as e:
			logging.error(f"Error fetching current pedalboard: {e}")
		return ModepController.DEFAULT_PEDALBOARD

	@staticmethod
	def get_pedalboard_info(pbpath=DEFAULT_PEDALBOARD):
		try:
			r = ModepController._request("get", "pedalboard/info/?bundlepath=" + quote(pbpath, safe=''))
			if r is None:
				return {}
			return r.json()
		except Exception as e:
			logging.error(f"An error occurred: {e}")
			return {}

	@staticmethod
	def get_all_pedalboard_entries():
		"""All pedalboards as ``[{'bundle','title'}]`` in a single GET — the
		pedalboard/list handler already includes titles, so this avoids a
		per-board get_pedalboard_info fan-out. For the editor's live board switcher
		(M6a) and the overview board manager. Excludes default.pedalboard (empty
		scratch template — not user-selectable). Empty list on host error."""
		try:
			r = ModepController._request("get", "pedalboard/list")
			if r is not None:
				default = ModepController.DEFAULT_PEDALBOARD.rstrip("/")
				return [{"bundle": i["bundle"], "title": i.get("title", "")}
						for i in r.json() if i["bundle"].rstrip("/") != default]
		except Exception as e:
			logging.error(f"Error fetching pedalboard entries: {e}")
		return []

	@staticmethod
	def set_pedalboard(board):
		"""Load bundle ``board``: GET /reset wipes the live JACK graph, then POST
		load_bundle rebuilds it. Returns ``True`` only if the host's current
		pedalboard is ``board`` afterward, else ``False``.

		The boolean is load-bearing for the editor's switch path: /reset destroys
		the live graph *before* load_bundle, so a load_bundle failure leaves an
		EMPTY host graph. A caller that destroys+reseeds (editor_switch_pedalboard)
		must bail on ``False`` rather than paint a blank/stale canvas over the
		wiped graph and falsely report success. Footswitch callers ignore the
		return — behavior unchanged."""
		try:
			ModepController._request("get", "reset")
			ModepController._request("post", "pedalboard/load_bundle/?bundlepath=" + quote(board, safe=''))
		except Exception as e:
			logging.error(f"Failed to set pedalboard: {e}")
			return False
		# Authoritative check: the host's current bundle must now be `board`
		# (normalized) — this catches a reset-done / load_bundle-failed window that
		# _request swallows (it returns None, not an exception, on HTTP failure).
		cur = ModepController.get_current_pedalboard()
		return bool(cur) and cur.rstrip("/") == board.rstrip("/")

	@staticmethod
	def get_last_pedalboard():
		try:
			return open(ModepController.LAST_PEDALBOARD, "rt").read()
		except FileNotFoundError:
			logging.error("Last pedalboard file not found.")
			return ModepController.DEFAULT_PEDALBOARD

	@staticmethod
	def set_last_pedalboard(board):
		try:
			with open(ModepController.LAST_PEDALBOARD, "wt") as f:
				f.write(board)
		except Exception as e:
			logging.error(f"Failed to set last pedalboard: {e}")

	@staticmethod
	def set_next_pedalboard():
		# Navigate ALL pedalboards, not just the active bank: the user expects the
		# footswitch to reach every board in pedalboard/list (a bank is a curated
		# subset that silently hides boards like 'BluesBreaker' from nav).
		boards = ModepController.get_all_pedalboards()
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
		boards = ModepController.get_all_pedalboards()   # full list, not the bank (see set_next)
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
			if r is not None and r.status_code == 200:
				return r.content.decode('utf-8')
		except Exception as e:
			logging.error(f"Error fetching current pedalboard: {e}")
		return ""

	@staticmethod
	def get_snapshot_list():
		try:
			r = requests.get(ModepController.SERVER_URI + "snapshot/list", timeout=2.0)
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
			r = requests.get(url, params={'id': idx}, timeout=2.0)
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
			if r is not None and r.status_code == 200:
				return r.json()
		except:
			pass
		return ""


	@staticmethod
	def snapshot_save(save_pb_also=True):
		try:
			# Send the POST request with the formatted value as payload
			r = ModepController._request("post", "snapshot/save")
			if r is None:
				return False
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
			if r is None:
				return
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
	def _symbolify(name):
		"""Mirror mod-ui's symbolify (mod/__init__.py:188): NFKD ASCII-fold,
		collapse non-alphanumerics to '_', prefix '_' if it starts with a digit.
		mod-ui truncates this to 16 for the ttl/bundle symbol (host.py save)."""
		if not name:
			return "_"
		name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii', 'ignore')
		name = re.sub("[^_a-zA-Z0-9]+", "_", name)
		if name and name[0].isdigit():
			name = "_" + name
		return name

	@staticmethod
	def save_current_pedalboard():
		try:
			current_bundlepath = ModepController.get_current_pedalboard()
			if not current_bundlepath or not current_bundlepath.endswith('.pedalboard'):
				logging.error("save_current_pedalboard aborted: no valid current bundlepath (%r)", current_bundlepath)
				return False
			dir_basename = os.path.basename(current_bundlepath)[:-len('.pedalboard')]
			info = ModepController.get_pedalboard_info(current_bundlepath)
			title = (info or {}).get('title', '')

			# GUARD (root-cause fix): mod-ui's asNew=0 save writes the ttl into the
			# CURRENT bundle dir but names it symbolify(title)[:16]. If the title's
			# symbol diverges from the dir, the save creates a mismatched ttl and
			# orphans the real one -- exactly how Exct_NAM_Widr.pedalboard got a
			# Crunch_0.ttl (a foreign title was read for the wrong board). Refuse +
			# log so a wrong-title read can never corrupt a bundle (and is visible
			# for live repro). The dir is symbolify(title)[:16], optionally with a
			# mod-ui '-NNNN' collision suffix, so accept either form.
			sym = ModepController._symbolify(title)[:16]
			if not (dir_basename == sym or dir_basename.startswith(sym + "-")):
				logging.error("save_current_pedalboard aborted: title %r (sym=%r) does not match "
							  "bundle dir %r; refusing to rename/orphan the ttl", title, sym, dir_basename)
				return False

			# Send FORM-encoded (data=), NOT json=: the PedalboardSave handler reads
			# get_argument('title'/'asNew'), which only sees query/form fields -- a
			# JSON body leaves them empty -> 400. Mirrors the web UI's $.ajax.
			r = ModepController._request("post", "pedalboard/save", data={'title': title, 'asNew': 0})

			if r is None:
				return False
			if r.status_code == 200:
				print("Pedalboard saved successfully.", r.text)
				return True
			logging.error("Failed to save pedalboard. %s", r.text)
			return False
		except Exception as e:
			logging.error("Failed to save current pedalboard: %s", e)
			return False

	@staticmethod
	def save_pedalboard_as(title):
		"""Save the current live graph as a NEW pedalboard bundle named after
		``title`` (asNew=1). The host mints a fresh dir = symbolify(title)[:16]
		(with a '-NNNN' suffix on collision) and switches the current board to it.

		This is structurally corruption-IMMUNE: the new dir is created FROM the
		title, so dir==ttl==manifest holds by construction -- hence (unlike the
		in-place save) there is intentionally NO dir==sym guard here. Returns
		``{'bundlepath', 'title'}`` (the host's new bundle) on success, else None.
		Form-encoded POST (data=), same as the in-place save."""
		try:
			r = ModepController._request("post", "pedalboard/save",
										 data={'title': title, 'asNew': 1})
			if r is None or r.status_code != 200:
				if r is not None:
					logging.error("Failed to save-as pedalboard. %s", r.text)
				return None
			j = r.json()
			if not j.get('ok'):
				return None
			return {'bundlepath': j.get('bundlepath'), 'title': j.get('title') or title}
		except Exception as e:
			logging.error("Failed to save pedalboard as %r: %s", title, e)
			return None

	@staticmethod
	def effect_list():
		"""Every installed plugin's FULL native info. mod-ui's /effect/list is a
		reduced list (no ports), so enrich the URIs with one /effect/bulk POST.
		Returns a uri->info dict (plugincatalog.normalize accepts it); [] on failure.
		Generous timeout: this is a one-shot startup scan that may build the host's
		plugin cache on first call."""
		try:
			r = ModepController._request("get", "effect/list", timeout=15)
			if r is None or r.status_code != 200:
				return []
			plugins = r.json() or []
			uris = [p["uri"] for p in plugins if isinstance(p, dict) and p.get("uri")]
			if not uris:
				return []
			rb = ModepController._request("post", "effect/bulk", json=uris, timeout=30)
			if rb is not None and rb.status_code == 200:
				return rb.json()
		except Exception as e:
			logging.error(f"An error occurred: {e}")
		return []

	@staticmethod
	def effect_get_information(uri=""):
		try:
			r = ModepController._request("get", "effect/get?uri=" + quote(uri, safe=''))
			if r is not None and r.status_code == 200:
				return r.json()
		except Exception as e:
			logging.error(f"An error occurred: {e}")
		return {}

	@staticmethod
	def bypass_effect(instance, value):
		try:
			r = ModepController._request(
				"post",
				f"effect/parameter/syn_set/graph/{quote(instance, safe='')}/:bypass",
				json={"value": bool(value)})
			if r is None:
				return "MODEP host did not respond"
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

			r = requests.post(url, json={"value": value}, timeout=2.0)
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
			r = requests.get(url, timeout=2.0)
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
			r = requests.post(url, json=payload, timeout=2.0)
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

			r = requests.get(url, timeout=2.0)
			if r.status_code == 200:
				return r.json()[uri]
			else:
				print("Failed to retrieve patch.", r.text)
		except Exception as e:
			print(f"An error occurred: {e}")

	@staticmethod
	def dump_graph():
		"""Return the LIVE in-memory graph (plugins + connections) from the mod
		host as a pedalboard/info-compatible dict, or ``None`` on host failure.
		Lets ``model.initialize_modep_pedalboard`` build from the running JACK
		graph instead of the stale on-disk .ttl (custom fork endpoint; see
		host.syn_dump_graph / webserver GraphDumpSYN)."""
		try:
			r = ModepController._request("get", "syn_dump_graph")
			if r is not None and r.status_code == 200:
				return r.json()
		except Exception as e:
			logging.error(f"Error dumping live graph: {e}")
		return None

	# ── Graph mutation (M4b) ──────────────────────────────────────────────
	# Thin pass-through wrappers over the existing mod-ui graph endpoints (the
	# same ones the web UI's desktop.js drives). Port/instance arguments are in
	# the graph namespace ('/graph/<inst>/<symbol>', bare instance name for
	# add/remove); the harder mapping (port-symbol↔jack-name, instance minting,
	# self-echo guard) lives one layer up in the editor (M5), not here. Return
	# ``None`` on success or an error string, like the other write calls.
	@staticmethod
	def add_effect(instance, uri, x=0.0, y=0.0):
		"""Add plugin ``uri`` as new instance ``instance`` (bare name) at (x, y).
		Mirrors web UI /effect/add (returns the new plugin's data on success)."""
		try:
			endpoint = (f"effect/add/graph/{quote(instance, safe='')}"
						f"?uri={quote(uri, safe='')}&x={x}&y={y}")
			# Generous timeout: some plugins (FFT/spectral) take seconds to
			# instantiate on the host. The editor calls this off the GUI thread,
			# so waiting here never freezes the UI.
			r = ModepController._request("get", endpoint, timeout=60)
			if r is None:
				return "MODEP host did not respond"
			if r.status_code == 200 and r.json():
				return None
			return "host rejected the add"
		except Exception as e:
			return f"An error occurred: {e}"

	@staticmethod
	def remove_effect(instance):
		"""Remove instance ``instance`` (bare name) and its connections."""
		try:
			r = ModepController._request("get", f"effect/remove/graph/{quote(instance, safe='')}")
			if r is None:
				return "MODEP host did not respond"
			if r.status_code == 200 and r.json():
				return None
			return r.text or "effect remove failed"
		except Exception as e:
			return f"An error occurred: {e}"

	@staticmethod
	def connect(port_from, port_to):
		"""Connect two ports given in graph-namespace form ('/graph/<inst>/<sym>',
		'/graph/capture_1'). Mirrors web UI /effect/connect/<from>,<to>."""
		try:
			r = ModepController._request("get", f"effect/connect/{port_from},{port_to}")
			if r is None:
				return "MODEP host did not respond"
			if r.status_code == 200 and r.json():
				return None
			return r.text or "connect failed"
		except Exception as e:
			return f"An error occurred: {e}"

	@staticmethod
	def disconnect(port_from, port_to):
		"""Disconnect two ports given in graph-namespace form. Mirrors web UI
		/effect/disconnect/<from>,<to>."""
		try:
			r = ModepController._request("get", f"effect/disconnect/{port_from},{port_to}")
			if r is None:
				return "MODEP host did not respond"
			if r.status_code == 200 and r.json():
				return None
			return r.text or "disconnect failed"
		except Exception as e:
			return f"An error occurred: {e}"

	@staticmethod
	def set_bpm(value):
		try:
			# Construct the URL with the instance and symbol as part of the path
			url = f"{ModepController.SERVER_URI}general/"
			# Format the value similarly to the server-side logic
			formatted_value = "%.1f" % value

			# Send the POST request with the formatted value as payload
			r = requests.post(url, json={"cmd": "transport-bpm", "value": formatted_value}, timeout=2.0)

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
			r = requests.post(url, json={"cmd": "transport-bpb", "value": formatted_value}, timeout=2.0)

			if r.status_code == 200:
				return None
			else:
				return r.text
		except Exception as e:
			return f"An error occurred: {e}"


# ── Backend seam ─────────────────────────────────────────────────────────────
# The model classes and the pedalboard builder (now in `model.py`) reach the
# MODEP host through `get_backend()` instead of naming `ModepController`
# directly. That lets an off-device entry point (e.g. qt_app.py)
# `set_backend(fake)` to serve fixtures with no Pi hardware. The default is
# `ModepController` itself, so the on-device (Kivy/Pi) path is byte-for-byte
# unchanged — same staticmethods, no extra indirection. Same inject-at-the-seam
# pattern as scheduler.py.
_backend = None


def set_backend(backend):
	"""Install the active backend. Call once at startup, before building the
	Presenter. Pass ``None`` to fall back to the real ``ModepController``."""
	global _backend
	_backend = backend


def get_backend():
	"""Return the active backend; defaults to ``ModepController`` (real host)."""
	return _backend if _backend is not None else ModepController


if __name__ == '__main__':
	r = ModepController.snapshot_save()
	print(r)
