"""
AirContinuity Modern Windows Setup Wizard (Windows 10 / 11)
Self-contained graphical installer for AirContinuity.
Installs AirContinuity, UxPlay, and BleHid with desktop/start-menu shortcuts
and Windows Add/Remove Programs integration.
Includes Educational & Privacy Policy Agreement.
"""
import os
import sys
import shutil
import zipfile
import winreg
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

APP_NAME = "AirContinuity"
APP_VERSION = "2.0.0"
APP_PUBLISHER = "AirContinuity Open Source Project"
APP_DESCRIPTION = "Apple Ecosystem & AirDrop Bridge for Windows (AirDrop, Mirroring, Notifications, HID Control)"

PRIVACY_POLICY_TEXT = """AIRCONTINUITY PRIVACY POLICY & EDUCATIONAL DISCLAIMER

1. EDUCATIONAL & RESEARCH PURPOSE
AirContinuity is developed strictly for educational, academic research, and personal device interoperability purposes. It demonstrates reverse-engineered implementations of open protocols (such as Apple Wireless Direct Link / Bonjour mDNS, Apple Notification Center Service over Bluetooth LE GATT, AirPlay RTSP/FairPlay receiver specifications, and standard Human Interface Device over GATT / HOGP).

This software is NOT affiliated with, endorsed by, or sponsored by Apple Inc. or Microsoft Corporation. All Apple trademarks (AirDrop, AirPlay, iOS, iPhone, macOS) and Microsoft trademarks (Windows) belong to their respective owners.

2. ZERO APP MONITORING OR SURVEILLANCE
• AirContinuity does NOT monitor, scan, log, or track your installed applications, open windows, process lists, or desktop activities.
• The Bluetooth LE HID input controller only redirects hardware keyboard and mouse events when you explicitly trigger "Capture Input" (or command mode), sending standard HID reports solely to your paired iPhone. It never logs, captures, or saves keystrokes to disk or memory.
• Screen mirroring features (AirPlay / WebRTC) display an incoming video stream from your own authorized iPhone locally onto your PC display. The software never records, snapshots, or uploads your screen content.

3. 100% LOCAL PEER-TO-PEER (NO CLOUD SERVERS)
• All communications—including file transfers, universal clipboard synchronization, screen mirroring, incoming call alerts, and Bluetooth LE notifications—occur directly and exclusively between your Windows PC and your iPhone over your local Wi-Fi network and direct Bluetooth LE links.
• There are NO backend cloud servers, tracking relays, or third-party proxies. No data ever leaves your local network.
• AirContinuity contains zero telemetry, zero analytics SDKs, zero user tracking, and zero advertising trackers.

4. USER CONSENT & ACCEPTANCE
By installing or using AirContinuity, you acknowledge and agree that this software is provided for personal educational interoperability purposes only, on an "AS IS" basis without warranties of any kind.
"""


def get_default_install_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Programs" / APP_NAME
    return Path.home() / "AppData" / "Local" / "Programs" / APP_NAME


def get_bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def create_windows_shortcut(target_path: str, shortcut_path: str, icon_path: str = None, description: str = ""):
    """Create a Windows .lnk shortcut using PowerShell without external python dependencies."""
    icon_line = f"$s.IconLocation = '{icon_path}';" if icon_path and os.path.exists(icon_path) else ""
    ps_cmd = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{shortcut_path}'); "
        f"$s.TargetPath = '{target_path}'; "
        f"$s.WorkingDirectory = '{os.path.dirname(target_path)}'; "
        f"$s.Description = '{description}'; "
        f"{icon_line} "
        f"$s.Save()"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                       capture_output=True, check=True)
    except Exception as e:
        print(f"Error creating shortcut {shortcut_path}: {e}")


