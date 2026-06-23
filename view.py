from kivy.clock import Clock
from kivy.graphics import Rectangle, Color
from kivy.properties import StringProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.relativelayout import RelativeLayout

from kivy.uix.scrollview import ScrollView

from configs import SCALE_FACTOR, FONTS
from mywidget.buttons import CustomButton, ABCDbutton, PluginButton
from mywidget.labels import BGLabel
from mywidget.utils import DebouncedTextInput
from presenter import Presenter
from utils import optimize_for_newline
from view_widgets import PatchFileWidget, ParameterSliderWidget, ParameterToggleWidget, BypassToggleWidget
from mywidget.snapshot_saveas_popup import SaveAsPopup


class BezelArea(RelativeLayout):
    def __init__(self, presenter, **kwargs):
        super(BezelArea, self).__init__(**kwargs)
        self.presenter = presenter  # Store the presenter instance

        # Create the web UI button and bind it to presenter's open_webui method
        self.webui_button = CustomButton(
            normal_image='./resources/2713webui.png',
            pressed_image='./resources/2713webui_pressed.png',
            size_hint=(None, None),
            size=(27 * SCALE_FACTOR, 13 * SCALE_FACTOR),
            pos=(0 * SCALE_FACTOR, 0 * SCALE_FACTOR)
        )
        self.webui_button.bind(on_release=self.on_webui_button_release)
        self.add_widget(self.webui_button)

        self.save_button = CustomButton(
            normal_image='./resources/1313save.png',
            pressed_image='./resources/1313save_pressed.png',
            size_hint=(None, None),
            size=(13 * SCALE_FACTOR, 13 * SCALE_FACTOR),
            pos=(0 * SCALE_FACTOR, 14 * SCALE_FACTOR)
        )
        self.save_button.bind(on_release=self.on_save_button_release)
        self.add_widget(self.save_button)

        self.saveas_button = CustomButton(
            normal_image='./resources/1313saveas.png',
            pressed_image='./resources/1313saveas_pressed.png',
            size_hint=(None, None),
            size=(13 * SCALE_FACTOR, 13 * SCALE_FACTOR),
            pos=(14 * SCALE_FACTOR, 14 * SCALE_FACTOR)
        )
        self.saveas_button.bind(on_release=self.on_saveas_button_release)
        self.add_widget(self.saveas_button)

        self.button0 = CustomButton(
            normal_image='./resources/1313generic.png',
            pressed_image='./resources/1313generic_pressed.png',
            size_hint=(None, None),
            size=(13 * SCALE_FACTOR, 13 * SCALE_FACTOR),
            pos=(32 * SCALE_FACTOR, 14 * SCALE_FACTOR)
        )
        self.button0.bind(on_release=self.prev_pb)
        self.add_widget(self.button0)


        self.button1 = CustomButton(
            normal_image='./resources/1313_tuner_button.png',
            pressed_image='./resources/1313_tuner_button_pressed.png',
            size_hint=(None, None),
            size=(13 * SCALE_FACTOR, 13 * SCALE_FACTOR),
            pos=(46 * SCALE_FACTOR, 14 * SCALE_FACTOR)
        )
        self.button1.bind(on_release=self.on_modechange_button_release)
        self.add_widget(self.button1)

        self.button2 = CustomButton(
            normal_image='./resources/1313generic.png',
            pressed_image='./resources/1313generic_pressed.png',
            size_hint=(None, None),
            size=(13 * SCALE_FACTOR, 13 * SCALE_FACTOR),
            pos=(60 * SCALE_FACTOR, 14 * SCALE_FACTOR)
        )
        self.button2.bind(on_release=self.next_pb)
        self.add_widget(self.button2)

        self.button3 = CustomButton(
            normal_image='./resources/2013generic.png',
            pressed_image='./resources/2013generic_pressed.png',
            size_hint=(None, None),
            size=(20 * SCALE_FACTOR, 13 * SCALE_FACTOR),
            pos=(32 * SCALE_FACTOR, 0 * SCALE_FACTOR)
        )
        self.button3.bind(on_release=self.prev_ss)
        self.add_widget(self.button3)

        self.button4 = CustomButton(
            normal_image='./resources/2013generic.png',
            pressed_image='./resources/2013generic_pressed.png',
            size_hint=(None, None),
            size=(20 * SCALE_FACTOR, 13 * SCALE_FACTOR),
            pos=(53 * SCALE_FACTOR, 0 * SCALE_FACTOR)
        )
        self.button4.bind(on_release=self.next_ss)
        self.add_widget(self.button4)


        self.abcd_button = ABCDbutton(
            size_hint=(None, None),
            size=(29 * SCALE_FACTOR, 14 * SCALE_FACTOR),
            pos=(78 * SCALE_FACTOR, 0 * SCALE_FACTOR)
        )
        self.add_widget(self.abcd_button)

        # Bind to the on_abcdstate_change event of the ABCDbutton
        self.abcd_button.bind(on_abcdstate_change=self.on_abcdstate_change)


        self.modedisplay = BGLabel(
            bg_image='./resources/mode_label_pbnav.png',
            text="",
            color=(0.05, 0.3, 0, 1),
            pos=(78 * SCALE_FACTOR, 20 * SCALE_FACTOR),
            size_hint=(None, None),
            size=(54 * SCALE_FACTOR, 7 * SCALE_FACTOR))

        self.add_widget(self.modedisplay)


        self.bpm_display = BGLabel(
            bg_image='./resources/2309BPMdisp.png',
            text="000.0",
            font_name=FONTS[2],
            font_size= 16 * SCALE_FACTOR,
            color=(0.05, 0.3, 0, 1),
            pos=(109 * SCALE_FACTOR, 2 * SCALE_FACTOR),
            size_hint=(None, None),
            size=(23 * SCALE_FACTOR, 9 * SCALE_FACTOR),
            text_size=(23 * SCALE_FACTOR, 11 * SCALE_FACTOR))

        self.add_widget(self.bpm_display)


    def open_saveas_popup(self):
        # Check if popup already exists and is open (optional safeguard)
        if hasattr(self, 'saveas_popup') and self.saveas_popup and self.saveas_popup._is_open:
            return

        self.saveas_popup = SaveAsPopup(presenter=self.presenter)
        self.saveas_popup.open()

    def set_textinput_focus(self, dt):
        self.saveas_popup.text_input.focus = True

    def on_saveas_popup_ok(self, name):
        # Call the presenter method with the name
        self.presenter.save_snapshot_as(name)
        # Dismiss the popup
        self.saveas_popup.dismiss()

    def on_saveas_popup_cancel(self, instance):
        # Dismiss the popup
        self.saveas_popup.dismiss()

    def on_save_button_release(self, instance):
        self.presenter.save_snapshot()

    def on_saveas_button_release(self, instance):
        self.open_saveas_popup()

    def on_webui_button_release(self, instance):
        self.webui_button.disabled = True  # Disable the button
        self.presenter.open_webui()


    def set_abcd_availability(self, available):
        self.abcd_button.activated = available

    def on_abcdstate_change(self, instance, previous_state, current_state):
        # Notify the presenter of the state change
        self.presenter.abcd_button_state(previous_state, current_state)

    def on_modechange_button_release(self, instance):
        self.presenter.modechange()
        print("끼요올")

    def update_bpm_display(self, bpm):
        self.bpm_display.text = f" {bpm:.1f}".rjust(5, ' ')

    def prev_pb(self, instance):
        self.presenter.prev_pedalboard()

    def next_pb(self, instance):
        self.presenter.next_pedalboard()

    def prev_ss(self, instance):
        self.presenter.prev_snapshot()

    def next_ss(self, instance):
        self.presenter.next_snapshot()

    def set_mode_display(self, mode):
        if mode == 0:
            self.modedisplay.set_bg_image('./resources/mode_label_pbnav.png')
        elif mode == 1:
            self.modedisplay.set_bg_image('./resources/mode_label_effassign.png')
        elif mode == 2:
            self.modedisplay.set_bg_image('./resources/mode_label_pbassign.png')
        self.modedisplay.update_bg()

    def set_abcd_state(self, state):
        self.abcd_button.toggle_state(state)

