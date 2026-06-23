from kivy.properties import DictProperty, StringProperty, ListProperty, NumericProperty, BooleanProperty
from kivy.uix.label import Label
from kivy.uix.relativelayout import RelativeLayout

from configs import SCALE_FACTOR, FONTS, PRM_MAX_CHARACTERS
from mywidget.buttons import CustomToggleButton
from mywidget.controls import MySlider
from mywidget.labels import BGLabel
from utils import optimize_for_newline
from mywidget.filechooser_popup import FileChooserPopup


class PatchFileWidget(RelativeLayout):
    patch_data = DictProperty({})
    effect_instance = StringProperty('')
    patch_uri = StringProperty('')
    patch_file_types = ListProperty(['*'])
    patch_file_path = StringProperty('')
    patch_value = StringProperty('')
    patch_name = StringProperty('Default Parameter Name')

    def __init__(self, patch_data=None, **kwargs):
        self.register_event_type('on_patch_change')

        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = 49 * SCALE_FACTOR
        self.patch_data = patch_data or {}

        # Retrieve values from patch_data
        self.patch_label = self.patch_data.get('patch_label', 'Default Parameter Name')
        self.effect_instance = self.patch_data.get('effect_instance', ' ')
        self.patch_uri = self.patch_data.get('patch_uri', ' ')
        self.patch_file_path = self.patch_data.get('patch_file_path', './')
        self.patch_file_types = self.patch_data.get('patch_file_types', '*')
        self.patch_value = self.patch_data.get('patch_value', [' ', ' '])[0]
        # Derive patch_name from patch_value
        self.patch_name = (
            self.patch_value.split('/')[-1].rsplit('.', 1)[0]
            if self.patch_value.strip() else 'Empty Patch'
        )

        self.patch_file_disp = BGLabel(
            bg_image='./resources/Disp5347.png',
            text=optimize_for_newline("  " + self.patch_name, 12),
            font_name=FONTS[0],
            font_size=8 * SCALE_FACTOR,
            opacity=0.75,
            color=(165 / 255, 48 / 255, 48 / 255, 1),
            pos=(1 * SCALE_FACTOR, 0 * SCALE_FACTOR),
            size=(53 * SCALE_FACTOR, 47 * SCALE_FACTOR),
            text_size=(49 * SCALE_FACTOR, 45 * SCALE_FACTOR),
            valign='top',
        )

        self.patch_file_disp.bind(on_touch_up=self.on_label_touch_up)
        self.add_widget(self.patch_file_disp)
        self.popup = None

        # Bind changes to patch_value so that on_patch_value is called automatically
        self.bind(patch_value=self.on_patch_value)

    def on_label_touch_up(self, instance, touch):
        if instance.collide_point(*touch.pos):
            self.open_filechooser()
            return True
        return False

    def open_filechooser(self):
        if self.popup:
            print("Popup is already open. Avoiding creation of a new one.")
            return

        self.popup = FileChooserPopup(
            initial_path=self.patch_file_path,
            on_open_callback=self.select_file,
        )
        self.popup.open()
        self.popup.bind(on_dismiss=self.on_popup_dismiss)

    def select_file(self, selected_file):
        if selected_file:
            print("Selected file:", selected_file)
            # Update patch_value. The binding will automatically dispatch the event.
            self.patch_value = selected_file
            self.patch_name = selected_file.split('/')[-1].rsplit('.', 1)[0]
            self.patch_file_disp.text = optimize_for_newline("  " + self.patch_name, 12)
            self.popup.dismiss()

    def on_patch_value(self, instance, value):
        # Dispatch the custom event when patch_value changes.
        self.dispatch('on_patch_change', self.effect_instance, self.patch_uri, value)

    def on_patch_change(self, effect_instance, patch_uri, patch_file):
        # This event can be handled by binding to it externally.
        return

    def on_popup_dismiss(self, instance):
        self.popup = None



