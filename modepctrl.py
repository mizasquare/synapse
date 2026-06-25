import configs
import requests
from urllib.parse import quote
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