class FooterArea(RelativeLayout):
    def __init__(self, presenter, **kwargs):
        super(FooterArea, self).__init__(**kwargs)
        self.presenter = presenter  # Store the presenter instance

        # Create the web UI button and bind it to presenter's open_webui method
        self.fs0_label = BGLabel(
            bg_image='./resources/4409fsdisp.png',
            text="Prev PB",
            font_name=FONTS[0],
            font_size=8 * SCALE_FACTOR,
            color=(0.05, 0.3, 0, 1),
            pos=(3 * SCALE_FACTOR, 2 * SCALE_FACTOR),
            size_hint=(None, None),
            size=(44 * SCALE_FACTOR, 9 * SCALE_FACTOR),
            text_size=(40 * SCALE_FACTOR, 11 * SCALE_FACTOR))
        self.add_widget(self.fs0_label)

        self.fs1_label = BGLabel(
            bg_image='./resources/4409fsdisp.png',
            text="Next PB",
            font_name=FONTS[0],
            font_size=8 * SCALE_FACTOR,
            color=(0.05, 0.3, 0, 1),
            pos=(53 * SCALE_FACTOR, 2 * SCALE_FACTOR),
            size_hint=(None, None),
            size=(44 * SCALE_FACTOR, 9 * SCALE_FACTOR),
            text_size=(40 * SCALE_FACTOR, 11 * SCALE_FACTOR))
        self.add_widget(self.fs1_label)

        self.fs2_label = BGLabel(
            bg_image='./resources/4409fsdisp.png',
            text="Prev SS",
            font_name=FONTS[0],
            font_size=8 * SCALE_FACTOR,
            color=(0.05, 0.3, 0, 1),
            pos=(104 * SCALE_FACTOR, 2 * SCALE_FACTOR),
            size_hint=(None, None),
            size=(44 * SCALE_FACTOR, 9 * SCALE_FACTOR),
            text_size=(40 * SCALE_FACTOR, 11 * SCALE_FACTOR))
        self.add_widget(self.fs2_label)

        self.fs3_label = BGLabel(
            bg_image='./resources/4409fsdisp.png',
            text="Next SS",
            font_name=FONTS[0],
            font_size=8 * SCALE_FACTOR,
            color=(0.05, 0.3, 0, 1),
            pos=(154 * SCALE_FACTOR, 2 * SCALE_FACTOR),
            size_hint=(None, None),
            size=(44 * SCALE_FACTOR, 9 * SCALE_FACTOR),
            text_size=(40 * SCALE_FACTOR, 11 * SCALE_FACTOR))
        self.add_widget(self.fs3_label)

    def fs_label_update(self, idx, text):
        text = text[:7]
        if idx == 0:
            self.fs0_label.text = text
        elif idx == 1:
            self.fs1_label.text = text
        elif idx == 2:
            self.fs2_label.text = text
        elif idx == 3:
            self.fs3_label.text = text