def register_uninstall_entry(install_dir: Path, exe_path: Path):
    """Register the application in Windows Add/Remove Programs (HKCU)."""
    try:
        key_path = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            uninst_cmd = f'powershell -Command "Remove-Item -Recurse -Force \'{install_dir}\'; Remove-Item -Force \'$([Environment]::GetFolderPath(\'Desktop\'))\\{APP_NAME}.lnk\'; Remove-Item -Force \'$([Environment]::GetFolderPath(\'StartMenu\'))\\Programs\\{APP_NAME}.lnk\'; Remove-Item -Recurse -Force \'HKCU:\\{key_path}\' "'
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(exe_path))
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(install_dir))
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, uninst_cmd)
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    except Exception as e:
        print(f"Failed to register uninstall entry: {e}")


class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} Setup — v{APP_VERSION}")
        self.geometry("640x500")
        self.minsize(600, 460)
        self.resizable(False, False)

        # Apply dark theme styling
        self.configure(bg="#1E1E20")
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.style.configure(".", background="#1E1E20", foreground="#FFFFFF")
        self.style.configure("TLabel", background="#1E1E20", foreground="#FFFFFF")
        self.style.configure("TButton", background="#0A84FF", foreground="#FFFFFF", borderwidth=0)
        self.style.map("TButton", background=[("active", "#0060D0")])

        self.install_dir = tk.StringVar(value=str(get_default_install_dir()))
        self.create_desktop_shortcut = tk.BooleanVar(value=True)
        self.create_start_shortcut = tk.BooleanVar(value=True)
        self.policy_accepted = tk.BooleanVar(value=False)
        self.launch_after_install = tk.BooleanVar(value=True)

        self.current_step = 0
        self.steps = ["welcome", "privacy", "directory", "installing", "finish"]

        # Top Banner
        self.banner = tk.Frame(self, bg="#141416", height=70)
        self.banner.pack(fill="x", side="top")
        self.banner_title = tk.Label(self.banner, text=f"Install {APP_NAME}", font=("Segoe UI", 16, "bold"),
                                     bg="#141416", fg="#FFFFFF")
        self.banner_title.pack(anchor="w", padx=24, pady=(14, 2))
        self.banner_sub = tk.Label(self.banner, text="Apple Ecosystem Bridge for Windows 10 & 11",
                                   font=("Segoe UI", 10), bg="#141416", fg="#8E8E93")
        self.banner_sub.pack(anchor="w", padx=24, pady=(0, 10))

        # Content Container
        self.container = tk.Frame(self, bg="#1E1E20")
        self.container.pack(fill="both", expand=True, padx=24, pady=16)

        # Bottom Button Bar
        self.button_bar = tk.Frame(self, bg="#18181A", height=60)
        self.button_bar.pack(fill="x", side="bottom")

        self.btn_cancel = tk.Button(self.button_bar, text="Cancel", font=("Segoe UI", 10), bg="#2C2C2E",
                                    fg="#FFFFFF", activebackground="#3A3A3C", activeforeground="#FFFFFF",
                                    bd=0, padx=16, pady=6, command=self.destroy)
        self.btn_cancel.pack(side="left", padx=20, pady=14)

        self.btn_next = tk.Button(self.button_bar, text="Next >", font=("Segoe UI", 10, "bold"), bg="#0A84FF",
                                  fg="#FFFFFF", activebackground="#0060D0", activeforeground="#FFFFFF",
                                  bd=0, padx=20, pady=6, command=self.on_next)
        self.btn_next.pack(side="right", padx=20, pady=14)

        self.btn_back = tk.Button(self.button_bar, text="< Back", font=("Segoe UI", 10), bg="#2C2C2E",
                                  fg="#FFFFFF", activebackground="#3A3A3C", activeforeground="#FFFFFF",
                                  bd=0, padx=16, pady=6, command=self.on_back)
        self.btn_back.pack(side="right", padx=(0, 8), pady=14)

        self.frames = {}
        self._build_welcome_frame()
        self._build_privacy_frame()
        self._build_directory_frame()
        self._build_installing_frame()
        self._build_finish_frame()

        self.show_step("welcome")

    def show_step(self, step_name: str):
        for name, frame in self.frames.items():
            if name == step_name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()

        if step_name == "welcome":
            self.banner_title.configure(text=f"Welcome to {APP_NAME} Setup")
            self.banner_sub.configure(text="Install Apple Continuity & AirDrop on your Windows PC")
            self.btn_back.configure(state="disabled")
            self.btn_next.configure(text="Next >", state="normal")
            self.btn_cancel.configure(state="normal")
        elif step_name == "privacy":
            self.banner_title.configure(text="Privacy Policy & Educational Disclaimer")
            self.banner_sub.configure(text="Please review the privacy commitments before proceeding")
            self.btn_back.configure(state="normal")
            self._update_privacy_btn()
            self.btn_cancel.configure(state="normal")
        elif step_name == "directory":
            self.banner_title.configure(text="Choose Install Location")
            self.banner_sub.configure(text="Select the destination folder for AirContinuity")
            self.btn_back.configure(state="normal")
            self.btn_next.configure(text="Install", state="normal")
            self.btn_cancel.configure(state="normal")
        elif step_name == "installing":
            self.banner_title.configure(text="Installing AirContinuity...")
            self.banner_sub.configure(text="Please wait while files and shortcuts are installed")
            self.btn_back.configure(state="disabled")
            self.btn_next.configure(state="disabled")
            self.btn_cancel.configure(state="disabled")
            threading.Thread(target=self._run_installation, daemon=True).start()
        elif step_name == "finish":
            self.banner_title.configure(text="Installation Complete!")
            self.banner_sub.configure(text=f"{APP_NAME} has been successfully installed on your PC")
            self.btn_back.configure(state="disabled")
            self.btn_next.configure(text="Finish", state="normal", command=self.on_finish)
            self.btn_cancel.configure(state="disabled")

    def _build_welcome_frame(self):
        frame = tk.Frame(self.container, bg="#1E1E20")
        self.frames["welcome"] = frame

        title = tk.Label(frame, text=f"{APP_NAME} for Windows 10 / 11", font=("Segoe UI", 14, "bold"),
                         bg="#1E1E20", fg="#FFFFFF")
        title.pack(anchor="w", pady=(10, 8))

        desc = (
            f"This wizard will install {APP_NAME} on your computer.\n\n"
            "Key Continuity Features Included:\n"
            "• 📁 AirDrop-style direct Wi-Fi file transfers\n"
            "• 🖥️ Native 60 FPS AirPlay screen mirroring with hardware decoding\n"
            "• 🎮 Full Keyboard, Mouse & Trackpad control of your iPhone via Bluetooth LE\n"
            "• 🔔 Real-time iPhone push notifications (ANCS) & phone call controls\n"
            "• 📋 Instant two-way Universal Clipboard sync\n\n"
            "Click 'Next' to review the Privacy Policy and begin setup."
        )
        desc_lbl = tk.Label(frame, text=desc, font=("Segoe UI", 10), bg="#1E1E20", fg="#D1D1D6",
                            justify="left", wraplength=580)
        desc_lbl.pack(anchor="w", pady=(0, 10))

    def _build_privacy_frame(self):
        frame = tk.Frame(self.container, bg="#1E1E20")
        self.frames["privacy"] = frame

        txt_frame = tk.Frame(frame, bg="#141416", bd=1, relief="solid")
        txt_frame.pack(fill="both", expand=True, pady=(0, 10))

        scrollbar = tk.Scrollbar(txt_frame)
        scrollbar.pack(side="right", fill="y")

        text_widget = tk.Text(txt_frame, wrap="word", yscrollcommand=scrollbar.set,
                              font=("Segoe UI", 9), bg="#141416", fg="#D1D1D6", bd=0, padx=10, pady=10)
        text_widget.insert("1.0", PRIVACY_POLICY_TEXT)
        text_widget.configure(state="disabled")
        text_widget.pack(fill="both", expand=True)
        scrollbar.config(command=text_widget.yview)

        chk = tk.Checkbutton(frame, text="I have read and accept the Educational Disclaimer and Privacy Policy",
                             variable=self.policy_accepted, font=("Segoe UI", 10, "bold"), bg="#1E1E20",
                             fg="#30D158", selectcolor="#141416", activebackground="#1E1E20",
                             activeforeground="#30D158", command=self._update_privacy_btn)
        chk.pack(anchor="w", pady=(0, 4))

    def _update_privacy_btn(self):
        if self.policy_accepted.get():
            self.btn_next.configure(state="normal", text="Next >")
        else:
            self.btn_next.configure(state="disabled", text="Accept to Continue")

    def _build_directory_frame(self):
        frame = tk.Frame(self.container, bg="#1E1E20")
        self.frames["directory"] = frame

        lbl = tk.Label(frame, text="Select Destination Directory:", font=("Segoe UI", 11, "bold"),
                       bg="#1E1E20", fg="#FFFFFF")
        lbl.pack(anchor="w", pady=(10, 6))

        dir_box = tk.Frame(frame, bg="#1E1E20")
        dir_box.pack(fill="x", pady=(0, 20))

        self.entry_dir = tk.Entry(dir_box, textvariable=self.install_dir, font=("Segoe UI", 10),
                                  bg="#2C2C2E", fg="#FFFFFF", bd=1, relief="solid")
        self.entry_dir.pack(side="left", fill="x", expand=True, padx=(0, 10), ipady=4)

        btn_browse = tk.Button(dir_box, text="Browse...", font=("Segoe UI", 9), bg="#2C2C2E",
                               fg="#FFFFFF", bd=0, padx=12, pady=4, command=self._browse_dir)
        btn_browse.pack(side="left")

        opt_lbl = tk.Label(frame, text="Additional Shortcuts & Integrations:", font=("Segoe UI", 11, "bold"),
                           bg="#1E1E20", fg="#FFFFFF")
        opt_lbl.pack(anchor="w", pady=(10, 6))

        chk_desk = tk.Checkbutton(frame, text="Create Desktop Shortcut", variable=self.create_desktop_shortcut,
                                  font=("Segoe UI", 10), bg="#1E1E20", fg="#FFFFFF", selectcolor="#141416",
                                  activebackground="#1E1E20", activeforeground="#FFFFFF")
        chk_desk.pack(anchor="w", pady=2)

        chk_start = tk.Checkbutton(frame, text="Create Start Menu Shortcut", variable=self.create_start_shortcut,
                                   font=("Segoe UI", 10), bg="#1E1E20", fg="#FFFFFF", selectcolor="#141416",
                                   activebackground="#1E1E20", activeforeground="#FFFFFF")
        chk_start.pack(anchor="w", pady=2)

    def _browse_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.install_dir.get())
        if chosen:
            self.install_dir.set(str(Path(chosen) / APP_NAME))

    def _build_installing_frame(self):
        frame = tk.Frame(self.container, bg="#1E1E20")
        self.frames["installing"] = frame

        self.lbl_progress = tk.Label(frame, text="Extracting files...", font=("Segoe UI", 11),
                                     bg="#1E1E20", fg="#FFFFFF")
        self.lbl_progress.pack(anchor="w", pady=(40, 10))

        self.progress_bar = ttk.Progressbar(frame, mode="determinate", length=540)
        self.progress_bar.pack(fill="x", pady=(0, 16))

        self.lbl_detail = tk.Label(frame, text="", font=("Segoe UI", 9), bg="#1E1E20", fg="#8E8E93")
        self.lbl_detail.pack(anchor="w")

    def _build_finish_frame(self):
        frame = tk.Frame(self.container, bg="#1E1E20")
        self.frames["finish"] = frame

        success_lbl = tk.Label(frame, text="✓ Installation Completed Successfully!", font=("Segoe UI", 14, "bold"),
                               bg="#1E1E20", fg="#30D158")
        success_lbl.pack(anchor="w", pady=(20, 10))

        msg = (
            f"{APP_NAME} has been installed to:\n"
            f"{self.install_dir.get()}\n\n"
            "You can now launch AirContinuity from your Desktop, Start Menu, or directly from here.\n"
            "To connect your iPhone, ensure Bluetooth and Wi-Fi are turned on."
        )
        msg_lbl = tk.Label(frame, text=msg, font=("Segoe UI", 10), bg="#1E1E20", fg="#D1D1D6",
                           justify="left", wraplength=560)
        msg_lbl.pack(anchor="w", pady=(0, 20))

        chk_launch = tk.Checkbutton(frame, text="Launch AirContinuity now", variable=self.launch_after_install,
                                    font=("Segoe UI", 11, "bold"), bg="#1E1E20", fg="#0A84FF", selectcolor="#141416",
                                    activebackground="#1E1E20", activeforeground="#0A84FF")
        chk_launch.pack(anchor="w")

    def on_next(self):
        step_idx = self.steps.index(self.frames_current())
        if step_idx < len(self.steps) - 1:
            self.show_step(self.steps[step_idx + 1])

    def on_back(self):
        step_idx = self.steps.index(self.frames_current())
        if step_idx > 0:
            self.show_step(self.steps[step_idx - 1])

    def frames_current(self) -> str:
        for name, frame in self.frames.items():
            if frame.winfo_ismapped():
                return name
        return "welcome"

    def _run_installation(self):
        dest_dir = Path(self.install_dir.get())
        dest_dir.mkdir(parents=True, exist_ok=True)
        bundle_dir = get_bundle_dir()

        self._set_progress(10, "Extracting application binaries...")

        # 1. Look for payload.zip or standalone files
        payload_zip = bundle_dir / "payload.zip"
        if payload_zip.exists():
            with zipfile.ZipFile(payload_zip, "r") as zf:
                total_files = len(zf.namelist())
                for i, member in enumerate(zf.namelist(), 1):
                    zf.extract(member, dest_dir)
                    if i % 5 == 0:
                        pct = 10 + int((i / total_files) * 60)
                        self._set_progress(pct, f"Extracting {member}...")
        else:
            # Copy from local bundle directory or project root
            src_files = [
                ("AirContinuity.exe", bundle_dir / "AirContinuity.exe"),
                ("PRIVACY_POLICY.md", bundle_dir / "PRIVACY_POLICY.md"),
            ]
            for name, src in src_files:
                if src.exists():
                    shutil.copy2(src, dest_dir / name)

            for dname in ["blehid", "uxplay"]:
                src_d = bundle_dir / dname
                dst_d = dest_dir / dname
                if src_d.exists():
                    if dst_d.exists():
                        shutil.rmtree(dst_d)
                    shutil.copytree(src_d, dst_d)

        self._set_progress(75, "Creating Windows shortcuts...")

        exe_path = dest_dir / "AirContinuity.exe"
        icon_path = dest_dir / "app" / "ui" / "assets" / "icon.ico"
        if not icon_path.exists():
            icon_path = exe_path

        # Create Desktop Shortcut
        if self.create_desktop_shortcut.get():
            desktop_dir = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
            if desktop_dir.exists():
                lnk = str(desktop_dir / f"{APP_NAME}.lnk")
                create_windows_shortcut(str(exe_path), lnk, str(icon_path), APP_DESCRIPTION)

        # Create Start Menu Shortcut
        if self.create_start_shortcut.get():
            start_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if start_dir.exists():
                lnk = str(start_dir / f"{APP_NAME}.lnk")
                create_windows_shortcut(str(exe_path), lnk, str(icon_path), APP_DESCRIPTION)

        self._set_progress(90, "Registering Windows uninstaller...")
        register_uninstall_entry(dest_dir, exe_path)

        self._set_progress(100, "Done!")
        self.after(500, lambda: self.show_step("finish"))

    def _set_progress(self, val: int, text: str):
        self.after(0, lambda: [
            self.progress_bar.configure(value=val),
            self.lbl_detail.configure(text=text)
        ])

    def on_finish(self):
        if self.launch_after_install.get():
            exe_path = Path(self.install_dir.get()) / "AirContinuity.exe"
            if exe_path.exists():
                subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent))
        self.destroy()


def main():
    app = InstallerApp()
    app.mainloop()


if __name__ == "__main__":
    main()

