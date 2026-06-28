"""App-side JACK level meter for the OVERVIEW IN/OUT nodes.

The Qt app keeps no JACK client of its own (all audio control is HTTP to the MODEP
host), so this owns a dedicated ``jack.Client("SynapseMeter")`` purely to *read*
signal level -- the precedent was the old Kivy tuner (since removed), which
likewise spun up its own client to pull capture buffers.

Taps are JACK fan-out connections, so they are non-destructive to the live graph:

  * IN  -- taps ``system:capture_1/2`` (stable; the guitar input).
  * OUT -- ``system:playback_1/2`` are SINKS (can't be read directly), so we mirror
           whatever feeds them onto our taps. That feeder changes on every board /
           snapshot switch, so a JACK graph-order callback flags a re-tap, performed
           lazily on the GUI thread (never from inside a JACK callback).

The realtime ``process`` callback only writes plain Python floats (GIL-protected --
JACK-Client runs it on a Python thread). The GUI thread reads them via ``snapshot``;
``QtView`` maps the linear amplitudes to the dB scale the meters already use.

Per channel we keep two numbers: the peak *since the last read* (the live bar, so a
30 Hz GUI read never misses a transient between reads) and a 5-second moving-window
peak (the dB readout). The window is a ring of ten 0.5 s buckets -- each block does
``bucket = max(bucket, peak)`` and the read is ``max(buckets)`` (O(10), cheap); the
process callback rotates buckets by frame count, so it needs no wall clock.
"""
import logging

try:
    import jack
    import numpy as np
except Exception:                       # jack/numpy absent (off-device dev box)
    jack = None
    np = None

log = logging.getLogger(__name__)

WINDOW_SEC = 5.0
N_BUCKETS = 10
BUCKET_SEC = WINDOW_SEC / N_BUCKETS      # 0.5 s per bucket

CAPTURE = ("system:capture_1", "system:capture_2")
PLAYBACK = ("system:playback_1", "system:playback_2")


def _peak(port):
    a = port.get_array()
    if a.size == 0:
        return 0.0
    return float(np.max(np.abs(a)))


class LevelMeter:
    def __init__(self, name="SynapseMeter"):
        self.ok = False
        self.client = None
        # live (since-last-read) peak per side = max of L/R
        self._in_peak = 0.0
        self._out_peak = 0.0
        # 5 s moving-window peak, as a ring of per-bucket maxima
        self._in_buckets = [0.0] * N_BUCKETS
        self._out_buckets = [0.0] * N_BUCKETS
        self._cur = 0
        self._frames_in_bucket = 0
        self._bucket_frames = 1
        self._retap = True               # resolve output taps lazily on the GUI thread

        if jack is None:
            log.info("LevelMeter: jack/numpy unavailable -> meter disabled")
            return
        try:
            self.client = jack.Client(name)
            self._in_l = self.client.inports.register("in_l")
            self._in_r = self.client.inports.register("in_r")
            self._out_l = self.client.inports.register("out_l")
            self._out_r = self.client.inports.register("out_r")
            self._bucket_frames = max(1, int(self.client.samplerate * BUCKET_SEC))
            self.client.set_process_callback(self._process)
            self.client.set_graph_order_callback(self._on_graph_change)
            self.client.activate()
            self._connect_inputs()
            self.ok = True
            log.info("LevelMeter: active @ %d Hz", self.client.samplerate)
        except Exception as e:
            log.warning("LevelMeter: init failed (%s) -> meter disabled", e)
            self._safe_close()

    # ----------------------------------------------------------- realtime
    def _process(self, frames):
        il = _peak(self._in_l); ir = _peak(self._in_r)
        ol = _peak(self._out_l); orr = _peak(self._out_r)
        ip = il if il > ir else ir
        op = ol if ol > orr else orr
        if ip > self._in_peak:
            self._in_peak = ip
        if op > self._out_peak:
            self._out_peak = op
        cur = self._cur
        if ip > self._in_buckets[cur]:
            self._in_buckets[cur] = ip
        if op > self._out_buckets[cur]:
            self._out_buckets[cur] = op
        self._frames_in_bucket += frames
        if self._frames_in_bucket >= self._bucket_frames:
            self._frames_in_bucket = 0
            nxt = (cur + 1) % N_BUCKETS
            self._in_buckets[nxt] = 0.0
            self._out_buckets[nxt] = 0.0
            self._cur = nxt

    def _on_graph_change(self):
        # JACK thread: only flag; reconnection happens on the GUI thread (snapshot).
        self._retap = True
        return 0

    # ----------------------------------------------------------- tapping
    def _connect_inputs(self):
        self._try_connect(CAPTURE[0], self._in_l)
        self._try_connect(CAPTURE[1], self._in_r)

    def _retap_outputs(self):
        # Mirror the sources feeding system:playback onto our out_* taps.
        for sink, dst in ((PLAYBACK[0], self._out_l), (PLAYBACK[1], self._out_r)):
            try:
                srcs = self.client.get_all_connections(sink)
            except jack.JackError:
                srcs = []
            for s in srcs:
                self._try_connect(s, dst)

    def _try_connect(self, src, dst):
        try:
            self.client.connect(src, dst)
        except jack.JackError:
            pass                         # already connected, or source absent -- fine

    # ----------------------------------------------------------- GUI thread
    def snapshot(self):
        """Read + reset the live peaks; return linear amplitudes (or None)."""
        if not self.ok:
            return None
        if self._retap:
            self._retap = False
            try:
                self._retap_outputs()
            except Exception as e:
                log.debug("LevelMeter retap failed: %s", e)
        in_amp = self._in_peak; self._in_peak = 0.0
        out_amp = self._out_peak; self._out_peak = 0.0
        return {
            "in_amp": in_amp,
            "in_peak_amp": max(self._in_buckets),
            "out_amp": out_amp,
            "out_peak_amp": max(self._out_buckets),
        }

    def stop(self):
        self._safe_close()

    def _safe_close(self):
        self.ok = False
        if self.client is not None:
            try:
                self.client.deactivate()
            except Exception:
                pass
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
