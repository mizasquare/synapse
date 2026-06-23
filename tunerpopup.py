from collections import deque
import numpy as np
import jack
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.clock import Clock
from yin import find_pitch


def get_nearest_note_and_cents(freq):
    """
    Find the nearest musical note and cents deviation.
    """
    if freq <= 0:
        return "-", 0

    A4 = 440.0
    midi_number = 69 + 12 * np.log2(freq / A4)
    nearest_midi = int(round(midi_number))

    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    note_name = note_names[nearest_midi % 12]
    octave = (nearest_midi // 12) - 1  # Adjust octave
    note = f"{note_name}{octave}"

    true_freq = A4 * (2 ** ((nearest_midi - 69) / 12))
    cents_off = 1200 * np.log2(freq / true_freq)
    return note, cents_off


class TunerPopup(Popup):
    """
    A popup window that captures JACK audio input and runs a tuner.
    """

    def __init__(self, title="Guitar Tuner", update_interval=1 / 30.0, **kwargs):
        super().__init__(title=title, **kwargs)
        self.jack_client = None
        self.audio_buffer = deque(maxlen=4096)
        self.input_port = None

        # Short history of frequencies for smoothing:
        self.freq_buffer = deque(maxlen=8)

        layout = BoxLayout(orientation='vertical')
        self.pitch_label = Label(text="Detecting...", font_size=80, bold=True)
        layout.add_widget(self.pitch_label)

        self.deviation_label = Label(text="", font_size=40, bold=True)
        layout.add_widget(self.deviation_label)

        self.content = layout

        self._init_jack()
        Clock.schedule_interval(self._update_tuner, update_interval)

    def _init_jack(self):
        self.jack_client = jack.Client("Tuner")
        self.input_port = self.jack_client.inports.register("input_1")

        @self.jack_client.set_process_callback
        def process(frames):
            self.audio_buffer.extend(self.input_port.get_array())

        self.jack_client.activate()
        try:
            self.jack_client.connect("system:capture_1", self.input_port.name)
        except jack.JackError as e:
            print(f"JACK Connection Error: {e}")

    def _update_tuner(self, dt):
        # We need enough samples to attempt pitch detection
        if len(self.audio_buffer) < 2048:
            return

        # Copy a slice of audio samples
        buffer_copy = np.array(self.audio_buffer, dtype=np.float32)[-2048:]
        detected_freq = find_pitch(buffer_copy, self.jack_client.samplerate)
        if detected_freq:
            # Add the new pitch to the buffer
            self.freq_buffer.append(detected_freq)

            # Compute an average frequency over the buffer
            avg_freq = np.mean(self.freq_buffer)

            # Convert that average freq to the nearest note and deviation
            note, cents_off = get_nearest_note_and_cents(avg_freq)

            # Update labels
            self.pitch_label.text = f"{note} ({avg_freq:.2f} Hz)"
            self.deviation_label.text = f"{cents_off:+.2f} cents"

    def on_dismiss(self):
        Clock.unschedule(self._update_tuner)
        if self.jack_client:
            self.jack_client.deactivate()
            self.jack_client.close()
            self.jack_client = None
