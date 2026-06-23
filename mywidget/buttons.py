from kivy.properties import NumericProperty
from kivy.properties import BooleanProperty
from kivy.properties import DictProperty
from kivy.properties import StringProperty

from kivy.uix.behaviors import ButtonBehavior, ToggleButtonBehavior
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.core.image import Image as CoreImage

from mywidget.utils import DebounceBehavior


class ABCDbutton(DebounceBehavior, ButtonBehavior, Image):
    activated = BooleanProperty(False)
    abcdstate = NumericProperty(-2)
    is_touched = BooleanProperty(False)  # To avoid multiple touch down events

    def __init__(self, **kwargs):
        super(ABCDbutton, self).__init__(**kwargs)
        self.register_event_type('on_abcdstate_change')
        self.bg_image = './resources/2914abcd_n.png'
        self.source = self.bg_image
        self.allow_stretch = True
        self.keep_ratio = False
        self.size_hint = (None, None)
        self.set_texture_filter(self.source)

    def set_texture_filter(self, image_source):
        texture = CoreImage(image_source).texture
        texture.mag_filter = 'nearest'
        texture.min_filter = 'nearest'
        self.texture = texture

    def set_bg(self, image_path):
        self.bg_image = image_path
        self.source = self.bg_image
        self.set_texture_filter(self.source)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and not self.is_touched and self.activated:
            # Only proceed if debounce permits the activation
            if not self.can_activate():
                return False
            self.is_touched = True
            _prev_state = self.abcdstate
            x, y = self.pos
            width, height = self.size

            if touch.x < x + width / 2:
                if touch.y < y + height / 2:
                    self.toggle_state(2)
                else:
                    self.toggle_state(0)
            else:
                if touch.y < y + height / 2:
                    self.toggle_state(3)
                else:
                    self.toggle_state(1)
            self.dispatch('on_abcdstate_change', _prev_state, self.abcdstate)
            return True
        return super(ABCDbutton, self).on_touch_down(touch)

    def on_touch_up(self, touch):
        if self.is_touched:
            self.is_touched = False
        return super(ABCDbutton, self).on_touch_up(touch)

    def toggle_state(self, new_state):

        if self.abcdstate == new_state:
            self.abcdstate = -1
        else:
            self.abcdstate = new_state
        self.update_bg_image()

    def update_bg_image(self):
        if self.abcdstate == 0:
            self.set_bg('./resources/2914abcd_a.png')
        elif self.abcdstate == 1:
            self.set_bg('./resources/2914abcd_b.png')
        elif self.abcdstate == 2:
            self.set_bg('./resources/2914abcd_c.png')
        elif self.abcdstate == 3:
            self.set_bg('./resources/2914abcd_d.png')
        else:
            self.set_bg('./resources/2914abcd_n.png')

    def on_abcdstate_change(self, previous_state, current_state):
        print(f"{previous_state}, {current_state}")
        return

class CustomButton(DebounceBehavior, ButtonBehavior, Image):
    normal_image = StringProperty('')
    pressed_image = StringProperty('')

    def __init__(self, normal_image, pressed_image, **kwargs):
        super(CustomButton, self).__init__(**kwargs)
        self.normal_image = normal_image
        self.pressed_image = pressed_image
        self.source = self.normal_image
        self.fit_mode = 'fill'
        self.size_hint = (None, None)
        self.set_texture_filter(self.source)

    def on_press(self):
        # Only change to the pressed image if debounce allows
        if not self.can_activate():
            return
        self.source = self.pressed_image
        self.set_texture_filter(self.source)

    def on_touch_up(self, touch):
        self.on_release()
        return super(CustomButton, self).on_touch_up(touch)

    def on_release(self):
        self.source = self.normal_image
        self.set_texture_filter(self.source)

    def set_texture_filter(self, image_source):
        texture = CoreImage(image_source).texture
        texture.mag_filter = 'nearest'
        texture.min_filter = 'nearest'
        self.texture = texture

class CustomToggleButton(DebounceBehavior, ToggleButtonBehavior, Image):
    normal_image = StringProperty('')
    toggled_image = StringProperty('')
    def __init__(self, normal_image, toggled_image, **kwargs):
        self.normal_image = normal_image
        self.toggled_image = toggled_image
        self.source = self.normal_image
        self.fit_mode = 'fill'
        super(CustomToggleButton, self).__init__(**kwargs)
        self.size_hint = (None, None)
        self.set_texture_filter(self.source)

    def on_state(self, widget, value):
        # Only update if debounce check passes

        if value == 'down':
            self.source = self.toggled_image
        else:
            self.source = self.normal_image
        self.set_texture_filter(self.source)

    def set_texture_filter(self, image_source):
        texture = CoreImage(image_source).texture
        texture.mag_filter = 'nearest'
        texture.min_filter = 'nearest'
        self.texture = texture


class PluginButton(DebounceBehavior, Button):
    plugin_data = DictProperty()

    def __init__(self, **kwargs):
        super(PluginButton, self).__init__(**kwargs)
