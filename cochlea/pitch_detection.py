"""Dual-algorithm monophonic pitch detection with octave cross-checking.

Two independent estimators run on the same (hum-cleaned) frame:

* NSDF -- McLeod's Normalized Square Difference Function, a time-domain method
  purpose-built for instrument tuners (Tartini). Bounded [-1, 1]; the peak value
  doubles as a clarity/confidence measure. Precise on the fundamental period,
  but prone to *octave-down* errors (picks a multiple of the true period).
* HPS -- Harmonic Product Spectrum, a frequency-domain method. Coarser in
  frequency (bin-limited) but sees the harmonic stack directly. Prone to the
  *opposite* error: locking onto a strong harmonic (octave-up).

Because their octave-error directions are opposite, reconcile() cross-checks the
two: agreement -> high confidence + NSDF's precise frequency; octave-scale
disagreement -> pick the candidate best supported by the harmonic spectrum;
wild disagreement -> publish nothing (let the engine hold / fade).

Pure numpy. Hum removal (hum_filter) shares the FFTs computed here.
"""
from dataclasses import dataclass

import numpy as np

from . import hum_filter


@dataclass(frozen=True)
class PitchCandidate:
    freq: float
    confidence: float   # 0..1, detector-local


@dataclass(frozen=True)
class PitchEstimate:
    freq: float
    confidence: float   # 0..1, after cross-check
    method: str         # 'agree' | 'octave-fix' | 'nsdf-only' | 'hps-only'


def _next_pow2(n):
    p = 1
    while p < n:
        p <<= 1
    return p


def _parabolic_x(y, i):
    """Sub-sample refined position of an extremum near integer index i."""
    if i <= 0 or i >= len(y) - 1:
        return float(i)
    a, b, c = float(y[i - 1]), float(y[i]), float(y[i + 1])
    denom = a - 2.0 * b + c
    if abs(denom) < 1e-12:
        return float(i)
    off = 0.5 * (a - c) / denom
    return i + off if abs(off) < 1.0 else float(i)