class PortCtrlArea(ScrollView):
    def __init__(self, **kwargs):
        super(PortCtrlArea, self).__init__(**kwargs)
        with self.canvas.before:
            Color(1, 1, 1, 1)  # Set color to fully opaque to ensure the image displays properly
        self.size_hint = (None, None)
        self.size = (53 * SCALE_FACTOR, 92 * SCALE_FACTOR)
        self.pos = (140 * SCALE_FACTOR, 21 * SCALE_FACTOR)
        self.grid_layout = GridLayout(cols=1, size_hint_y=None)
        self.grid_layout.bind(minimum_height=self.grid_layout.setter('height'))
        self.add_widget(self.grid_layout)

    def populate_port_area(self, effectData=None, **kwargs):
        """Populate effectData based on presenter data."""
        self.grid_layout.clear_widgets()  # Clear any existing widgets

        # Reset the scroll position to the top
        self.scroll_y = 1.0
        bypassportdata={'port_name': "Bypass",
                        'port_symbol': ":bypass",
                        'effect_instance': effectData['effect_instance'],
                        "port_value": effectData['effect_bypassed'],
                        }
        bypassport = BypassToggleWidget(port_data=bypassportdata)
        bypassport.bind(on_port_value_change=self.on_port_value_change)
        self.grid_layout.add_widget(bypassport)

        for effectPatches in effectData['patches'] if effectData else []:
            patch_widget = PatchFileWidget(patch_data=effectPatches)
            # Bind to the 'on_patch_change' event
            patch_widget.bind(on_patch_change=self.on_patch_change)
            self.grid_layout.add_widget(patch_widget)


        for effectport in effectData['effect_ports'] if effectData else []:
            if 'toggle' in effectport.get('port_properties'):
                param_widget = ParameterToggleWidget(port_data=effectport)

            else:
                param_widget = ParameterSliderWidget(port_data=effectport)

            # Bind to the 'on_port_value_change' event
            param_widget.bind(on_port_value_change=self.on_port_value_change)
            self.grid_layout.add_widget(param_widget)

    def on_patch_change(self, instance, effect_instance, patch_uri, patch_file):
        # Forward the event to the presenter
        self.parent.presenter.patch_changed(effect_instance, patch_uri, patch_file)

    def on_port_value_change(self, instance, effect_instance, port_symbol, value):
        # Send this information back to the presenter
        self.parent.presenter.parameter_changed(effect_instance, port_symbol, value)

