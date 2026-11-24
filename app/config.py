# Configuration and Windows Startup Manager
import os
import sys
import json
import winreg
from pathlib import Path

APP_NAME = "AirContinuity"
DEFAULT_CONFIG = {
    "server_port": 8089,
    "download_dir": str(Path.home() / "Downloads" / "AirContinuity"),
    "start_on_boot": True,
    "minimize_to_tray": True,
    "device_name": "My iPhone",
    "theme": "dark",
    "auto_clipboard_sync": True
}

def get_app_dir() -> Path:
    """Return persistent configuration directory in %APPDATA%."""
    app_data = os.environ.get("APPDATA", str(Path.home()))
    target = Path(app_data) / APP_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target

def get_config_path() -> Path:
    return get_app_dir() / "config.json"

def load_config() -> dict:
    path = get_config_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(data)
                return config
        except Exception:
            pass
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()

def save_config(config: dict):
    path = get_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Failed to save config: {e}")

def get_executable_path() -> str:
    """Return the absolute path of the running executable or script."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])

def is_run_at_startup() -> bool:
    """Check if the app is configured to run at Windows startup."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except Exception:
        return False

def set_run_at_startup(enable: bool) -> bool:
    """Add or remove the app from Windows CurrentVersion\\Run."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                exe_path = get_executable_path()
                cmd = f'"{exe_path}" --startup'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        print(f"Error modifying startup registry: {e}")
        return False
