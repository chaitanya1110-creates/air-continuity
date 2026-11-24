"""
AirContinuity Desktop GUI (CustomTkinter)
Modern, Apple-style Windows application providing:
- QR code pairing and live status
- Screen Mirror viewer launcher
- Notifications feed & Incoming Call answer/decline controls
- AirDrop-style file transfer manager
- Universal Clipboard history & live sync
- Settings & Windows Startup integration
"""
import os
import sys
import webbrowser
import subprocess
import shutil
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Dict, Any, List

import customtkinter as ctk
from PIL import Image
import qrcode

from app import config
from app.ancs_service import ANCSClient
from app.clipboard_sync import ClipboardSync
from app.file_transfer import FileTransferManager
from app.mirror_server import MirrorServer
from app.airplay_bonjour import BonjourService
from app.airplay_receiver import AirPlayReceiver
from app.input_control import InputController

# Set CustomTkinter theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class MainWindow(ctk.CTk):
    def __init__(self,
                 cfg: dict,
                 ancs_client: ANCSClient,
                 clipboard_sync: ClipboardSync,
                 file_manager: FileTransferManager,
                 mirror_server: MirrorServer,
                 bonjour_service: BonjourService,
                 airplay_receiver: AirPlayReceiver = None,
                 input_controller: InputController = None):
        super().__init__()

        self.cfg = cfg
        self.ancs_client = ancs_client
        self.clipboard_sync = clipboard_sync
        self.file_manager = file_manager
        self.mirror_server = mirror_server
        self.bonjour_service = bonjour_service
        self.airplay_receiver = airplay_receiver
        self.input_controller = input_controller

        self.local_ip = self.bonjour_service.get_local_ip()
        self.port = self.cfg.get("server_port", 8089)
        self.pairing_url = f"http://{self.local_ip}:{self.port}"

        self.title("AirContinuity — iPhone Bridge for Windows")
        self.geometry("1060x680")
        self.minsize(920, 600)

        # Set Window Icon
        icon_path = Path(__file__).resolve().parent / "assets" / "icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        # State
        self.notifications: List[Dict[str, Any]] = []
        self.active_call_uid = None
        self.current_tab = "overview"

        # Wire callbacks
        self.ancs_client.on_notification = self._on_ancs_notification
        self.ancs_client.on_call = self._on_incoming_call
        self.ancs_client.on_status = self._on_ancs_status
        self.clipboard_sync.on_change = self._on_clipboard_change
        self.file_manager.on_transfer = self._on_file_transfer
        self.mirror_server.on_client_connect_cb = self._on_client_connected
        self.mirror_server.on_screen_mirror_cb = self._on_mirror_state_changed

        if self.input_controller:
            self.input_controller.on_status_change = self._on_input_status_changed

        self.protocol("WM_DELETE_WINDOW", self.on_close_requested)

        self._build_ui()
        self.select_tab("overview")

    def _build_ui(self):
        # Main layout: Sidebar (col 0) + Content (col 1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 1. Sidebar
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color="#141416")
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.sidebar.grid_rowconfigure(7, weight=1)

        # App Brand Header
        self.logo_label = ctk.CTkLabel(
            self.sidebar,
            text="AirContinuity",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#FFFFFF"
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(24, 4), sticky="w")

        self.sub_logo = ctk.CTkLabel(
            self.sidebar,
            text="Apple Ecosystem for PC",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#8E8E93"
        )
        self.sub_logo.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="w")

        # Navigation Buttons
        self.nav_buttons = {}
        nav_items = [
            ("overview", "📱  Overview & Pair"),
            ("mirror", "🖥️  Screen Mirror"),
            ("notifications", "🔔  Notifications & Calls"),
            ("airdrop", "📁  AirDrop Files"),
            ("clipboard", "📋  Universal Clipboard"),
            ("settings", "⚙️  Settings"),
        ]

        for i, (key, label) in enumerate(nav_items, start=2):
            btn = ctk.CTkButton(
                self.sidebar,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
                height=42,
                corner_radius=10,
                anchor="w",
                fg_color="transparent",
                text_color="#EBEBF5",
                hover_color="#2C2C2E",
                command=lambda k=key: self.select_tab(k)
            )
            btn.grid(row=i, column=0, padx=14, pady=4, sticky="ew")
            self.nav_buttons[key] = btn

        # Bottom Status in Sidebar
        self.status_card = ctk.CTkFrame(self.sidebar, corner_radius=12, fg_color="#1C1C1E")
        self.status_card.grid(row=8, column=0, padx=14, pady=16, sticky="ew")

        self.ble_dot = ctk.CTkLabel(
            self.status_card,
            text="● BLE ANCS Active",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#30D158"
        )
        self.ble_dot.pack(anchor="w", padx=12, pady=(10, 2))

        self.ip_info_label = ctk.CTkLabel(
            self.status_card,
            text=f"Wi-Fi: {self.local_ip}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#8E8E93"
        )
        self.ip_info_label.pack(anchor="w", padx=12, pady=(0, 10))

        # 2. Main Content Frame
        self.content_area = ctk.CTkFrame(self, corner_radius=0, fg_color="#1C1C1E")
        self.content_area.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.content_area.grid_columnconfigure(0, weight=1)
        self.content_area.grid_rowconfigure(1, weight=1)

        # Global Top Bar for Incoming Calls / Quick Action
        self.call_banner = ctk.CTkFrame(self.content_area, corner_radius=12, fg_color="#2C2C2E")
        self._setup_call_banner()

        # Tab Containers
        self.tab_frames = {}
        self._build_overview_tab()
        self._build_mirror_tab()
        self._build_notifications_tab()
        self._build_airdrop_tab()
        self._build_clipboard_tab()
        self._build_settings_tab()

    def _setup_call_banner(self):
        # Hidden by default, shown when incoming call arrives
        self.call_title = ctk.CTkLabel(
            self.call_banner,
            text="📞 Incoming iPhone Call",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#30D158"
        )
        self.call_title.pack(side="left", padx=16, pady=10)

        self.call_caller_label = ctk.CTkLabel(
            self.call_banner,
            text="Calling...",
            font=ctk.CTkFont(size=13),
            text_color="#FFFFFF"
        )
        self.call_caller_label.pack(side="left", padx=10, pady=10)

        self.btn_call_decline = ctk.CTkButton(
            self.call_banner,
            text="Decline",
            width=80,
            height=30,
            fg_color="#FF453A",
            hover_color="#D70015",
            command=self._on_decline_call_clicked
        )
        self.btn_call_decline.pack(side="right", padx=(6, 16), pady=10)

        self.btn_call_answer = ctk.CTkButton(
            self.call_banner,
            text="Answer",
            width=80,
            height=30,
            fg_color="#30D158",
            hover_color="#248A3D",
            command=self._on_answer_call_clicked
        )
        self.btn_call_answer.pack(side="right", padx=6, pady=10)

    def select_tab(self, key: str):
        self.current_tab = key
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(fg_color="#0A84FF", text_color="#FFFFFF")
            else:
                btn.configure(fg_color="transparent", text_color="#EBEBF5")

        for k, frame in self.tab_frames.items():
            if k == key:
                frame.grid(row=1, column=0, sticky="nsew", padx=24, pady=20)
            else:
                frame.grid_forget()

    # --- TAB 1: OVERVIEW & PAIRING ---
    def _build_overview_tab(self):
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.tab_frames["overview"] = frame
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        # Left Column: QR Code & Pairing
        left_box = ctk.CTkFrame(frame, corner_radius=16, fg_color="#242426")
        left_box.grid(row=0, column=0, sticky="nsew", padx=(0, 12), pady=0)

        title = ctk.CTkLabel(
            left_box,
            text="Pair Your iPhone",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title.pack(anchor="w", padx=20, pady=(20, 4))

        sub = ctk.CTkLabel(
            left_box,
            text="Scan this QR code with your iPhone Camera to open the AirContinuity Companion.",
            font=ctk.CTkFont(size=13),
            text_color="#8E8E93",
            wraplength=340,
            justify="left"
        )
        sub.pack(anchor="w", padx=20, pady=(0, 16))

        # Generate QR Code Image
        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(self.pairing_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        self.ctk_qr = ctk.CTkImage(light_image=qr_img, dark_image=qr_img, size=(190, 190))
        qr_label = ctk.CTkLabel(left_box, image=self.ctk_qr, text="")
        qr_label.pack(pady=10)

        url_label = ctk.CTkLabel(
            left_box,
            text=self.pairing_url,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#0A84FF"
        )
        url_label.pack(pady=(4, 14))

        btn_row = ctk.CTkFrame(left_box, fg_color="transparent")
        btn_row.pack(pady=(0, 20))

        btn_copy = ctk.CTkButton(
            btn_row,
            text="Copy Link",
            width=110,
            command=lambda: self.clipboard_sync.set_windows_clipboard(self.pairing_url, source="PC")
        )
        btn_copy.pack(side="left", padx=6)

        btn_open = ctk.CTkButton(
            btn_row,
            text="Open in Browser",
            width=130,
            fg_color="#2C2C2E",
            command=lambda: webbrowser.open(self.pairing_url)
        )
        btn_open.pack(side="left", padx=6)

        # Right Column: Features summary & Instructions
        right_box = ctk.CTkFrame(frame, corner_radius=16, fg_color="#242426")
        right_box.grid(row=0, column=1, sticky="nsew", padx=(12, 0), pady=0)

        right_title = ctk.CTkLabel(
            right_box,
            text="Active Continuity Features",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        right_title.pack(anchor="w", padx=20, pady=(20, 12))

        features = [
            ("📺  Screen Mirroring", "Native AirPlay receiver — mirror iPhone via Control Center."),
            ("🔔  ANCS Notifications", "Receive push alerts for iMessage, WhatsApp, Mail & Apps."),
            ("📞  Incoming Call Relay", "Answer or decline calls directly from your desktop."),
            ("📋  Universal Clipboard", "Copy text on iPhone, paste on Windows instantly."),
            ("📁  AirDrop Transfers", "Zero-install Wi-Fi file dropping to Downloads."),
            ("🚀  Windows Startup", "Launches silently on Windows boot into System Tray.")
        ]

        for icon_title, desc in features:
            f_frame = ctk.CTkFrame(right_box, fg_color="transparent")
            f_frame.pack(anchor="w", padx=20, pady=6, fill="x")

            t_lbl = ctk.CTkLabel(f_frame, text=icon_title, font=ctk.CTkFont(size=14, weight="bold"), text_color="#FFFFFF")
            t_lbl.pack(anchor="w")

            d_lbl = ctk.CTkLabel(f_frame, text=desc, font=ctk.CTkFont(size=12), text_color="#8E8E93")
            d_lbl.pack(anchor="w")

    # --- TAB 2: SCREEN MIRROR (AirPlay Receiver) ---
    def _build_mirror_tab(self):
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.tab_frames["mirror"] = frame
        frame.grid_columnconfigure(0, weight=1)

        card = ctk.CTkScrollableFrame(frame, corner_radius=16, fg_color="#242426")
        card.pack(fill="both", expand=True, padx=0, pady=0)

        title = ctk.CTkLabel(card, text="iPhone Screen Mirroring & Control", font=ctk.CTkFont(size=20, weight="bold"))
        title.pack(anchor="w", padx=24, pady=(24, 6))

        sub = ctk.CTkLabel(
            card,
            text="Mirror your iPhone screen and control it with your PC keyboard, mouse, and trackpad.",
            font=ctk.CTkFont(size=13),
            text_color="#8E8E93"
        )
        sub.pack(anchor="w", padx=24, pady=(0, 20))

        # Status badge
        self.mirror_state_badge = ctk.CTkLabel(
            card,
            text="⚪ AirPlay Receiver: Not Started",
            font=ctk.CTkFont(size=14, weight="normal"),
            text_color="#8E8E93"
        )
        self.mirror_state_badge.pack(pady=(10, 16))

        # Button row
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(pady=(0, 10))

        self.btn_start_airplay = ctk.CTkButton(
            btn_row,
            text="▶  Start AirPlay Receiver",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=46,
            width=260,
            fg_color="#0A84FF",
            hover_color="#0060D0",
            command=self._on_start_airplay_clicked
        )
        self.btn_start_airplay.pack(side="left", padx=6)

        self.btn_stop_airplay = ctk.CTkButton(
            btn_row,
            text="⏹  Stop",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=46,
            width=100,
            fg_color="#FF453A",
            hover_color="#D70015",
            command=self._on_stop_airplay_clicked
        )
        self.btn_stop_airplay.pack(side="left", padx=6)

        # Install notice (shown only if UxPlay is not installed)
        self.install_frame = ctk.CTkFrame(card, corner_radius=12, fg_color="#2C2416", border_width=1, border_color="#FF9F0A")
        self.install_notice_title = ctk.CTkLabel(
            self.install_frame,
            text="⚠️  UxPlay AirPlay Receiver Not Found",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FF9F0A"
        )
        self.install_notice_title.pack(anchor="w", padx=16, pady=(14, 4))

        self.install_notice_body = ctk.CTkLabel(
            self.install_frame,
            text="AirContinuity uses UxPlay (open-source) to receive AirPlay screen mirroring.\nClick below to install it automatically via Windows Package Manager (winget).",
            font=ctk.CTkFont(size=12),
            text_color="#EBEBF5",
            justify="left"
        )
        self.install_notice_body.pack(anchor="w", padx=16, pady=(0, 10))

        self.btn_install_uxplay = ctk.CTkButton(
            self.install_frame,
            text="📦  Install UxPlay Now",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            fg_color="#FF9F0A",
            text_color="#000000",
            hover_color="#E08E00",
            command=self._on_install_uxplay_clicked
        )
        self.btn_install_uxplay.pack(anchor="w", padx=16, pady=(0, 14))

        # --- KEYBOARD, MOUSE & TRACKPAD CONTROL SECTION ---
        input_card = ctk.CTkFrame(card, corner_radius=12, fg_color="#1C1C1E")
        input_card.pack(padx=24, pady=(10, 16), fill="x")

        ic_header = ctk.CTkFrame(input_card, fg_color="transparent")
        ic_header.pack(fill="x", padx=16, pady=(14, 6))

        ic_title = ctk.CTkLabel(
            ic_header,
            text="🎮  Keyboard, Mouse & Trackpad Control",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#FFFFFF"
        )
        ic_title.pack(side="left")

        self.input_state_badge = ctk.CTkLabel(
            ic_header,
            text="🟢 Bluetooth HID: Ready" if (self.input_controller and self.input_controller.is_connected) else "⚪ Bluetooth HID: Ready",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#30D158" if (self.input_controller and self.input_controller.is_connected) else "#8E8E93"
        )
        self.input_state_badge.pack(side="right")

        ic_sub = ctk.CTkLabel(
            input_card,
            text="Control your mirrored iPhone using your PC keyboard, mouse, and trackpad gestures.",
            font=ctk.CTkFont(size=12),
            text_color="#8E8E93"
        )
        ic_sub.pack(anchor="w", padx=16, pady=(0, 10))

        # Capture control buttons
        ic_btn_row = ctk.CTkFrame(input_card, fg_color="transparent")
        ic_btn_row.pack(fill="x", padx=16, pady=(0, 12))

        self.btn_capture_input = ctk.CTkButton(
            ic_btn_row,
            text="🎯  Capture Input (Drive iPhone)",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            width=260,
            fg_color="#30D158",
            hover_color="#28B84D",
            command=self._on_toggle_capture_clicked
        )
        self.btn_capture_input.pack(side="left", padx=(0, 10))

        # Quick text sending input
        self.entry_quick_type = ctk.CTkEntry(
            ic_btn_row,
            placeholder_text="Type text to send to iPhone...",
            height=42,
            width=280
        )
        self.entry_quick_type.pack(side="left", padx=(0, 8), fill="x", expand=True)
        self.entry_quick_type.bind("<Return>", lambda e: self._on_send_quick_type())

        self.btn_send_type = ctk.CTkButton(
            ic_btn_row,
            text="Send Text",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=42,
            width=90,
            fg_color="#5856D6",
            hover_color="#4745B8",
            command=self._on_send_quick_type
        )
        self.btn_send_type.pack(side="left")

        # Shortcuts and gestures guide
        guide_box = ctk.CTkFrame(input_card, corner_radius=8, fg_color="#141416")
        guide_box.pack(fill="x", padx=16, pady=(0, 14))

        guide_items = (
            "• 🖱️  Mouse / Trackpad: Move cursor across screen • Left-click to tap • Scroll wheel / 2-finger swipe to scroll\n"
            "• ⌨️  Keyboard: Type in any app, iMessage, Notes, Safari, or search bar\n"
            "• ⚡ Release Control: Press Ctrl + Alt + Q anytime to instantly return input to PC\n"
            "• 💡 iPhone Setup: Enable Settings → Accessibility → Touch → AssistiveTouch for on-screen cursor"
        )
        guide_lbl = ctk.CTkLabel(
            guide_box,
            text=guide_items,
            font=ctk.CTkFont(size=12),
            text_color="#A1A1A6",
            justify="left"
        )
        guide_lbl.pack(anchor="w", padx=12, pady=10)

        # Instructions card
        instr_card = ctk.CTkFrame(card, corner_radius=12, fg_color="#1C1C1E")
        instr_card.pack(padx=24, pady=(0, 24), fill="x")

        instr_title = ctk.CTkLabel(instr_card, text="How to mirror your iPhone screen:", font=ctk.CTkFont(size=14, weight="bold"))
        instr_title.pack(anchor="w", padx=16, pady=(14, 8))

        steps = (
            "1. Click 'Start AirPlay Receiver' above.\n"
            "2. On your iPhone, swipe down from the top-right corner to open Control Center.\n"
            "3. Tap the 'Screen Mirroring' button (two overlapping rectangles).\n"
            f"4. Select '{self.airplay_receiver.server_name if self.airplay_receiver else 'AirContinuity'}' from the list.\n"
            "5. Your iPhone screen will appear in a window on this PC!\n"
            "6. Click 'Capture Input' above to drive the iPhone with your PC keyboard, mouse, and trackpad.\n\n"
            "Note: Both devices must be on the same Wi-Fi network."
        )
        instr_text = ctk.CTkLabel(instr_card, text=steps, font=ctk.CTkFont(size=13), text_color="#A1A1A6", justify="left")
        instr_text.pack(anchor="w", padx=16, pady=(0, 14))

        # Check installation status and show/hide install notice
        self._update_airplay_install_status()

    def _update_airplay_install_status(self):
        """Show or hide the install notice based on UxPlay availability."""
        if self.airplay_receiver and self.airplay_receiver.is_installed():
            self.install_frame.pack_forget()
            self.btn_start_airplay.configure(state="normal")
        else:
            self.install_frame.pack(padx=24, pady=(0, 16), fill="x")
            self.btn_start_airplay.configure(state="disabled")

    def _on_start_airplay_clicked(self):
        """Start the AirPlay receiver."""
        if not self.airplay_receiver:
            return

        self.btn_start_airplay.configure(state="disabled", text="Starting...")

        def do_start():
            success = self.airplay_receiver.start()
            self.after(0, lambda: self._on_airplay_started(success))

        threading.Thread(target=do_start, daemon=True).start()

    def _on_airplay_started(self, success: bool):
        if success:
            self.btn_start_airplay.configure(
                text="✅  AirPlay Receiver Running",
                state="disabled",
                fg_color="#30D158"
            )
            self.mirror_state_badge.configure(
                text="🟢 AirPlay Receiver Active — Open Control Center on iPhone to Mirror",
                text_color="#30D158"
            )
        else:
            self.btn_start_airplay.configure(
                text="▶  Start AirPlay Receiver",
                state="normal",
                fg_color="#0A84FF"
            )
            self.mirror_state_badge.configure(
                text="🔴 Failed to start AirPlay receiver",
                text_color="#FF453A"
            )
            self._update_airplay_install_status()

    def _on_stop_airplay_clicked(self):
        """Stop the AirPlay receiver."""
        if not self.airplay_receiver:
            return

        self.airplay_receiver.stop()
        self.btn_start_airplay.configure(
            text="▶  Start AirPlay Receiver",
            state="normal",
            fg_color="#0A84FF"
        )
        self.mirror_state_badge.configure(
            text="⚪ AirPlay Receiver: Stopped",
            text_color="#8E8E93"
        )

    def _on_install_uxplay_clicked(self):
        """Install UxPlay via winget."""
        self.btn_install_uxplay.configure(state="disabled", text="Installing... (this may take a minute)")
        self.install_notice_body.configure(text="Downloading and installing UxPlay via winget...\nPlease allow any Windows firewall prompts.")

        def do_install():
            success = self.airplay_receiver.install_uxplay()
            self.after(0, lambda: self._on_uxplay_install_complete(success))

        threading.Thread(target=do_install, daemon=True).start()

    def _on_uxplay_install_complete(self, success: bool):
        if success:
            self.install_notice_title.configure(text="✅ UxPlay Installed Successfully!", text_color="#30D158")
            self.install_notice_body.configure(text="AirPlay receiver is ready. Click 'Start AirPlay Receiver' to begin.")
            self.btn_install_uxplay.configure(text="Installed ✓", state="disabled", fg_color="#30D158")
            self.btn_start_airplay.configure(state="normal")
            # Hide the install card after a short delay
            self.after(3000, lambda: self.install_frame.pack_forget())
        else:
            self.install_notice_title.configure(text="❌ Installation Failed", text_color="#FF453A")
            self.install_notice_body.configure(
                text="Could not install UxPlay automatically.\n"
                     "Try running manually in PowerShell:\n"
                     "  winget install leapbtw.uxplay"
            )
            self.btn_install_uxplay.configure(text="📦  Retry Install", state="normal", fg_color="#FF9F0A")

    # --- Keyboard, Mouse & Trackpad Control Handlers ---
    def _on_toggle_capture_clicked(self):
        """Toggle keyboard and mouse capture between PC and iPhone."""
        if not self.input_controller:
            return
        if self.input_controller.is_capturing:
            self.input_controller.stop_capture()
        else:
            self.input_controller.start_capture()

    def _on_send_quick_type(self):
        """Send typed text to iPhone via BleHid."""
        if not self.input_controller:
            return
        text = self.entry_quick_type.get()
        if text:
            self.input_controller.send_type(text)
            self.entry_quick_type.delete(0, "end")

    def _on_input_status_changed(self, text: str, is_connected: bool, is_capturing: bool):
        """Callback from InputController background thread."""
        self.after(0, lambda: self._update_input_ui(text, is_connected, is_capturing))

    def _update_input_ui(self, text: str, is_connected: bool, is_capturing: bool):
        """Update input UI badges and button states."""
        if not hasattr(self, "input_state_badge"):
            return

        if is_capturing:
            self.input_state_badge.configure(
                text="🎮 Input Captured — Controlling iPhone",
                text_color="#30D158"
            )
            self.btn_capture_input.configure(
                text="⏹  Release Control (Return to PC) [Ctrl+Alt+Q]",
                fg_color="#FF453A",
                hover_color="#D70015"
            )
        elif is_connected:
            self.input_state_badge.configure(
                text="🟢 iPhone Connected (Keyboard & Mouse Ready)",
                text_color="#30D158"
            )
            self.btn_capture_input.configure(
                text="🎯  Capture Input (Drive iPhone)",
                fg_color="#30D158",
                hover_color="#28B84D"
            )
        else:
            self.input_state_badge.configure(
                text=text,
                text_color="#8E8E93"
            )
            self.btn_capture_input.configure(
                text="🎯  Capture Input (Drive iPhone)",
                fg_color="#30D158",
                hover_color="#28B84D"
            )

    # --- TAB 3: NOTIFICATIONS & CALLS ---
    def _build_notifications_tab(self):
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.tab_frames["notifications"] = frame
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        title = ctk.CTkLabel(header, text="Notifications & Phone Calls", font=ctk.CTkFont(size=20, weight="bold"))
        title.pack(side="left")

        btn_clear = ctk.CTkButton(header, text="Clear List", width=90, fg_color="#2C2C2E", command=self.clear_notifications)
        btn_clear.pack(side="right")

        self.notif_scroll = ctk.CTkScrollableFrame(frame, corner_radius=14, fg_color="#242426")
        self.notif_scroll.grid(row=1, column=0, sticky="nsew")

        self.empty_notif_lbl = ctk.CTkLabel(
            self.notif_scroll,
            text="No notifications received yet.\nEnsure iPhone is paired with PC in Windows Bluetooth settings.",
            font=ctk.CTkFont(size=13),
            text_color="#8E8E93"
        )
        self.empty_notif_lbl.pack(pady=40)

    def add_notification_card(self, notif: Dict[str, Any]):
        if self.empty_notif_lbl.winfo_exists():
            self.empty_notif_lbl.pack_forget()

        card = ctk.CTkFrame(self.notif_scroll, corner_radius=10, fg_color="#1C1C1E")
        card.pack(fill="x", padx=10, pady=6)

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=12, pady=(10, 2))

        app_lbl = ctk.CTkLabel(
            top_row,
            text=f"📱  {notif.get('app', 'iPhone')}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#0A84FF"
        )
        app_lbl.pack(side="left")

        time_lbl = ctk.CTkLabel(
            top_row,
            text=notif.get("time", "Just now"),
            font=ctk.CTkFont(size=11),
            text_color="#8E8E93"
        )
        time_lbl.pack(side="right")

        title_lbl = ctk.CTkLabel(
            card,
            text=notif.get("title", ""),
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        title_lbl.pack(fill="x", padx=12, pady=(2, 2))

        if notif.get("message"):
            msg_lbl = ctk.CTkLabel(
                card,
                text=notif.get("message", ""),
                font=ctk.CTkFont(size=13),
                text_color="#EBEBF5",
                wraplength=600,
                justify="left",
                anchor="w"
            )
            msg_lbl.pack(fill="x", padx=12, pady=(0, 10))

    def clear_notifications(self):
        for widget in self.notif_scroll.winfo_children():
            widget.destroy()
        self.empty_notif_lbl = ctk.CTkLabel(
            self.notif_scroll,
            text="No notifications received yet.",
            font=ctk.CTkFont(size=13),
            text_color="#8E8E93"
        )
        self.empty_notif_lbl.pack(pady=40)

    # --- TAB 4: AIRDROP FILES ---
    def _build_airdrop_tab(self):
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.tab_frames["airdrop"] = frame
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        # Header
        top_box = ctk.CTkFrame(frame, corner_radius=14, fg_color="#242426")
        top_box.grid(row=0, column=0, sticky="ew", pady=(0, 16))

        t_lbl = ctk.CTkLabel(top_box, text="AirDrop — High Speed File Transfer", font=ctk.CTkFont(size=18, weight="bold"))
        t_lbl.pack(anchor="w", padx=20, pady=(16, 4))

        sub_lbl = ctk.CTkLabel(
            top_box,
            text=f"Files sent from iPhone are saved to: {self.file_manager.download_dir}",
            font=ctk.CTkFont(size=13),
            text_color="#8E8E93"
        )
        sub_lbl.pack(anchor="w", padx=20, pady=(0, 14))

        action_row = ctk.CTkFrame(top_box, fg_color="transparent")
        action_row.pack(anchor="w", padx=20, pady=(0, 10))

        btn_send = ctk.CTkButton(
            action_row,
            text="📤  Send Files to iPhone",
            font=ctk.CTkFont(weight="bold"),
            command=self.select_files_to_send
        )
        btn_send.pack(side="left", padx=(0, 10))

        btn_folder = ctk.CTkButton(
            action_row,
            text="📂  Open Downloads Folder",
            fg_color="#2C2C2E",
            command=self.open_downloads_folder
        )
        btn_folder.pack(side="left")

        # Status text for file transfer
        self.transfer_feedback_lbl = ctk.CTkLabel(
            top_box,
            text="💡 Tip: Open the AirContinuity companion web page in iPhone Safari to drop and receive files.",
            font=ctk.CTkFont(size=12),
            text_color="#8E8E93"
        )
        self.transfer_feedback_lbl.pack(anchor="w", padx=20, pady=(0, 14))

        # Transfer List
        list_header = ctk.CTkLabel(frame, text="Recent Transfers", font=ctk.CTkFont(size=15, weight="bold"))
        list_header.grid(row=1, column=0, sticky="w", pady=(0, 8))

        self.transfer_scroll = ctk.CTkScrollableFrame(frame, corner_radius=14, fg_color="#242426")
        self.transfer_scroll.grid(row=2, column=0, sticky="nsew")

        self.empty_transfers_lbl = ctk.CTkLabel(
            self.transfer_scroll,
            text="No files transferred yet.",
            font=ctk.CTkFont(size=13),
            text_color="#8E8E93"
        )
        self.empty_transfers_lbl.pack(pady=40)

    def select_files_to_send(self):
        paths = filedialog.askopenfilenames(title="Select files to share with iPhone")
        if not paths:
            return
        
        is_client_connected = len(self.mirror_server.active_sockets) > 0
        for p in paths:
            record = self.file_manager.queue_outgoing_file(p)
            if record:
                self.add_transfer_card(record)
                self.mirror_server.broadcast({
                    "type": "file_ready",
                    "id": record["id"],
                    "name": record["name"],
                    "size": record["size"]
                })

        if hasattr(self, "transfer_feedback_lbl"):
            if is_client_connected:
                self.transfer_feedback_lbl.configure(
                    text="✅ File(s) sent! A download banner & chime have been sent to iPhone Safari.",
                    text_color="#30D158"
                )
            else:
                self.transfer_feedback_lbl.configure(
                    text="⚠️ iPhone Safari is not connected! Scan QR code in 'Overview & Pair' to open and receive.",
                    text_color="#FF9F0A"
                )

    def add_transfer_card(self, item: Dict):
        if self.empty_transfers_lbl.winfo_exists():
            self.empty_transfers_lbl.pack_forget()

        # Play chime on incoming file received from iPhone
        if item.get("direction") == "incoming":
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

        card = ctk.CTkFrame(self.transfer_scroll, corner_radius=10, fg_color="#1C1C1E")
        card.pack(fill="x", padx=10, pady=5)

        icon = "📥" if item.get("direction") == "incoming" else "📤"
        icon_lbl = ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=18))
        icon_lbl.pack(side="left", padx=14, pady=10)

        info_box = ctk.CTkFrame(card, fg_color="transparent")
        info_box.pack(side="left", fill="both", expand=True, pady=8)

        name_lbl = ctk.CTkLabel(info_box, text=item.get("name", ""), font=ctk.CTkFont(size=13, weight="bold"), anchor="w")
        name_lbl.pack(fill="x")

        sub = f"{item.get('size')} • {item.get('time')} • {item.get('status')}"
        sub_lbl = ctk.CTkLabel(info_box, text=sub, font=ctk.CTkFont(size=11), text_color="#8E8E93", anchor="w")
        sub_lbl.pack(fill="x")

        if item.get("path") and os.path.exists(item.get("path")):
            btn_open = ctk.CTkButton(
                card,
                text="Open",
                width=65,
                height=28,
                fg_color="#2C2C2E",
                command=lambda p=item["path"]: os.startfile(p)
            )
            btn_open.pack(side="right", padx=12, pady=10)

    def open_downloads_folder(self):
        folder = self.file_manager.download_dir
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))

    # --- TAB 5: UNIVERSAL CLIPBOARD ---
    def _build_clipboard_tab(self):
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.tab_frames["clipboard"] = frame
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        # Top box
        top_box = ctk.CTkFrame(frame, corner_radius=14, fg_color="#242426")
        top_box.grid(row=0, column=0, sticky="ew", pady=(0, 16))

        t_lbl = ctk.CTkLabel(top_box, text="Universal Clipboard Sync", font=ctk.CTkFont(size=18, weight="bold"))
        t_lbl.pack(anchor="w", padx=20, pady=(16, 4))

        sub_lbl = ctk.CTkLabel(
            top_box,
            text="Copy on Windows, paste on iPhone instantly. Real-time bi-directional sync.",
            font=ctk.CTkFont(size=13),
            text_color="#8E8E93"
        )
        sub_lbl.pack(anchor="w", padx=20, pady=(0, 12))

        self.clip_preview = ctk.CTkEntry(
            top_box,
            placeholder_text="Current clipboard content...",
            height=40,
            corner_radius=8
        )
        self.clip_preview.pack(fill="x", padx=20, pady=(0, 16))

        # History
        hist_title = ctk.CTkLabel(frame, text="Clipboard History", font=ctk.CTkFont(size=15, weight="bold"))
        hist_title.grid(row=1, column=0, sticky="w", pady=(0, 8))

        self.clip_scroll = ctk.CTkScrollableFrame(frame, corner_radius=14, fg_color="#242426")
        self.clip_scroll.grid(row=2, column=0, sticky="nsew")

    def add_clipboard_card(self, text: str, source: str):
        card = ctk.CTkFrame(self.clip_scroll, corner_radius=10, fg_color="#1C1C1E")
        card.pack(fill="x", padx=10, pady=5)

        badge_color = "#0A84FF" if source == "iPhone" else "#30D158"
        src_lbl = ctk.CTkLabel(
            card,
            text=f"From {source}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=badge_color
        )
        src_lbl.pack(anchor="w", padx=12, pady=(8, 2))

        txt_lbl = ctk.CTkLabel(
            card,
            text=text[:180] + ("..." if len(text) > 180 else ""),
            font=ctk.CTkFont(size=13),
            text_color="#FFFFFF",
            wraplength=620,
            justify="left",
            anchor="w"
        )
        txt_lbl.pack(fill="x", padx=12, pady=(0, 8))

    # --- TAB 6: SETTINGS ---
    def _build_settings_tab(self):
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.tab_frames["settings"] = frame
        frame.grid_columnconfigure(0, weight=1)

        card = ctk.CTkScrollableFrame(frame, corner_radius=16, fg_color="#242426")
        card.pack(fill="both", expand=True)

        title = ctk.CTkLabel(card, text="System & Startup Settings", font=ctk.CTkFont(size=20, weight="bold"))
        title.pack(anchor="w", padx=24, pady=(24, 16))

        # Windows Startup Switch
        self.startup_switch = ctk.CTkSwitch(
            card,
            text="Start with Windows on Boot (Auto-launch as background service)",
            font=ctk.CTkFont(size=14, weight="normal"),
            command=self._on_toggle_startup
        )
        self.startup_switch.pack(anchor="w", padx=24, pady=12)
        if config.is_run_at_startup():
            self.startup_switch.select()

        # Minimize to tray switch
        self.tray_switch = ctk.CTkSwitch(
            card,
            text="Minimize to System Tray on Close (Keep running in background)",
            font=ctk.CTkFont(size=14, weight="normal"),
            command=self._on_toggle_tray
        )
        self.tray_switch.pack(anchor="w", padx=24, pady=12)
        if self.cfg.get("minimize_to_tray", True):
            self.tray_switch.select()

        # Download Directory
        sep = ctk.CTkFrame(card, height=1, fg_color="#3A3A3C")
        sep.pack(fill="x", padx=24, pady=20)

        dir_lbl = ctk.CTkLabel(card, text="AirDrop Downloads Directory:", font=ctk.CTkFont(size=14, weight="normal"))
        dir_lbl.pack(anchor="w", padx=24, pady=(0, 6))

        row_dir = ctk.CTkFrame(card, fg_color="transparent")
        row_dir.pack(anchor="w", padx=24, pady=(0, 20), fill="x")

        self.dir_entry = ctk.CTkEntry(row_dir, width=420)
        self.dir_entry.insert(0, str(self.file_manager.download_dir))
        self.dir_entry.pack(side="left", padx=(0, 10))

        btn_browse = ctk.CTkButton(row_dir, text="Browse...", width=90, command=self._browse_download_dir)
        btn_browse.pack(side="left")

        # --- PRIVACY POLICY & EDUCATIONAL DISCLAIMER SECTION ---
        sep2 = ctk.CTkFrame(card, height=1, fg_color="#3A3A3C")
        sep2.pack(fill="x", padx=24, pady=20)

        privacy_card = ctk.CTkFrame(card, corner_radius=12, fg_color="#1C1C1E", border_width=1, border_color="#2C2C2E")
        privacy_card.pack(fill="x", padx=24, pady=(0, 24))

        p_header = ctk.CTkFrame(privacy_card, fg_color="transparent")
        p_header.pack(fill="x", padx=16, pady=(14, 6))

        p_title = ctk.CTkLabel(
            p_header,
            text="🛡️  Privacy Policy & Educational Disclaimer",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#30D158"
        )
        p_title.pack(side="left")

        p_summary = (
            "• 🎓 Educational & Research Purpose: Developed solely for educational demonstrations of open Continuity protocols.\n"
            "• 🚫 No App Monitoring: AirContinuity does NOT monitor, inspect, log, or track your installed apps or activities.\n"
            "• 🔒 100% Local Peer-to-Peer: All communications (AirDrop, AirPlay, BLE, Clipboard) stay strictly on your local Wi-Fi / Bluetooth.\n"
            "• ☁️ Zero Cloud Servers / Zero Telemetry: No files, messages, or keystrokes are ever sent to remote servers or third parties."
        )
        p_lbl = ctk.CTkLabel(
            privacy_card,
            text=p_summary,
            font=ctk.CTkFont(size=12),
            text_color="#A1A1A6",
            justify="left"
        )
        p_lbl.pack(anchor="w", padx=16, pady=(0, 12))

        btn_view_policy = ctk.CTkButton(
            privacy_card,
            text="📜  View Full Privacy Policy",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=34,
            width=200,
            fg_color="#2C2C2E",
            hover_color="#3A3A3C",
            command=self._show_privacy_policy_dialog
        )
        btn_view_policy.pack(anchor="w", padx=16, pady=(0, 14))

    def _show_privacy_policy_dialog(self):
        """Display the complete Privacy Policy modal dialog."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("AirContinuity — Privacy Policy & Educational Disclaimer")
        dialog.geometry("640x520")
        dialog.minsize(500, 400)
        dialog.attributes("-topmost", True)

        scroll = ctk.CTkScrollableFrame(dialog, fg_color="#1C1C1E", corner_radius=12)
        scroll.pack(fill="both", expand=True, padx=16, pady=16)

        title = ctk.CTkLabel(
            scroll,
            text="Privacy Policy & Educational Disclaimer",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#FFFFFF"
        )
        title.pack(anchor="w", padx=12, pady=(10, 8))

        policy_text = (
            "1. Educational & Research Purpose\n"
            "AirContinuity is developed strictly for educational, academic research, and personal device "
            "interoperability purposes. It demonstrates reverse-engineered implementations of open protocols "
            "(Apple Wireless Direct Link / mDNS, Apple Notification Center Service over Bluetooth LE GATT, "
            "AirPlay RTSP receiver specifications, and standard Human Interface Device over GATT / HOGP).\n\n"
            "This software is not affiliated with, endorsed by, or sponsored by Apple Inc. or Microsoft Corporation.\n\n"
            "2. Zero App Monitoring or Surveillance\n"
            "• AirContinuity does NOT monitor, scan, log, or track your installed applications, open windows, process lists, or desktop activities.\n"
            "• The Bluetooth LE HID input controller only redirects hardware keyboard and mouse events when you explicitly activate 'Capture Input'. It never logs, captures, or saves keystrokes.\n"
            "• Screen mirroring displays an incoming video feed from your authorized iPhone locally on your display; it never records, snapshots, or uploads your screen.\n\n"
            "3. 100% Local Peer-to-Peer Communication\n"
            "• All data (AirDrop file transfers, universal clipboard sync, screen mirroring, incoming call alerts, and notifications) "
            "is transmitted exclusively between your Windows PC and iPhone over your local Wi-Fi and Bluetooth LE links.\n"
            "• There are NO external cloud servers, relay proxies, analytics SDKs, telemetry, or third-party trackers.\n\n"
            "4. User Consent\n"
            "By using AirContinuity, you acknowledge that this software is provided for personal educational interoperability purposes on an 'AS IS' basis."
        )

        content = ctk.CTkLabel(
            scroll,
            text=policy_text,
            font=ctk.CTkFont(size=12),
            text_color="#D1D1D6",
            justify="left",
            wraplength=560
        )
        content.pack(anchor="w", padx=12, pady=(0, 16))

        btn_close = ctk.CTkButton(dialog, text="Close", width=100, height=32, command=dialog.destroy)
        btn_close.pack(pady=(0, 12))

    def _on_toggle_startup(self):
        enabled = bool(self.startup_switch.get())
        config.set_run_at_startup(enabled)
        self.cfg["start_on_boot"] = enabled
        config.save_config(self.cfg)

    def _on_toggle_tray(self):
        self.cfg["minimize_to_tray"] = bool(self.tray_switch.get())
        config.save_config(self.cfg)

    def _browse_download_dir(self):
        new_dir = filedialog.askdirectory(initialdir=str(self.file_manager.download_dir))
        if new_dir:
            self.file_manager.set_download_dir(new_dir)
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, new_dir)
            self.cfg["download_dir"] = new_dir
            config.save_config(self.cfg)

    # --- REAL-TIME EVENT HANDLERS ---
    def _on_ancs_notification(self, notif: Dict[str, Any]):
        self.after(0, lambda: self._handle_notif_gui(notif))

    def _handle_notif_gui(self, notif: Dict[str, Any]):
        self.add_notification_card(notif)

    def _on_incoming_call(self, call_info: Dict[str, Any]):
        self.active_call_uid = call_info.get("uid")
        self.after(0, lambda: self._show_call_banner(call_info))

    def _show_call_banner(self, call_info: Dict[str, Any]):
        caller = call_info.get("caller", "iPhone Call")
        self.call_caller_label.configure(text=f"Caller: {caller}")
        self.call_banner.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 0))

    def _on_answer_call_clicked(self):
        if self.active_call_uid is not None:
            self.ancs_client.perform_action(self.active_call_uid, "positive")
        self.call_banner.grid_forget()

    def _on_decline_call_clicked(self):
        if self.active_call_uid is not None:
            self.ancs_client.perform_action(self.active_call_uid, "negative")
        self.call_banner.grid_forget()

    def _on_ancs_status(self, msg: str):
        self.after(0, lambda: self.ble_dot.configure(text=f"● {msg[:28]}"))

    def _on_clipboard_change(self, text: str, source: str):
        self.after(0, lambda: self._update_clip_gui(text, source))

    def _update_clip_gui(self, text: str, source: str):
        self.clip_preview.delete(0, "end")
        self.clip_preview.insert(0, text[:100])
        self.add_clipboard_card(text, source)

    def _on_file_transfer(self, record: Dict):
        self.after(0, lambda: self.add_transfer_card(record))

    def _on_client_connected(self, count: int):
        status_txt = f"Connected ({count})" if count > 0 else "Ready to Pair"
        self.after(0, lambda: self.ip_info_label.configure(text=f"iPhone: {status_txt}"))

    def _on_mirror_state_changed(self, active: bool):
        """Called when AirPlay receiver reports a state change."""
        if active:
            badge_text = "🟢 iPhone Connected — Screen Mirroring Active"
            color = "#30D158"
        else:
            if self.airplay_receiver and self.airplay_receiver.is_running:
                badge_text = "🟡 AirPlay Receiver Running — Waiting for iPhone"
                color = "#FFD60A"
            else:
                badge_text = "⚪ AirPlay Receiver: Not Started"
                color = "#8E8E93"
        self.after(0, lambda: self.mirror_state_badge.configure(text=badge_text, text_color=color))

    # System Tray & Window management
    def on_close_requested(self):
        if self.cfg.get("minimize_to_tray", True):
            self.withdraw()
        else:
            self.destroy()

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()
