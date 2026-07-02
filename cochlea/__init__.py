"""cochlea -- the tuner's ear.

Dual-algorithm (NSDF + HPS) monophonic pitch detection with mains-hum removal
and octave cross-checking, plus the audio plumbing to feed it. Named for the
inner-ear organ whose basilar membrane is nature's own spectrum analyser.

T1 ships the DSP core (pitch_detection, hum_filter, ring_buffer, audio_source,
note_mapping). The threaded TunerEngine and app wiring land in later milestones.
"""
from .pitch_detection import PitchDetector, PitchEstimate, PitchCandidate, detect_pitch
from .note_mapping import NoteReading, freq_to_note, nearest_string, STRING_SETS
from .ring_buffer import RingBuffer
from .audio_source import (
    AudioSource, JackSource, ToneSource, ToneSweepSource, build_source,
)
from . import hum_filter

__all__ = [
    "PitchDetector", "PitchEstimate", "PitchCandidate", "detect_pitch",
    "NoteReading", "freq_to_note", "nearest_string", "STRING_SETS",
    "RingBuffer",
    "AudioSource", "JackSource", "ToneSource", "ToneSweepSource", "build_source",
    "hum_filter",
]
