"""Mains-hum removal in the frequency domain.

50/60 Hz hum and its harmonics are the tuner's worst enemy on low notes: hum is
a *genuine* periodic, harmonic signal, so BOTH pitch detectors can lock onto it
and agree on the wrong answer (see docs -- the cross-check does not save us here;
hum must be removed *before* detection).

We work in the frequency domain because we already need FFTs for pitch
detection: one rfft of the frame, attenuate the hum lines with a smooth
Gaussian notch, one irfft back to a clean time-domain frame that both detectors
share. No IIR, no per-sample Python loop, no scipy.

The notch is Gaussian (not brick-wall) to avoid Gibbs ringing; sigma is a couple
of Hz so a line at 240 Hz is killed while B3 (247 Hz) passes essentially
untouched.
"""
import numpy as np

# Default notch shape / reach. sigma is wider than the hum line itself so that a
# line landing between FFT bins (bin spacing is several Hz at tuner frame sizes)
# and its spectral leakage are still caught. At 3 Hz a 60 Hz notch is essentially
# gone by 82 Hz (low E), so guitar fundamentals are untouched in 60 Hz mode.
DEFAULT_SIGMA_HZ = 3.0    # Gaussian half-width of each notch
DEFAULT_N_HARMONICS = 6   # notch f0, 2f0, ... up to this many


def estimate_mains(mag, freqs):
    """Guess the mains frequency (50.0 or 60.0) from a magnitude spectrum.

    Sums energy in narrow windows around 50/100/150 vs 60/120/180 and returns
    whichever family is stronger. Returns None if neither shows real energy
    (silence / no hum) so the caller can skip notching."""
    def family_energy(f0):
        total = 0.0
        for h in (1, 2, 3):
            fc = f0 * h
            idx = int(np.argmin(np.abs(freqs - fc)))
            total += float(mag[max(0, idx - 1):idx + 2].sum())
        return total

    e50 = family_energy(50.0)
    e60 = family_energy(60.0)
    if max(e50, e60) <= 0.0:
        return None
    return 50.0 if e50 > e60 else 60.0


def notch_gain(freqs, mains, n_harmonics=DEFAULT_N_HARMONICS, sigma_hz=DEFAULT_SIGMA_HZ):
    """Real-valued per-bin gain (1.0 everywhere except dips to ~0 at hum lines)."""
    g = np.ones_like(freqs, dtype=np.float64)
    nyq = freqs[-1]
    for h in range(1, n_harmonics + 1):
        fc = mains * h
        if fc > nyq:
            break
        g *= 1.0 - np.exp(-0.5 * ((freqs - fc) / sigma_hz) ** 2)
    return g