class PedalboardDisplay(RelativeLayout):
    current_pbname = StringProperty('Default')
    current_snapshot = ListProperty(['0', {'0': 'Default'}])
    current_effects = ListProperty([])
    selected_effect_instance = StringProperty('')  # Keep track of selected plugin instance

    def __init__(self, presenter, **kwargs):
        super(PedalboardDisplay, self).__init__(**kwargs)
        self.presenter = presenter  # Store the presenter instance

        self.pbname_label = Label(
            font_name=FONTS[5],
            text=self.current_pbname[:16] + "~" if len(self.current_pbname) > 18 else self.current_pbname,
            font_size=16 * SCALE_FACTOR,
            color=(0.95, 0.93, 0.95, 0.9),
            size_hint=(None, None),
            size=(134 * SCALE_FACTOR, 11 * SCALE_FACTOR),
            pos=(6 * SCALE_FACTOR, 55 * SCALE_FACTOR),
            text_size=(134 * SCALE_FACTOR, 11 * SCALE_FACTOR)
        )
        self.add_widget(self.pbname_label)


        self.snapshot_label = Label(
            font_name=FONTS[2],
            text=f"{self.current_snapshot[0]}-{self.current_snapshot[1].get(str(self.current_snapshot[0]), '')}",
            font_size=16 * SCALE_FACTOR,
            color=(0.90, 0.88, 0.90, 0.7),
            size_hint=(None, None),
            size=(134 * SCALE_FACTOR, 9 * SCALE_FACTOR),
            pos=(6 * SCALE_FACTOR, 50 * SCALE_FACTOR),
            text_size=(134 * SCALE_FACTOR, 9 * SCALE_FACTOR)
        )
        self.add_widget(self.snapshot_label)

        self.effect_list_scroll = ScrollView(
            size_hint=(None, None),
            size=(134 * SCALE_FACTOR, 50 * SCALE_FACTOR),
            pos=(0 * SCALE_FACTOR, 0 * SCALE_FACTOR)
        )

        self.effect_list = GridLayout(
            cols=1,
            size_hint_y=None
        )
        self.effect_list.bind(minimum_height=self.effect_list.setter('height'))
        self.effect_list_scroll.add_widget(self.effect_list)
        self.add_widget(self.effect_list_scroll)

        # Bind property changes to methods that handle updates
        self.bind(selected_effect_instance=self.on_selected_effect_instance)
        self.bind(current_pbname=self.on_current_pedalboard)
        self.bind(current_effects=self.on_current_plugins)
        self.bind(current_snapshot=self.on_current_snapshot)


    def on_current_pedalboard(self, instance, value):
        """Automatically update the title label when current_pbname changes."""
        self.pbname_label.text = value[:16] + "~" if len(value) > 18 else value

    def on_current_snapshot(self, instance, value):
        try:
            idx, names = value[0], value[1]
            name = names.get(str(idx)) if isinstance(names, dict) else None
            self.snapshot_label.text = f"{idx}-{name}" if name is not None else f"{idx}-"
        except Exception:
            pass

        self.populate_plugin_list()


    def on_current_plugins(self, instance, value):
        """Automatically update the plugin list when current_effects changes."""
        self.populate_plugin_list()

    def populate_plugin_list(self):
        """Populate the plugin list with data from the presenter."""
        self.effect_list.clear_widgets()  # Clear any existing widgets
        for plugin in self.current_effects:
            self.add_plugin_item(plugin[0], plugin[1], plugin[2], plugin[3])

    def add_plugin_item(self, instance_name, plugin_name, category, status):
        item_layout = RelativeLayout(size_hint_y=None, height=10 * SCALE_FACTOR)
        optimized_plugin_name = plugin_name[:15] + ".." if len(plugin_name) > 17 else plugin_name

        is_selected = instance_name == self.selected_effect_instance

        plugin_button = PluginButton(
            font_name=FONTS[1],
            text=optimized_plugin_name,
            plugin_data={
                'instance_name': instance_name,
                'plugin_name': plugin_name,
                'category': category,
                'status': status
            },
            font_size=16 * SCALE_FACTOR,
            color=(0.95, 0.93, 0.95, 1),
            background_normal='',
            background_color=(1, 0.2, 0.6, 0.5) if is_selected else (0, 0, 0, 0),
            size_hint=(None, None),
            size=(97 * SCALE_FACTOR, 10 * SCALE_FACTOR),
            pos=(9 * SCALE_FACTOR, 0 * SCALE_FACTOR),
            text_size=(95 * SCALE_FACTOR, None),
        )
        plugin_button.bind(on_release=self.on_plugin_button_release)
        item_layout.add_widget(plugin_button)

        category_label = Label(
            font_name=FONTS[0],
            text=category[:6],
            font_size=8 * SCALE_FACTOR,
            color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(25 * SCALE_FACTOR, 10 * SCALE_FACTOR),
            pos=(108 * SCALE_FACTOR, 0 * SCALE_FACTOR),
            # text_size=(28 * SCALE_FACTOR, None)
        )
        item_layout.add_widget(category_label)

        status_label = Label(
            font_name=FONTS[0],
            text="●" if status[0] == "active" else "○",
            color=(0.2, 0.3, 0.55, 1) if status[1] == "assigned" else (0.85, 0.22, 0.2, 1),
            font_size=8 * SCALE_FACTOR,
            size_hint=(None, None),
            size=(8 * SCALE_FACTOR, 10 * SCALE_FACTOR),
            pos=(0 * SCALE_FACTOR, -1 * SCALE_FACTOR),
        )
        plugin_button.bind(on_release=self.on_plugin_button_release)
        item_layout.add_widget(status_label)

        self.effect_list.add_widget(item_layout)

    def on_plugin_button_release(self, button):
        self.selected_effect_instance = button.plugin_data['instance_name']

    def on_selected_effect_instance(self, source, instance):
        if instance:
            self.populate_plugin_list()
            self.presenter.view_update_effect(clear_ports=False)
            self.presenter.view_render_parameters(self.selected_effect_instance)

