"""
Windows System Tray integration for AirContinuity.
Runs in the background, enables auto-start, and allows quick access.
"""
import threading
from pathlib import Path
from PIL import Image
import pystray
from pystray import MenuItem as item

from app import config

class SystemTrayApp:
    def __init__(self, main_window, on_exit_callback):
        self.main_window = main_window
        self.on_exit_callback = on_exit_callback
        self.icon = None
        self._thread = None

    def start(self):
        icon_path = Path(__file__).resolve().parent / "assets" / "icon.png"
        image = Image.open(icon_path) if icon_path.exists() else Image.new("RGBA", (64, 64), (10, 132, 255, 255))

        menu = pystray.Menu(
            item("Show AirContinuity", self._on_show, default=True),
            item("Open AirDrop Folder", self._on_open_folder),
            pystray.Menu.SEPARATOR,
            item("Start with Windows", self._on_toggle_startup, checked=lambda item: config.is_run_at_startup()),
            pystray.Menu.SEPARATOR,
            item("Quit", self._on_quit)
        )

        self.icon = pystray.Icon("AirContinuity", image, "AirContinuity - Apple Bridge", menu)
        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()

    def _on_show(self, icon, item):
        self.main_window.after(0, self.main_window.show_window)

    def _on_open_folder(self, icon, item):
        self.main_window.after(0, self.main_window.open_downloads_folder)

    def _on_toggle_startup(self, icon, item):
        current = config.is_run_at_startup()
        config.set_run_at_startup(not current)

    def _on_quit(self, icon, item):
        self.icon.stop()
        self.main_window.after(0, self.on_exit_callback)

    def stop(self):
        if self.icon:
            self.icon.stop()
