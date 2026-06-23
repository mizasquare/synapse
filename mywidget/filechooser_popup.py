from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup

class FileChooserPopup(Popup):
    def __init__(self, initial_path, on_open_callback, **kwargs):
        super(FileChooserPopup, self).__init__(**kwargs)
        self.on_open_callback = on_open_callback
        self.size_hint = (0.7, 0.9)
        self.title = "Select Patch File"
        content = BoxLayout(orientation='vertical')
        self.filechooser = FileChooserListView(
            path=initial_path,
            rootpath=initial_path,
            filters=[]
        )
        content.add_widget(self.filechooser)

        buttons = BoxLayout(size_hint_y=None, height=40)
        open_btn = Button(text="Open")
        cancel_btn = Button(text="Cancel")
        buttons.add_widget(open_btn)
        buttons.add_widget(cancel_btn)
        content.add_widget(buttons)

        self.content = content
        open_btn.bind(on_release=self.file_chosen)
        cancel_btn.bind(on_release=self.dismiss)

    def file_chosen(self, *args):
        if self.filechooser.selection:
            # Pass the selected file path directly to the callback
            self.on_open_callback(self.filechooser.selection[0])
        self.dismiss()
