import socket
import logging
import os
from threading import Thread
from kivy.config import Config
from kivy.app import App
from kivy.core.window import Window
from kivy.clock import Clock
from configs import SCALE_FACTOR, SOCKET_PATH
import mywidget.controls
from view import SynapseGUI

# Configure Kivy settings
Config.set('graphics', 'window_title', 'GCaMP6s')
Config.set('graphics', 'resizable', False)
Config.set('kivy', 'keyboard_mode', 'dock')
Window.fullscreen = 'auto'
Window.title = "GCaMP6s"
Window.icon = "./resources/icon.png"

# Set scale factor
mywidget.controls.SCALE_FACTOR = SCALE_FACTOR

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GCaMP6sApp(App):
    def build(self):
        Window.icon = "./resources/icon.png"
        return SynapseGUI()

    def start_socket_listener(self):
        self.listener_thread = Thread(target=self.start_listener, daemon=True)
        self.listener_thread.start()

    def start_listener(self):
        socket_path = SOCKET_PATH
        try:
            os.unlink(socket_path)
        except OSError:
            if os.path.exists(socket_path):
                raise

        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(socket_path)
        os.chmod(socket_path, 0o666)
        print("Hardware controller listening...")

        while True:
            try:
                data, _ = self.sock.recvfrom(1024)
                message = data.decode('utf-8')
                print(message)
                Clock.schedule_once(lambda dt: self.notify_presenter(message))
            except Exception as e:
                logger.error(f"Error receiving message: {e}")
                break

    def notify_presenter(self, message):
        pass

    def on_stop(self):
        if hasattr(self, 'sock'):
            self.sock.close()
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)

if __name__ == '__main__':
    app = GCaMP6sApp()
    app.start_socket_listener()
    app.run()