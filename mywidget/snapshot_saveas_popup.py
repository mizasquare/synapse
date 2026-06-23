from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.clock import Clock
from mywidget.utils import DebouncedTextInput
from configs import SCALE_FACTOR, FONTS

class SaveAsPopup(Popup):
    def __init__(self, presenter, **kwargs):
        super(SaveAsPopup, self).__init__(**kwargs)
        self.presenter = presenter
        self.size_hint = (0.7, 0.3)
        self.pos_hint = {'center_x': 0.5, 'center_y': 0.65}
        self.title = ''

        self.text_input = DebouncedTextInput(
            size_hint=(1, None),
            height=16 * SCALE_FACTOR,
            multiline=False,
            font_size=16 * SCALE_FACTOR,
            font_name=FONTS[2],
        )

        content = BoxLayout(orientation='vertical')
        content.add_widget(Label(
            text='Save snapshot as...',
            size_hint_y=None,
            height=22 * SCALE_FACTOR,
            font_name=FONTS[0],
            font_size=8 * SCALE_FACTOR))
        content.add_widget(self.text_input)

        button_layout = BoxLayout(size_hint_y=None, height=10 * SCALE_FACTOR)
        ok_button = Button(text='OK', font_name=FONTS[0], font_size=8 * SCALE_FACTOR)
        cancel_button = Button(text='Cancel', font_name=FONTS[0], font_size=8 * SCALE_FACTOR)
        button_layout.add_widget(ok_button)
        button_layout.add_widget(cancel_button)
        content.add_widget(button_layout)

        self.content = content
        ok_button.bind(on_release=lambda instance: self.on_saveas_popup_ok(self.text_input.text))
        cancel_button.bind(on_release=self.on_saveas_popup_cancel)

        # Schedule the focus event to show the virtual keyboard
        Clock.schedule_once(self.set_textinput_focus, 0.1)

    def set_textinput_focus(self, dt):
        self.text_input.focus = True

    def on_saveas_popup_ok(self, name):
        self.presenter._save_snapshot_as(name)
        self.dismiss()

    def on_saveas_popup_cancel(self, instance):
        self.dismiss()