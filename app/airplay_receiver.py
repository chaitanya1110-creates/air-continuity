"""
AirPlay Screen Mirroring Receiver for AirContinuity.
Manages a UxPlay subprocess to receive native iOS Screen Mirroring
via the AirPlay protocol. iPhone users simply swipe to Control Center
and tap "Screen Mirroring" — no companion app required.

UxPlay is an open-source AirPlay receiver that handles:
  - mDNS/Bonjour discovery
  - FairPlay authentication
  - H.264 video decoding via GStreamer
  - Audio playback
"""
import os
import sys
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Callable


class AirPlayReceiver:
    """Manages the UxPlay AirPlay receiver subprocess."""

    def __init__(self, server_name: Optional[str] = None, fps: int = 60):
        self.server_name = server_name or f"AirContinuity-{socket.gethostname()}"
        self.fps = fps
        self._process: Optional[subprocess.Popen] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._uxplay_path: Optional[str] = None

        # Callbacks
        self.on_status_change: Optional[Callable[[str, bool], None]] = None  # (message, is_active)
        self.on_client_connected: Optional[Callable[[str], None]] = None  # (client_info)
        self.on_client_disconnected: Optional[Callable[[], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    def find_uxplay(self) -> Optional[str]:
        """Locate the UxPlay executable on the system."""
        candidates = []

        # If running from a PyInstaller frozen .exe
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            candidates.extend([
                str(exe_dir / "uxplay" / "uxplay-windows.exe"),
                str(exe_dir / "uxplay" / "uxplay.exe"),
                str(exe_dir / "uxplay-windows.exe"),
                str(exe_dir / "uxplay.exe"),
            ])
            if hasattr(sys, "_MEIPASS"):
                mei_dir = Path(sys._MEIPASS)
                candidates.extend([
                    str(mei_dir / "uxplay" / "uxplay-windows.exe"),
                    str(mei_dir / "uxplay" / "uxplay.exe"),
                ])

        # Check local bundled app directory in project root
        local_dir = Path(__file__).resolve().parent.parent / "uxplay"
        candidates.extend([
            str(local_dir / "uxplay-windows.exe"),
            str(local_dir / "uxplay.exe"),
            # winget / uxplay-windows typical locations
            shutil.which("uxplay"),
            shutil.which("uxplay.exe"),
            shutil.which("uxplay-windows"),
            shutil.which("uxplay-windows.exe"),
            r"C:\Program Files\uxplay-windows\uxplay.exe",
            r"C:\Program Files\uxplay-windows\uxplay-windows.exe",
            r"C:\Program Files (x86)\uxplay-windows\uxplay.exe",
            r"C:\Program Files (x86)\uxplay-windows\uxplay-windows.exe",
            # MSYS2 build
            r"C:\msys64\ucrt64\bin\uxplay.exe",
            r"C:\msys64\mingw64\bin\uxplay.exe",
        ])

        # Also check user's local AppData
        appdata_local = os.environ.get("LOCALAPPDATA", "")
        if appdata_local:
            candidates.append(str(Path(appdata_local) / "Programs" / "uxplay-windows" / "uxplay.exe"))
            candidates.append(str(Path(appdata_local) / "Programs" / "uxplay-windows" / "uxplay-windows.exe"))

        # Check ProgramFiles for uxplay-windows
        for env_var in ["ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"]:
            pf = os.environ.get(env_var, "")
            if pf:
                candidates.append(str(Path(pf) / "uxplay-windows" / "uxplay.exe"))
                candidates.append(str(Path(pf) / "uxplay-windows" / "uxplay-windows.exe"))
                candidates.append(str(Path(pf) / "UxPlay" / "uxplay.exe"))
                candidates.append(str(Path(pf) / "UxPlay" / "uxplay-windows.exe"))

        for path in candidates:
            if path and os.path.isfile(path):
                self._uxplay_path = path
                return path

        return None

    def is_installed(self) -> bool:
        """Check if UxPlay is available on the system."""
        return self.find_uxplay() is not None

    def install_uxplay(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Download and extract portable UxPlay release (no UAC/admin required).
        Falls back to winget if download fails.
        """
        import zipfile
        import urllib.request

        # 1. Try portable zip download directly into app's uxplay directory
        dest_dir = Path(__file__).resolve().parent.parent / "uxplay"
        dest_dir.mkdir(parents=True, exist_ok=True)
        zip_path = dest_dir / "uxplay-windows.zip"
        portable_url = "https://github.com/leapbtw/uxplay-windows/releases/download/2.0.0.1736/uxplay-windows.zip"

        try:
            if progress_callback:
                progress_callback("Downloading UxPlay portable package...")
            print(f"[AirPlay] Downloading portable UxPlay from {portable_url}...")

            urllib.request.urlretrieve(portable_url, zip_path)

            if progress_callback:
                progress_callback("Extracting UxPlay...")
            print("[AirPlay] Extracting UxPlay zip...")

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(dest_dir)

            if zip_path.exists():
                os.remove(zip_path)

            if self.find_uxplay():
                print(f"[AirPlay] UxPlay successfully installed to {self._uxplay_path}")
                if progress_callback:
                    progress_callback("UxPlay installed successfully!")
                return True
        except Exception as e:
            print(f"[AirPlay] Portable download failed: {e}. Falling back to winget...")
            if zip_path.exists():
                try:
                    os.remove(zip_path)
                except Exception:
                    pass

        # 2. Fallback to winget
        try:
            if progress_callback:
                progress_callback("Attempting winget installation...")
            result = subprocess.run(
                ["winget", "install", "leapbtw.uxplay", "--accept-source-agreements", "--accept-package-agreements"],
                capture_output=True, text=True, timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return self.find_uxplay() is not None
        except Exception as e:
            print(f"[AirPlay] Winget fallback error: {e}")
            return False

    def start(self) -> bool:
        """Start the AirPlay receiver."""
        if self._running:
            print("[AirPlay] Receiver is already running")
            return True

        uxplay_path = self.find_uxplay()
        if not uxplay_path:
            msg = "UxPlay not found. Install it with: winget install leapbtw.uxplay"
            print(f"[AirPlay] {msg}")
            if self.on_error:
                self.on_error(msg)
            return False

        try:
            uxplay_dir = os.path.dirname(os.path.abspath(uxplay_path))

            # Configure arguments.txt so uxplay-windows advertises our exact server name
            args_content = f"-n {self.server_name} -nh -fps {self.fps} -nc\n"
            config_paths = [
                Path(uxplay_dir) / "arguments.txt",
            ]
            appdata = os.environ.get("APPDATA")
            if appdata:
                config_paths.append(Path(appdata) / "leapbtw" / "uxplay-windows" / "arguments.txt")
                config_paths.append(Path(appdata) / "uxplay-windows" / "arguments.txt")

            for p in config_paths:
                try:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(args_content, encoding="utf-8")
                except Exception as e:
                    print(f"[AirPlay] Could not write {p}: {e}")

            cmd = [
                uxplay_path,
                "-n", self.server_name,
                "-nh",                    # Don't append @hostname
                "-fps", str(self.fps),    # Max framerate
                "-nc",                    # Don't close window on disconnect
            ]

            print(f"[AirPlay] Starting UxPlay: {' '.join(cmd)}")

            # Ensure working directory is set to UxPlay directory so DLLs are found
            env = os.environ.copy()
            env["PATH"] = f"{uxplay_dir};{env.get('PATH', '')}"

            # Launch without CREATE_NO_WINDOW / SW_HIDE so the Direct3D video
            # window ("AirPlay Video Stream") displays directly on the screen.
            self._process = subprocess.Popen(
                cmd,
                cwd=uxplay_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            self._running = True

            # Start monitoring thread
            self._monitor_thread = threading.Thread(target=self._monitor_output, daemon=True)
            self._monitor_thread.start()

            if self.on_status_change:
                self.on_status_change("AirPlay Receiver Active — Waiting for iPhone", True)

            print(f"[AirPlay] UxPlay receiver started (PID: {self._process.pid})")
            return True

        except Exception as e:
            error_msg = f"Failed to start AirPlay receiver: {e}"
            print(f"[AirPlay] {error_msg}")
            if self.on_error:
                self.on_error(error_msg)
            return False

    def _monitor_output(self):
        """Monitor UxPlay subprocess output for status changes."""
        if not self._process or not self._process.stdout:
            return

        try:
            for line in iter(self._process.stdout.readline, ''):
                if not self._running:
                    break

                line = line.strip()
                if not line:
                    continue

                print(f"[UxPlay] {line}")

                # Parse UxPlay output for status updates
                lower = line.lower()
                if "client connected" in lower or "connection from" in lower:
                    if self.on_status_change:
                        self.on_status_change("🟢 iPhone Connected — Mirroring Active", True)
                    if self.on_client_connected:
                        self.on_client_connected(line)

                elif "client disconnected" in lower or "connection closed" in lower or "teardown" in lower:
                    if self.on_status_change:
                        self.on_status_change("Waiting for iPhone Screen Mirror", True)
                    if self.on_client_disconnected:
                        self.on_client_disconnected()

                elif "error" in lower or "failed" in lower:
                    if self.on_error:
                        self.on_error(line)

        except Exception as e:
            if self._running:
                print(f"[AirPlay] Monitor thread error: {e}")

        # Process ended
        if self._running:
            self._running = False
            if self.on_status_change:
                self.on_status_change("AirPlay Receiver Stopped", False)

    def stop(self):
        """Stop the AirPlay receiver."""
        self._running = False

        if self._process:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=3)
            except Exception as e:
                print(f"[AirPlay] Error stopping UxPlay: {e}")
            finally:
                self._process = None

        if self.on_status_change:
            self.on_status_change("AirPlay Receiver Stopped", False)

        print("[AirPlay] Receiver stopped")

    def restart(self) -> bool:
        """Restart the AirPlay receiver."""
        self.stop()
        time.sleep(1)
        return self.start()

    @property
    def is_running(self) -> bool:
        """Check if the receiver is currently running."""
        if self._process and self._process.poll() is None:
            return True
        return False

    def get_status(self) -> dict:
        """Return current receiver status."""
        return {
            "running": self.is_running,
            "installed": self.is_installed(),
            "uxplay_path": self._uxplay_path,
            "server_name": self.server_name,
        }
