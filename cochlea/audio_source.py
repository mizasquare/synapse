"""Audio sources for the tuner: real JACK capture + synthetic test tones.

The engine talks to an AudioSource via start(on_samples)/stop(); on_samples is
handed float32 blocks. JackSource reads the live guitar (its own JACK client on
system:capture_1, same approach as the old Kivy tuner). The tone sources let the
whole engine be exercised off-device -- no guitar, no JACK -- which is how T1/T2
are verified. ToneSweepSource in particular ping-pongs around a centre pitch so
you can watch the needle track.
"""
import math
import threading
import time

import numpy as np


class AudioSource:
    """Interface. sample_rate is valid only after start()."""
    @property
    def sample_rate(self):
        raise NotImplementedError

    def start(self, on_samples):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError


class JackSource(AudioSource):
    """Live capture from a JACK port (default the first hardware input)."""

    def __init__(self, capture_port="system:capture_1", name="synapse-tuner"):
        self._capture_port = capture_port
        self._name = name
        self._client = None
        self._port = None
        self._on_samples = None
        self._sr = 48000

    @property
    def sample_rate(self):
        if self._client is None:
            raise RuntimeError("sample_rate available only after start()")
        return self._sr

    def start(self, on_samples):
        import jack

        self._on_samples = on_samples
        self._client = jack.Client(self._name, no_start_server=True)
        self._sr = self._client.samplerate
        self._port = self._client.inports.register("in")

        @self._client.set_process_callback
        def _process(frames):
            cb = self._on_samples
            if cb is not None:
                cb(self._port.get_array())

        self._client.activate()
        try:
            self._client.connect(self._capture_port, self._port)
        except Exception:
            # Leave unconnected rather than crash; caller sees no samples.
            pass

    def stop(self):
        if self._client is not None:
            self._on_samples = None      # silence callback before teardown
            try:
                self._client.deactivate()
                self._client.close()
            except Exception:
                pass
            self._client = None


class _ToneBase(AudioSource):
    """Square-wave generator on a daemon thread. Subclasses set _freq_at(t)."""
    BLOCK = 256

    def __init__(self, sample_rate=48000, amplitude=0.5, hum_hz=0.0, hum_amp=0.0,
                 noise=0.0):
        self._sr = int(sample_rate)
        self._amp = float(amplitude)
        self._hum_hz = float(hum_hz)     # inject mains hum for realistic tests
        self._hum_amp = float(hum_amp)
        self._noise = float(noise)
        self._on_samples = None
        self._thread = None
        self._running = False

    @property
    def sample_rate(self):
        return self._sr

    def _freq_at(self, t):
        raise NotImplementedError

    def start(self, on_samples):
        self._on_samples = on_samples
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="tone-source")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self):
        phase = 0.0
        hum_phase = 0.0
        block_dur = self.BLOCK / self._sr
        t = 0.0
        rng = np.random.default_rng(0)
        while self._running:
            t0 = time.monotonic()
            freq = self._freq_at(t)
            period = self._sr / freq
            idx = (phase + np.arange(self.BLOCK)) % period
            buf = self._amp * (1.0 - 4.0 * np.abs(idx / period - 0.5))   # square-ish tri
            phase += self.BLOCK
            if self._hum_amp > 0.0 and self._hum_hz > 0.0:
                ph = hum_phase + 2.0 * np.pi * self._hum_hz * np.arange(self.BLOCK) / self._sr
                buf = buf + self._hum_amp * np.sin(ph)
                hum_phase = ph[-1] + 2.0 * np.pi * self._hum_hz / self._sr
            if self._noise > 0.0:
                buf = buf + self._noise * rng.standard_normal(self.BLOCK)
            cb = self._on_samples
            if cb is not None:
                cb(buf.astype(np.float32))
            t += block_dur
            sleep = block_dur - (time.monotonic() - t0)
            if sleep > 0:
                time.sleep(sleep)


class ToneSource(_ToneBase):
    """Fixed-frequency tone (optionally with injected hum/noise)."""
    def __init__(self, freq_hz, **kw):
        super().__init__(**kw)
        self._freq = float(freq_hz)

    def _freq_at(self, t):
        return self._freq


class ToneSweepSource(_ToneBase):
    """Triangle-sweeps +/- SWEEP_CENTS around a centre pitch (watch the needle)."""
    SWEEP_CENTS = 60.0
    PERIOD_S = 8.0

    def __init__(self, center_hz=440.0, **kw):
        super().__init__(**kw)
        self._center = float(center_hz)

    def _freq_at(self, t):
        phase = (t % self.PERIOD_S) / self.PERIOD_S
        triangle = 1.0 - abs(2.0 * phase - 1.0)          # 0..1..0
        cents = self.SWEEP_CENTS * (2.0 * triangle - 1.0)
        return self._center * math.pow(2.0, cents / 1200.0)


def build_source(spec, capture_port="system:capture_1", name="synapse-tuner"):
    """Parse a source spec: 'jack', 'tone:<hz>', 'sweep[:<hz>]'."""
    if spec == "jack":
        return JackSource(capture_port, name=name)
    if spec.startswith("tone:"):
        return ToneSource(float(spec[5:]))
    if spec.startswith("sweep"):
        _, _, rest = spec.partition(":")
        return ToneSweepSource(center_hz=float(rest) if rest else 440.0)
    raise ValueError("unknown source spec: %r" % spec)
