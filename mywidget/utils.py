import time

from kivy.properties import NumericProperty
from kivy.uix.textinput import TextInput


class DebouncedTextInput(TextInput):
    # Set a short debounce timeout in seconds (adjust as needed)
    debounce_timeout = 0.15

    def __init__(self, **kwargs):
        super(DebouncedTextInput, self).__init__(**kwargs)
        self._last_insert_time = 0

    def insert_text(self, substring, from_undo=False):
        current_time = time.time()
        # If the time since the last insertion is too short, ignore this event
        if current_time - self._last_insert_time < self.debounce_timeout:
            return
        self._last_insert_time = current_time
        super(DebouncedTextInput, self).insert_text(substring, from_undo)


class DebounceBehavior(object):
    debounce_timeout = NumericProperty(2.0)

    def can_activate(self):
        current_time = time.time()
        if not hasattr(self, '_last_activation_time'):
            self._last_activation_time = 0
        if current_time - self._last_activation_time >= self.debounce_timeout:
            self._last_activation_time = current_time
            return True
        return False
