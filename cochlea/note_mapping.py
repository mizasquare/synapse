"""Frequency <-> musical note conversion, plus guitar/bass string tables.

Pure math, no DSP. The tuner engine turns a detected frequency into a
``NoteReading`` (note name, octave, cents deviation, the ideal frequency it is
being compared against, and -- in instrument modes -- the nearest open string).
"""
from dataclasses import dataclass

import numpy as np

# Sharps spelling; index == pitch class (0 == C).
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

A4_MIDI = 69            # MIDI note number of A4
DEFAULT_A4_HZ = 440.0   # concert-pitch reference; adjustable for alt tunings


@dataclass(frozen=True)
class NoteReading:
    note: str          # e.g. "E2"
    pitch_class: int   # 0..11 (0 == C)
    octave: int
    cents: float       # deviation from ideal, -50..+50 (negative == flat)
    freq_hz: float     # the frequency that was mapped
    ideal_hz: float    # the in-tune frequency of `note`
    string: str = ""   # nearest open string in instrument modes ("" otherwise)


def freq_to_note(freq_hz, a4_hz=DEFAULT_A4_HZ):
    """Map a frequency to its nearest equal-tempered note.

    Returns a NoteReading with `string` left blank -- string snapping is an
    instrument-mode concern layered on top (see nearest_string)."""
    if freq_hz <= 0.0:
        raise ValueError("freq_hz must be positive")
    midi = 12.0 * np.log2(freq_hz / a4_hz) + A4_MIDI
    midi_round = int(round(midi))
    cents = (midi - midi_round) * 100.0
    pitch_class = midi_round % 12
    octave = midi_round // 12 - 1
    ideal = a4_hz * 2.0 ** ((midi_round - A4_MIDI) / 12.0)
    return NoteReading(
        note="%s%d" % (NOTE_NAMES[pitch_class], octave),
        pitch_class=pitch_class,
        octave=octave,
        cents=cents,
        freq_hz=freq_hz,
        ideal_hz=ideal,
    )


# -- instrument string tables (standard tunings) ---------------------------
# name -> list of (open-string label, nominal frequency at A4=440).
STRING_SETS = {
    "guitar":       [("E2", 82.41), ("A2", 110.00), ("D3", 146.83),
                     ("G3", 196.00), ("B3", 246.94), ("E4", 329.63)],
    "guitar-dropd": [("D2", 73.42), ("A2", 110.00), ("D3", 146.83),
                     ("G3", 196.00), ("B3", 246.94), ("E4", 329.63)],
    "bass":         [("E1", 41.20), ("A1", 55.00), ("D2", 73.42), ("G2", 98.00)],
    "bass5":        [("B0", 30.87), ("E1", 41.20), ("A1", 55.00),
                     ("D2", 73.42), ("G2", 98.00)],
}


def nearest_string(freq_hz, string_set="guitar"):
    """Nearest open string (label, ideal_hz, cents_off) for an instrument mode.

    Compared in cents (log domain) so the choice is perceptually correct rather
    than biased toward high strings by raw-Hz distance."""
    strings = STRING_SETS[string_set]
    best_label, best_hz, best_cents = "", 0.0, 1e9
    for label, hz in strings:
        cents = 1200.0 * np.log2(freq_hz / hz)
        if abs(cents) < abs(best_cents):
            best_label, best_hz, best_cents = label, hz, cents
    return best_label, best_hz, best_cents
