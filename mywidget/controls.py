from kivy.core.image import Image as CoreImage
from kivy.uix.slider import Slider

SCALE_FACTOR = 8

class MySlider(Slider):
    def __init__(self, **kwargs):
        super(MySlider, self).__init__(**kwargs)
        self.orientation = 'horizontal'
        self.background_horizontal = './resources/SliderTrackS.png'
        self.cursor_image = './resources/SliderHandle.png'
        self.background_width = 8 * SCALE_FACTOR
        self.border_horizontal = (0, 0, 0, 0)
        self.bind(size=self._update_texture_filters)
        self.bind(pos=self._update_texture_filters)
        self.size_hint = (None, None)
        self.width = 53 * SCALE_FACTOR
        self.height = 8 * SCALE_FACTOR
        self.padding = 6 * SCALE_FACTOR
        self.cursor_size = (11 * SCALE_FACTOR, 8 * SCALE_FACTOR)

    def _update_texture_filters(self, *args):
        if self.background_horizontal:
            self._set_texture_filter(self.background_horizontal)
        if self.cursor_image:
            self._set_texture_filter(self.cursor_image)

    def _set_texture_filter(self, image_path):
        try:
            # Access the image texture
            texture = self._coreimage(image_path).texture
            texture.mag_filter = 'nearest'
            texture.min_filter = 'nearest'
        except Exception as e:
            print(f"Error setting texture filter: {e}")

    def _coreimage(self, path):
        return CoreImage(path)
