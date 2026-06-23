from kivy.core.image import Image as CoreImage
from kivy.graphics import Rectangle
from kivy.properties import StringProperty
from kivy.uix.label import Label


from kivy.core.image import Image as CoreImage
from kivy.resources import resource_find
from kivy.uix.label import Label
from kivy.graphics import Rectangle

class BGLabel(Label):
    bg_image = StringProperty('')

    def __init__(self, bg_image, **kwargs):
        # Resolve the resource path so the image is always found
        resolved_bg = resource_find(bg_image) or bg_image
        kwargs.setdefault('markup', True)
        super(BGLabel, self).__init__(**kwargs)
        self.bg_image = resolved_bg

        with self.canvas.before:
            self.bg = Rectangle(pos=self.pos, size=self.size, source=self.bg_image)

        self.bind(pos=self.update_bg, size=self.update_bg)
        self.set_bg_image(self.bg_image)

    def _set_texture_filter(self, image_path):
        try:
            texture = self._coreimage(image_path).texture
            texture.mag_filter = 'nearest'
            texture.min_filter = 'nearest'
        except Exception as e:
            print(f"Error setting texture filter: {e}")

    def _coreimage(self, path):
        return CoreImage(path)

    def update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size

    def set_bg_image(self, image_path):
        resolved_path = resource_find(image_path) or image_path
        self.bg_image = resolved_path
        self.bg.source = self.bg_image
        self._set_texture_filter(self.bg_image)
        self.update_bg()
