"""
Universal Clipboard Sync engine between Windows and iPhone.
Monitors the Windows clipboard and synchronizes with connected iPhone in real time.
"""
import time
import threading
from datetime import datetime
from typing import List, Dict, Callable, Optional
import win32clipboard
import win32con

class ClipboardSync:
    def __init__(self, on_change: Optional[Callable[[str, str], None]] = None):
        self.on_change = on_change  # callback(text, source)
        self.last_text = ""
        self.history: List[Dict] = []
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._ignore_next = False

    def start(self):
        self.is_running = True
        self.last_text = self.get_windows_clipboard()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.is_running = False

    def get_windows_clipboard(self) -> str:
        text = ""
        try:
            win32clipboard.OpenClipboard()
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
        except Exception:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
        return text or ""

    def set_windows_clipboard(self, text: str, source: str = "iPhone"):
        """Update Windows clipboard with content received from iPhone."""
        if not text or text == self.last_text:
            return
        try:
            self._ignore_next = True
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
            win32clipboard.CloseClipboard()

            self.last_text = text
            self._add_to_history(text, source)

            if self.on_change:
                self.on_change(text, source)
        except Exception as e:
            print(f"[Clipboard] Error setting clipboard: {e}")
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

    def _add_to_history(self, text: str, source: str):
        item = {
            "text": text,
            "source": source,
            "time": datetime.now().strftime("%H:%M:%S")
        }
        self.history.insert(0, item)
        if len(self.history) > 25:
            self.history.pop()

    def _monitor_loop(self):
        """Continuously check for Windows clipboard changes."""
        while self.is_running:
            try:
                current_text = self.get_windows_clipboard()
                if current_text and current_text != self.last_text:
                    if self._ignore_next:
                        self._ignore_next = False
                    else:
                        self.last_text = current_text
                        self._add_to_history(current_text, "PC")
                        if self.on_change:
                            self.on_change(current_text, "PC")
            except Exception:
                pass
            time.sleep(0.5)