class PitchDetector:
    """Configured detector; call detect(frame) repeatedly on frames of audio.

    mains: 50.0 / 60.0 to force a hum family, or None to auto-detect per frame.
    """

    def __init__(self, sample_rate, freq_min=65.0, freq_max=1300.0,
                 mains=None, nsdf_k=0.9, hps_harmonics=3, min_rms=1e-5,
                 notch_harmonics=hum_filter.DEFAULT_N_HARMONICS,
                 notch_sigma_hz=hum_filter.DEFAULT_SIGMA_HZ):
        self.sr = float(sample_rate)
        self.fmin = float(freq_min)
        self.fmax = float(freq_max)
        self.mains = mains
        self.nsdf_k = float(nsdf_k)
        self.min_rms = float(min_rms)   # digital-silence floor; the engine adds a musical gate
        self.hps_harmonics = int(hps_harmonics)
        self.notch_harmonics = int(notch_harmonics)
        self.notch_sigma_hz = float(notch_sigma_hz)

    # -- public ---------------------------------------------------------------
    def detect(self, frame):
        """Return (PitchEstimate | None, mains_hz | None) for one frame."""
        x = np.asarray(frame, dtype=np.float64)
        x = x - x.mean()                       # DC removal
        n = x.shape[0]
        if n < 64:
            return None, None
        if float(np.sqrt(np.mean(x * x))) < self.min_rms:
            return None, None                  # digital silence: nothing to detect

        # One rfft serves hum detection + removal; irfft yields the clean frame
        # both detectors then share.
        freqs = np.fft.rfftfreq(n, 1.0 / self.sr)
        X = np.fft.rfft(x)
        mag = np.abs(X)
        mains = self.mains if self.mains is not None else hum_filter.estimate_mains(mag, freqs)
        if mains:
            X = X * hum_filter.notch_gain(
                freqs, mains, self.notch_harmonics, self.notch_sigma_hz)
            x_clean = np.fft.irfft(X, n)
        else:
            x_clean = x

        nsdf_c = self._detect_nsdf(x_clean)
        hps_c, hmag, hfreqs = self._detect_hps(x_clean)
        est = self._reconcile(nsdf_c, hps_c, hmag, hfreqs)
        return est, mains

    # -- NSDF (time domain) ---------------------------------------------------
    def _detect_nsdf(self, x):
        nsdf = self._nsdf_curve(x)
        return self._pick_nsdf(nsdf)

    def _nsdf_curve(self, x):
        n = x.shape[0]
        nf = _next_pow2(2 * n)
        f = np.fft.rfft(x, nf)
        acf = np.fft.irfft(f * np.conj(f), nf)[:n]     # linear autocorrelation
        # m'(tau) = sum_{j<n-tau} x[j]^2 + sum_{j>=tau} x[j]^2  (McLeod SNAC)
        e = x * x
        E = np.empty(n + 1)
        E[0] = 0.0
        np.cumsum(e, out=E[1:])
        tau = np.arange(n)
        m = E[n - tau] + (E[n] - E[tau])
        nsdf = np.zeros(n)
        nz = m > 1e-12
        nsdf[nz] = 2.0 * acf[nz] / m[nz]
        return nsdf

    def _pick_nsdf(self, nsdf):
        n = len(nsdf)
        tau_min = max(2, int(self.sr / self.fmax))
        tau_max = min(n - 2, int(self.sr / self.fmin) + 1)
        if tau_min >= tau_max:
            return None

        # Skip the zero-lag main lobe: search only past the first zero crossing,
        # otherwise the descending flank near tau=0 masquerades as a high peak.
        first_neg = None
        for t in range(1, tau_max + 1):
            if nsdf[t] <= 0.0:
                first_neg = t
                break
        if first_neg is None:
            return None
        lo = max(tau_min, first_neg)

        # Key maxima: the single highest sample within each positive segment.
        key = []
        in_seg = False
        seg_tau, seg_val = -1, -2.0
        for t in range(lo, tau_max + 1):
            v = nsdf[t]
            if v > 0.0:
                if not in_seg:
                    in_seg, seg_val, seg_tau = True, -2.0, -1
                if v > seg_val:
                    seg_val, seg_tau = v, t
            elif in_seg:
                key.append((seg_tau, seg_val))
                in_seg = False
        if in_seg and seg_tau >= 0:
            key.append((seg_tau, seg_val))
        if not key:
            return None

        # First key max clearing k * (best key max) -- prefers the lowest
        # plausible period, which is the fundamental (rejects octave-down).
        gmax = max(v for _, v in key)
        thr = self.nsdf_k * gmax
        tau_est, clarity = None, 0.0
        for t, v in key:
            if v >= thr:
                tau_est, clarity = t, v
                break
        if tau_est is None:
            return None

        ref = _parabolic_x(nsdf, tau_est)
        if ref <= 0.0:
            return None
        freq = self.sr / ref
        if not (self.fmin * 0.9 <= freq <= self.fmax * 1.1):
            return None
        return PitchCandidate(freq, float(np.clip(clarity, 0.0, 1.0)))

    # -- HPS (frequency domain) ----------------------------------------------
    def _detect_hps(self, x):
        n = x.shape[0]
        w = np.hanning(n)
        nf = _next_pow2(2 * n)                          # zero-pad for finer bins
        mag = np.abs(np.fft.rfft(x * w, nf))
        freqs = np.fft.rfftfreq(nf, 1.0 / self.sr)

        hps = mag.copy()
        for h in range(2, self.hps_harmonics + 1):
            dec = mag[::h]
            hps[:len(dec)] *= dec

        lo = int(np.searchsorted(freqs, self.fmin))
        hi = int(np.searchsorted(freqs, self.fmax))
        if hi - lo < 3:
            return None, mag, freqs
        seg = hps[lo:hi]
        i = lo + int(np.argmax(seg))
        peak = float(hps[i])
        if peak <= 1e-30:                               # no spectral energy
            return None, mag, freqs
        ref = _parabolic_x(hps, i)
        freq = ref * self.sr / nf                       # freqs[k] = k*sr/nf
        mean = float(seg.mean()) + 1e-30
        conf = float(np.clip(1.0 - mean / peak, 0.0, 1.0))
        if freq <= 0.0:
            return None, mag, freqs
        return PitchCandidate(freq, conf), mag, freqs

    # -- cross-check ----------------------------------------------------------
    def _reconcile(self, nsdf_c, hps_c, mag, freqs):
        if nsdf_c is None and hps_c is None:
            return None
        if hps_c is None:
            return PitchEstimate(nsdf_c.freq, 0.85 * nsdf_c.confidence, "nsdf-only")
        if nsdf_c is None:
            return PitchEstimate(hps_c.freq, 0.60 * hps_c.confidence, "hps-only")

        fn, fh = nsdf_c.freq, hps_c.freq
        ratio = fn / fh
        # Agreement to within ~half a semitone (2^(0.5/12) = 1.0293).
        if 0.971 < ratio < 1.030:
            conf = min(1.0, 0.60 + 0.40 * nsdf_c.confidence)
            return PitchEstimate(fn, conf, "agree")

        # Disagreement (typically octave-scale): score the octave family of both
        # candidates by harmonic support in the spectrum and take the winner.
        def support(f):
            if f <= 0.0:
                return 0.0
            s = 0.0
            for h in (1, 2, 3):
                fc = f * h
                if fc >= freqs[-1]:
                    break
                idx = int(np.argmin(np.abs(freqs - fc)))
                s += float(mag[max(0, idx - 1):idx + 2].max())
            return s

        cands = set()
        for f in (fn, fh):
            for mult in (0.5, 1.0, 2.0):
                g = f * mult
                if self.fmin <= g <= self.fmax:
                    cands.add(round(g, 3))
        best, best_score = None, -1.0
        for g in cands:
            sc = support(g)
            if abs(1200.0 * np.log2(g / fn)) < 60.0:   # nudge toward NSDF (precise)
                sc *= 1.15
            if sc > best_score:
                best, best_score = g, sc
        if best is None:
            return None
        conf = 0.30 + 0.25 * max(nsdf_c.confidence, hps_c.confidence)
        return PitchEstimate(best, min(conf, 0.6), "octave-fix")


def detect_pitch(frame, sample_rate, **kw):
    """One-shot convenience wrapper (builds a detector per call)."""
    return PitchDetector(sample_rate, **kw).detect(frame)
