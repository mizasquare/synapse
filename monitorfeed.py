"""Live monitor feed — passive mod-ui websocket listener (transport "A").

Connects to the mod-ui websocket (the SAME stream the web UI uses) and forwards
``output_set <instance> <symbol> <value>`` frames (LV2 output/monitor control
ports: level meters, tuner, etc.) to a callback. Multi-client safe: this is just
another websocket client of the always-running mod-ui server -- it never opens a
second mod-host connection, so it can't conflict with an external web UI (see
docs/focus-control-rendering.md §9 and memory mod-ui-monitor-path).

Dependency-free: a minimal raw-socket WebSocket client (RFC 6455) in a daemon
thread, mirroring the reverse-listener / footswitch-poll idiom. Values are
marshalled onto the GUI thread via ``scheduler.schedule_once``.

The server paces monitor frames with a request/grant handshake: it sends
``data_ready N``; the client must echo it back to be granted the next batch.
We honour that so meters keep flowing. At silence nothing streams (mod-host emits
output ports only on change), which is correct -- the meter simply sits at 0.
"""
import base64
import logging
import os
import socket
import struct
import threading
import time

log = logging.getLogger(__name__)


class MonitorFeed:
    def __init__(self, on_output, scheduler, host="localhost", port=80, path="/websocket"):
        """on_output(instance, symbol, value) is called on the GUI thread."""
        self._on_output = on_output
        self._scheduler = scheduler
        self._host, self._port, self._path = host, port, path
        self._stop = threading.Event()
        self._sock = None
        self._buf = bytearray()
        self._last = {}                 # (instance,symbol) -> monotonic of last GUI push (throttle)
        self._thread = threading.Thread(target=self._run, daemon=True, name="monitor-feed")
        self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass

    # -- thread loop (reconnect with backoff) ----------------------------------
    def _run(self):
        while not self._stop.is_set():
            try:
                self._session()
            except Exception as e:
                log.warning("monitor feed dropped (%s); retrying", e)
            self._stop.wait(2.0)

    def _session(self):
        self._sock = socket.create_connection((self._host, self._port), timeout=5)
        self._buf = bytearray()
        self._handshake()
        self._sock.settimeout(30)
        while not self._stop.is_set():
            op, payload = self._read_frame()
            if op == 0x8:            # close
                return
            if op == 0x9:            # ping -> pong
                self._send(payload, opcode=0xA)
                continue
            if op != 0x1:            # only text frames carry mod-ui commands
                continue
            self._dispatch(payload.decode("utf-8", "replace"))

    # -- protocol --------------------------------------------------------------
    def _handshake(self):
        key = base64.b64encode(os.urandom(16)).decode()
        self._sock.sendall(
            (f"GET {self._path} HTTP/1.1\r\nHost: {self._host}\r\n"
             "Upgrade: websocket\r\nConnection: Upgrade\r\n"
             f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        while b"\r\n\r\n" not in self._buf:
            self._buf.extend(self._recv())
        head, _, rest = bytes(self._buf).partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise OSError("websocket upgrade failed: %r" % head[:60])
        self._buf = bytearray(rest)

    def _recv(self):
        d = self._sock.recv(4096)
        if not d:
            raise EOFError("websocket closed")
        return d

    def _fill(self, n):
        while len(self._buf) < n:
            self._buf.extend(self._recv())

    def _read_frame(self):
        self._fill(2)
        b1, idx = self._buf[1], 2
        ln = b1 & 0x7f
        if ln == 126:
            self._fill(4); ln = struct.unpack(">H", bytes(self._buf[2:4]))[0]; idx = 4
        elif ln == 127:
            self._fill(10); ln = struct.unpack(">Q", bytes(self._buf[2:10]))[0]; idx = 10
        op = self._buf[0] & 0x0f
        mask = b""
        if self._buf[1] & 0x80:               # server frames are normally unmasked
            self._fill(idx + 4); mask = bytes(self._buf[idx:idx + 4]); idx += 4
        self._fill(idx + ln)
        payload = bytes(self._buf[idx:idx + ln])
        del self._buf[:idx + ln]
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return op, payload

    def _send(self, data, opcode=0x1):
        if isinstance(data, str):
            data = data.encode()
        mask = os.urandom(4)                  # client frames MUST be masked
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        f = bytearray([0x80 | opcode])
        n = len(data)
        if n < 126:
            f.append(0x80 | n)
        elif n < 65536:
            f.append(0x80 | 126); f += struct.pack(">H", n)
        else:
            f.append(0x80 | 127); f += struct.pack(">Q", n)
        f += mask + masked
        self._sock.sendall(f)

    # -- mod-ui command dispatch -----------------------------------------------
    def _dispatch(self, text):
        cmd, _, rest = text.partition(" ")
        if cmd == "output_set":
            parts = rest.split(" ")
            if len(parts) < 3:
                return
            instance = parts[0].split("/graph/", 1)[-1].lstrip("/")
            symbol = parts[1]
            try:
                value = float(parts[2])
            except ValueError:
                return
            # throttle to ~30 Hz per (instance,symbol): drop intermediate frames so a
            # heavy signal can't flood the GUI thread (still always ack below to keep
            # the stream alive; the next window carries a fresh value).
            now = time.monotonic()
            key = (instance, symbol)
            if now - self._last.get(key, 0.0) < 0.033:
                return
            self._last[key] = now
            self._scheduler.schedule_once(
                lambda dt, i=instance, s=symbol, v=value: self._on_output(i, s, v))
        elif cmd == "data_ready":
            self._send(text)                  # ack -> grant the next monitor batch