class ParameterSliderWidget(RelativeLayout):
    # Define Kivy properties for each attribute
    port_name = StringProperty('Default Parameter Name')
    port_symbol = StringProperty('')
    effect_instance = StringProperty('')
    port_value = NumericProperty(0.5)
    port_unit = StringProperty('')
    port_range = DictProperty({'default': 0, 'minimum': 0, 'maximum': 1})

    def __init__(self, port_data=[], **kwargs):
        super().__init__(**kwargs)
        self.register_event_type('on_port_value_change')  # Register custom event
        self.size_hint_y = None
        self.height = 32 * SCALE_FACTOR
        if port_data:
            # Update the properties directly
            for key, value in port_data.items():
                if hasattr(self, key):
                    setattr(self, key, value)

        # Now you can use the properties directly in your widget
        self.slider = MySlider(
            min=self.port_range['min'],
            max=self.port_range['max'],
            value=self.port_value,
            pos=(0 * SCALE_FACTOR, 2 * SCALE_FACTOR)
        )
        self.slider.bind(value=self.on_slider_value_change)
        self.add_widget(self.slider)

        display_text = self.port_name[:PRM_MAX_CHARACTERS] + "." if len(
            self.port_name) > PRM_MAX_CHARACTERS else self.port_name

        # Use properties in your labels
        self.value_label = BGLabel(
            bg_image='./resources/ParamDigitS.png',

            text=f"{self.port_value:.2f}{self.port_unit}".rjust(10, ' '),
            font_name=FONTS[1],
            font_size=14 * SCALE_FACTOR,
            color=(0.05, 0.3, 0, 1),
            pos=(3 * SCALE_FACTOR, 12 * SCALE_FACTOR),
            size_hint=(None, None),
            size=(47 * SCALE_FACTOR, 8 * SCALE_FACTOR)
        )
        self.add_widget(self.value_label)

        # Bind to property changes to update labels automatically
        self.bind(port_value=self.update_value_label)

        # Add label for parameter name
        self.add_widget(BGLabel(
            bg_image='./resources/ParamLabelS.png',
            text=display_text,
            font_name=FONTS[2],
            font_size=16 * SCALE_FACTOR,
            color=(0.05, 0.1, 0, 1),
            pos=(3 * SCALE_FACTOR, 21 * SCALE_FACTOR),
            size_hint=(None, None),
            size=(47 * SCALE_FACTOR, 8 * SCALE_FACTOR),
            text_size=(None, 8 * SCALE_FACTOR)
        ))

    def update_value_label(self, *args):
        display_value = f"{self.port_value:.2f}{self.port_unit}".rjust(10, ' ')
        self.value_label.text = display_value

    def on_slider_value_change(self, instance, value):
        # Update the property, which will automatically update the label
        self.port_value = value
        # Dispatch event with the necessary information
        self.dispatch('on_port_value_change', self.effect_instance, self.port_symbol, value)

    def on_port_value_change(self, effect_instance, port_symbol, value):
        pass  # Placeholder for event handling