class SynapseGUI(RelativeLayout):
    def __init__(self, **kwargs):
        super(SynapseGUI, self).__init__(**kwargs)

        # Create the presenter instance
        self.presenter = Presenter(self)

        # Initialize the canvas and background
        with self.canvas.before:
            self.rect = Rectangle(source='./resources/UI-design_3.png', pos=self.pos,
                                  size=(self.size[0], self.size[1]))
        self.bind(pos=self.update_rect, size=self.update_rect)
        self.rect.texture.mag_filter = 'nearest'
        self.rect.texture.min_filter = 'nearest'

        # Initialize view components (display_frame, port_control_area, etc.)
        self.display_frame = PedalboardDisplay(presenter=self.presenter,
                                               size=(134 * SCALE_FACTOR, 70 * SCALE_FACTOR),
                                               size_hint=(None, None),
                                               pos=(5 * SCALE_FACTOR, 47 * SCALE_FACTOR))
        self.add_widget(self.display_frame)

        self.port_control_area = PortCtrlArea(
            size=(53 * SCALE_FACTOR, 94 * SCALE_FACTOR),
            size_hint=(None, None),
            pos=(142 * SCALE_FACTOR, 22 * SCALE_FACTOR))
        self.add_widget(self.port_control_area)

        self.bezel = BezelArea(
            presenter=self.presenter,
            size=(135 * SCALE_FACTOR, 35 * SCALE_FACTOR),
            size_hint=(None, None),
            pos=(4 * SCALE_FACTOR, 18 * SCALE_FACTOR)
        )
        self.add_widget(self.bezel)

        self.footer = FooterArea(
            presenter=self.presenter,
            size=(200 * SCALE_FACTOR, 12 * SCALE_FACTOR),
            size_hint=(None, None),
            pos=(0 * SCALE_FACTOR, 0 * SCALE_FACTOR)
        )
        self.add_widget(self.footer)

        # Now that all view components are initialized, instruct the presenter to load data
        self.initialize_presenter()

    def initialize_presenter(self, *args):
        """Instruct the presenter to load data after the view is fully initialized."""
        self.presenter.initiate_view()

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = (self.size[0], self.size[1])

    def refresh_plugin_display(self, pb_title, plugins, snapshot, **kwargs):
        """Interface method to update the plugin list in PedalboardDisplay."""
        if pb_title:
            self.display_frame.current_pbname = pb_title
        if plugins:
            self.display_frame.current_effects = plugins
        if snapshot:
            self.display_frame.current_snapshot = snapshot


    def populate_port_area(self, effectData):
        """Interface method to update the parameter area."""
        self.port_control_area.populate_port_area(effectData)

    def enable_webui_button(self):
        self.bezel.webui_button.disabled = False

    def update_parameter_display(self, instance_name, param_symbol, value):
        # Locate the correct widget and update it instead of redrawing everything
        # isinstance 를 먼저 검사해야 port_symbol 없는 위젯(PatchFileWidget 등)에서 안전.
        for widget in self.port_control_area.grid_layout.children:
            if isinstance(widget, ParameterSliderWidget) and widget.port_symbol == param_symbol:
                widget.set_value_external(value)  # thumb + 라벨 갱신(host 되쏨 없음)
                return
            if isinstance(widget, ParameterToggleWidget) and widget.port_symbol == param_symbol:
                # 토글: port_value 설정 → update_toggle_button 으로 버튼 상태만 바뀜.
                # on_port_value_change 디스패치는 버튼 '직접 누름'에서만 발생하므로 host 되쏨 없음.
                widget.port_value = 1 if value >= 0.5 else 0
                return
            if isinstance(widget, BypassToggleWidget) and widget.port_symbol == param_symbol:
                widget.port_value = value >= 0.5  # 포트영역 Bypass 스위치 갱신(디스패치 없음)
                return

    def update_patch_display(self, instance_name, patch_uri, patch_file):
        for widget in self.port_control_area.grid_layout.children:
            if isinstance(widget, PatchFileWidget) and widget.patch_uri == patch_uri:
                widget.set_patch_external(patch_file)  # 디스패치 억제 → host 되쏨 없음
                return

    def set_abcd_availability(self, available):
        self.bezel.set_abcd_availability(available)

    def update_bpm_display(self, bpm):
        self.bezel.update_bpm_display(bpm)

    def update_mode_display(self, mode):
        self.bezel.set_mode_display(mode)
        self.bezel.set_abcd_state(-2)

