"""
Bluetooth LE HID Input Controller for AirContinuity.
Manages a BleHid.Cli subprocess to turn the Windows PC into a native
Bluetooth keyboard, mouse, and trackpad controller for the iPhone.
Allows typing on the PC keyboard and moving/clicking/scrolling the mouse/trackpad.
"""
import os
import sys
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Callable


class InputController:
    """Manages the BleHid subprocess for keyboard and mouse control."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._is_capturing = False
        self._keyboard_subs = 0
        self._mouse_subs = 0
        self._blehid_path: Optional[str] = None

        # Callbacks
        self.on_status_change: Optional[Callable[[str, bool, bool], None]] = None  # (status_text, is_connected, is_capturing)
        self.on_subscribers_change: Optional[Callable[[int, int], None]] = None     # (keyboard_subs, mouse_subs)

    def find_blehid(self) -> Optional[str]:
        """Locate the BleHid executable on the system."""
        candidates = []

        # If running from a PyInstaller frozen .exe
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            candidates.extend([
                str(exe_dir / "blehid" / "BleHid.Cli.exe"),
                str(exe_dir / "BleHid.Cli.exe"),
            ])
            if hasattr(sys, "_MEIPASS"):
                mei_dir = Path(sys._MEIPASS)
                candidates.extend([
                    str(mei_dir / "blehid" / "BleHid.Cli.exe"),
                    str(mei_dir / "BleHid.Cli.exe"),
                ])

        # Source repository local folder
        local_dir = Path(__file__).resolve().parent.parent / "blehid"
        candidates.extend([
            str(local_dir / "BleHid.Cli.exe"),
            shutil.which("BleHid.Cli"),
            shutil.which("BleHid.Cli.exe"),
        ])

        for path in candidates:
            if path and os.path.isfile(path):
                self._blehid_path = path
                return path

        return None

    def is_available(self) -> bool:
        """Check if BleHid executable is available."""
        return self.find_blehid() is not None

    def start(self) -> bool:
        """Start the BLE HID peripheral subprocess."""
        if self._running:
            return True

        exe_path = self.find_blehid()
        if not exe_path:
            print("[BleHid] BleHid.Cli.exe not found")
            return False

        try:
            exe_dir = os.path.dirname(os.path.abspath(exe_path))

            # Launch with stdin/stdout piped for real-time control
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # Hide console window

            self._process = subprocess.Popen(
                [exe_path],
                cwd=exe_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            self._running = True
            self._monitor_thread = threading.Thread(target=self._monitor_output, daemon=True)
            self._monitor_thread.start()

            print(f"[BleHid] Subprocess started (PID: {self._process.pid})")
            if self.on_status_change:
                self.on_status_change("Bluetooth HID Peripheral Active — Waiting for iPhone", False, False)
            return True

        except Exception as e:
            print(f"[BleHid] Error starting subprocess: {e}")
            return False

    def _monitor_output(self):
        """Read lines from BleHid and track connection and capture status."""
        if not self._process or not self._process.stdout:
            return

        try:
            for line in iter(self._process.stdout.readline, ''):
                if not self._running:
                    break

                line = line.strip()
                if not line:
                    continue

                print(f"[BleHid] {line}")
                lower = line.lower()

                # Parse subscriber events
                if "keyboard input report:" in lower and "subscriber" in lower:
                    try:
                        self._keyboard_subs = int(line.split(":")[1].strip().split()[0])
                    except Exception:
                        self._keyboard_subs = 1
                    self._notify_subscribers()

                elif "mouse input report:" in lower and "subscriber" in lower:
                    try:
                        self._mouse_subs = int(line.split(":")[1].strip().split()[0])
                    except Exception:
                        self._mouse_subs = 1
                    self._notify_subscribers()

                elif "keyboard subs" in lower:
                    try:
                        self._keyboard_subs = int(line.split(":")[1].strip())
                    except Exception:
                        pass
                    self._notify_subscribers()

                elif "mouse subs" in lower:
                    try:
                        self._mouse_subs = int(line.split(":")[1].strip())
                    except Exception:
                        pass
                    self._notify_subscribers()

                # Parse capture state
                if "capturing" in lower or "redirecting local input" in lower or "swallowed locally" in lower:
                    self._is_capturing = True
                    if self.on_status_change:
                        self.on_status_change("🎮 Controlling iPhone (Press Ctrl+Alt+Q to return)", True, True)

                elif "stopped" in lower and self._is_capturing:
                    self._is_capturing = False
                    if self.on_status_change:
                        connected = (self._keyboard_subs > 0 or self._mouse_subs > 0)
                        self.on_status_change(
                            "🟢 iPhone Connected — Ready to Control" if connected else "Waiting for iPhone",
                            connected,
                            False
                        )

        except Exception as e:
            if self._running:
                print(f"[BleHid] Monitor thread error: {e}")

        self._running = False
        self._is_capturing = False
        if self.on_status_change:
            self.on_status_change("Bluetooth HID Controller Stopped", False, False)

    def _notify_subscribers(self):
        connected = (self._keyboard_subs > 0 or self._mouse_subs > 0)
        if self.on_subscribers_change:
            self.on_subscribers_change(self._keyboard_subs, self._mouse_subs)
        if self.on_status_change:
            if self._is_capturing:
                status_text = "🎮 Controlling iPhone (Press Ctrl+Alt+Q to return)"
            elif connected:
                status_text = "🟢 iPhone Connected (Keyboard & Mouse Ready)"
            else:
                status_text = "Waiting for iPhone Bluetooth connection..."
            self.on_status_change(status_text, connected, self._is_capturing)

    def start_capture(self) -> bool:
        """Redirect keyboard, mouse, and trackpad to the iPhone."""
        if not self._process or not self._process.stdin:
            return False

        try:
            self._process.stdin.write("capture\n")
            self._process.stdin.flush()
            self._is_capturing = True
            if self.on_status_change:
                self.on_status_change("🎮 Controlling iPhone (Press Ctrl+Alt+Q to return)", True, True)
            print("[BleHid] Sent capture command")
            return True
        except Exception as e:
            print(f"[BleHid] Error sending capture: {e}")
            return False

    def stop_capture(self) -> bool:
        """Release keyboard and mouse back to the PC."""
        try:
            # BleHid capture runs a low-level Win32 hook loop. If the UI button is clicked
            # to release capture, restarting the subprocess cleanly drops the hook and restores
            # normal mouse/keyboard to the PC, while the iPhone auto-reconnects in seconds.
            if self._is_capturing:
                self.stop()
                self.start()
            elif self._process and self._process.stdin:
                self._process.stdin.write("\n")
                self._process.stdin.flush()

            self._is_capturing = False
            connected = (self._keyboard_subs > 0 or self._mouse_subs > 0)
            if self.on_status_change:
                self.on_status_change(
                    "🟢 iPhone Connected (Keyboard & Mouse Ready)" if connected else "Waiting for iPhone",
                    connected,
                    False
                )
            return True
        except Exception as e:
            print(f"[BleHid] Error stopping capture: {e}")
            return False

    def send_type(self, text: str):
        """Type text directly to the iPhone."""
        if self._process and self._process.stdin:
            try:
                # Sanitize text
                clean = text.replace("\n", " ").replace("\r", "")
                self._process.stdin.write(f"type {clean}\n")
                self._process.stdin.flush()
            except Exception as e:
                print(f"[BleHid] Error sending type: {e}")

    def send_scroll(self, amount: int):
        """Scroll wheel or trackpad on iPhone (positive=up, negative=down)."""
        if self._process and self._process.stdin:
            try:
                self._process.stdin.write(f"scroll {amount}\n")
                self._process.stdin.flush()
            except Exception as e:
                print(f"[BleHid] Error sending scroll: {e}")

    def stop(self):
        """Stop the BleHid subprocess."""
        self._running = False
        self._is_capturing = False

        if self._process:
            try:
                if self._process.stdin:
                    try:
                        self._process.stdin.write("quit\n")
                        self._process.stdin.flush()
                    except Exception:
                        pass
                self._process.terminate()
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=2)
            except Exception as e:
                print(f"[BleHid] Error stopping process: {e}")
            finally:
                self._process = None

        print("[BleHid] Controller stopped")

    @property
    def is_running(self) -> bool:
        return self._running and self._process is not None and self._process.poll() is None

    @property
    def is_connected(self) -> bool:
        return self._keyboard_subs > 0 or self._mouse_subs > 0

    @property
    def is_capturing(self) -> bool:
        return self._is_capturing