class BaseToggleWidget(RelativeLayout):
    """
    A base widget for boolean-style parameter toggles that displays:
      - A label showing `port_name`
      - A CustomToggleButton that toggles on/off
      - An event `on_port_value_change` to communicate changes
    Concrete subclasses must define how `port_value` is stored/managed (BooleanProperty vs. NumericProperty)
    and can customize images or the toggle logic as needed.
    """
    # Common properties
    port_name = StringProperty('')
    port_symbol = StringProperty('')
    effect_instance = StringProperty('')
    # You can choose to store images in the subclass or in the base; here we set default
    normal_image = StringProperty('./resources/1013footsw_off.png')
    toggled_image = StringProperty('./resources/1013footsw_on.png')

    def __init__(self, port_data=None, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = 25 * SCALE_FACTOR

        # Subclasses can override this property to handle boolean or numeric
        # Or define a property in the subclass with the exact type you need (BooleanProperty, NumericProperty)
        # e.g. self.port_value = 0 or self.port_value = False in the subclass

        # If the user passed in a dictionary like {port_name, port_symbol, effect_instance, port_value}, update self
        if port_data:
            for key, value in port_data.items():
                if hasattr(self, key):
                    setattr(self, key, value)

        # Register a custom event that watchers can bind to
        self.register_event_type('on_port_value_change')

        # Create the toggle button
        #  - We’ll let the subclass define how to interpret port_value -> state
        #  - Or we define an is_active() method that the subclass can override
        self.toggle_button = CustomToggleButton(
            normal_image=self.normal_image,
            toggled_image=self.toggled_image,
            size_hint=(None, None),
            size=(10 * SCALE_FACTOR, 13 * SCALE_FACTOR),
            pos=(22 * SCALE_FACTOR, 2 * SCALE_FACTOR)
        )
        self.toggle_button.bind(on_press=self.on_toggle_button_press)
        self.add_widget(self.toggle_button)

        # Create a label for the parameter name
        self.add_widget(BGLabel(
            bg_image='./resources/ParamLabelS.png',
            text=self.port_name,
            font_name=FONTS[2],
            font_size=16 * SCALE_FACTOR,
            color=(0.05, 0.1, 0, 1),
            pos=(3 * SCALE_FACTOR, 16 * SCALE_FACTOR),
            size_hint=(None, None),
            size=(47 * SCALE_FACTOR, 8 * SCALE_FACTOR),
            text_size=(None, 8 * SCALE_FACTOR)
        ))

        # Let the subclass decide how to bind port_value changes
        self.bind_port_value()

    def bind_port_value(self):
        """
        Subclass should override if it has a specific property, e.g.:
           self.bind(port_value=self.update_toggle_button)
        """
        pass

    def on_toggle_button_press(self, button):
        """
        Called whenever the toggle button is pressed. The base class
        defers to the subclass for deciding how port_value changes.
        """
        pass

    def on_port_value_change(self, effect_instance, port_symbol, port_value):
        """
        Fired whenever port_value changes (subclasses call `dispatch`).
        """
        pass


class ParameterToggleWidget(BaseToggleWidget):
    """
    Parameter toggles are typically 0/1 (numeric), but can be forced to be on or off.
    We'll store port_value as a NumericProperty for potential range in the future.
    """
    port_value = NumericProperty(0)  # 0 or 1 for boolean style

    def __init__(self, port_data=None, **kwargs):
        # We can override images, if we like; or stick to the parent's normal_image/toggled_image
        self.normal_image = './resources/1013footsw_off.png'
        self.toggled_image = './resources/1013footsw_on.png'
        super().__init__(port_data=port_data, **kwargs)

    def bind_port_value(self):
        # We know we have a NumericProperty here, so let's sync the toggle button
        self.bind(port_value=self.update_toggle_button)

        # Initialize the toggle button's 'state' from the current port_value
        self.update_toggle_button(self, self.port_value)

    def update_toggle_button(self, instance, value):
        # For ParameterToggleWidget, let's interpret 0 => 'normal', 1 => 'down'
        self.toggle_button.state = 'down' if value else 'normal'

    def on_toggle_button_press(self, button):
        # If the button is pressed, toggle the numeric property accordingly
        # This is just an example logic: feel free to invert if you want
        # The user code had the logic reversed: if state == 'normal' => set param_value = 1, so adapt as needed
        self.port_value = 1 if button.state == 'down' else 0

        # Dispatch an event letting listeners know the new port_value
        self.dispatch('on_port_value_change', self.effect_instance, self.port_symbol, self.port_value)

    def on_port_value_change(self, effect_instance, port_symbol, port_value):
        """
        Subclass or outside code can bind to this event to do something like:
          modepctrl.set_parameter_value(effect_instance, port_symbol, port_value)
        """
        pass


class BypassToggleWidget(BaseToggleWidget):
    """
    Bypass toggles are true/false (boolean). For some plugins,
    True might mean 'bypassed' or 'enabled', so you can invert logic if needed.
    """
    port_value = BooleanProperty(False)

    def __init__(self, port_data=None, **kwargs):
        # If you'd like to flip images relative to ParameterToggleWidget:
        self.normal_image = './resources/1013footsw_on.png'
        self.toggled_image = './resources/1013footsw_off.png'
        super().__init__(port_data=port_data, **kwargs)

    def bind_port_value(self):
        self.bind(port_value=self.update_toggle_button)
        self.update_toggle_button(self, self.port_value)

    def update_toggle_button(self, instance, value):
        """
        If port_value is True => the button is 'down' (meaning "bypass on"? or "effect off"?).
        Adjust to your specific semantics if needed.
        """
        self.toggle_button.state = 'down' if value else 'normal'

    def on_toggle_button_press(self, button):
        """
        If the user presses the toggle, set port_value accordingly.
        'down' => True, 'normal' => False.
        """
        self.port_value = (button.state == 'down')

        # Fire the event so higher-level logic can catch it
        self.dispatch('on_port_value_change', self.effect_instance, self.port_symbol, self.port_value)

    def on_port_value_change(self, effect_instance, port_symbol, port_value):
        pass
