# AirContinuity — Apple Continuity & AirDrop Bridge for Windows

An all-in-one Windows bridge that brings Apple's ecosystem features—**AirDrop file transfers, iPhone screen mirroring, push notifications, incoming call management, and universal clipboard sync**—to Windows laptops and PCs.

Packaged as a standalone Windows executable (`AirContinuity.exe`) with native Windows startup and System Tray integration.

---

## 🔬 Reverse Engineering Breakdown: How Apple Ecosystem Protocols Work

| Feature | Apple Native Protocol (Mac <-> iPhone) | AirContinuity Reverse-Engineered Implementation on Windows |
| :--- | :--- | :--- |
| **AirDrop File Transfer** | **AWDL (Apple Wireless Direct Link)** frame exchange over Wi-Fi channels 6/44/149 + TLS client certificates + HTTP POST. | Standard Windows Wi-Fi cards cannot craft raw AWDL action frames. AirContinuity announces local mDNS/Bonjour services and serves a zero-install high-speed local Wi-Fi transfer portal with drag-and-drop. |
| **Notifications** | **ANCS (Apple Notification Center Service)** over Bluetooth LE GATT (UUID `7905F431-B5CE-4E99-A40F-4B1E122D00D0`). | **100% Native:** Subscribes to the official ANCS GATT characteristics on Windows using WinRT BLE, parsing notifications for iMessage, WhatsApp, Mail, and apps. |
| **Phone Calls** | Continuity FaceTime relay + **Bluetooth HFP 1.7 (Hands-Free Profile)**. | Intercepts ANCS Category ID `0x01` (Incoming Call), alerts user with Caller ID, and sends `ActionIDPositive` (0x00 = Answer) or `ActionIDNegative` (0x01 = Decline) directly to the phone. |
| **Screen Mirroring** | **AirPlay RTSP stream + FairPlay DRM** + RemoteXPC encrypted touch channel. | Advertises Bonjour AirPlay receiver (`_airplay._tcp`) + real-time WebRTC 60 FPS screen broadcast with responsive viewport and click relay. |
| **Universal Clipboard** | Proximity BLE advertisement + local APNs/CloudKit sync. | Bi-directional real-time clipboard sync: polls Windows clipboard (`win32clipboard`) and connects via WebSockets and REST endpoint (`/api/clipboard`) for iOS Shortcuts. |
| **Startup on Boot** | macOS launchd daemon (`com.apple.rapportd`). | Windows Registry integration (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`) with background System Tray minimization. |

---

## 🚀 Features

1. **📱 Zero-Install Pairing:**
   - Launch AirContinuity on Windows.
   - Scan the on-screen QR code with your iPhone Camera to open the companion web portal in Safari.
2. **🖥️ iPhone Screen Mirroring:**
   - Tap "Start Screen Mirror" on the iPhone to stream your display to your Windows PC at 60 FPS with hardware-accelerated playback.
3. **🔔 Live iPhone Notifications:**
   - Native notifications for calls, messages, social media, and apps directly on your Windows desktop.
4. **📞 Answer & Decline Phone Calls:**
   - An incoming call banner pops up showing caller ID with one-click **Answer** and **Decline** buttons.
5. **📁 AirDrop-Style Transfers:**
   - Drag and drop files from Windows to send to your iPhone.
   - Upload photos, videos, and documents from iPhone directly into your Windows `Downloads/AirContinuity` folder.
6. **📋 Universal Clipboard:**
   - Copy text on Windows -> available on iPhone.
   - Copy text on iPhone -> immediately active in Windows clipboard.
7. **⚙️ Windows Startup & Tray:**
   - Toggling "Start with Windows" enables automatic boot launch.
   - Minimizes to the Windows System Tray (near the clock) so it never gets in your way.

---

## 🛠️ Architecture & File Structure

```
airdrop for windows/
├── app/
│   ├── config.py             # Config & Windows Startup registry manager (HKCU\Run)
│   ├── ancs_service.py       # Bluetooth LE ANCS client for notifications & call control
│   ├── airplay_bonjour.py    # Bonjour mDNS service advertiser
│   ├── mirror_server.py      # HTTP, WebSocket & WebRTC screen mirror relay
│   ├── file_transfer.py      # High-speed local file manager
│   ├── clipboard_sync.py     # Universal clipboard listener & sync engine
│   ├── ui/
│   │   ├── main_window.py    # CustomTkinter modern desktop GUI
│   │   ├── tray.py           # System Tray handler (pystray)
│   │   └── assets/           # App icons (.png and .ico)
│   └── web/                  # iOS Companion Web Portal
│       ├── index.html        # Glassmorphic Apple-style web interface
│       ├── style.css         # Dark mode iOS design system
│       ├── app.js            # WebRTC screen capture, upload & clipboard logic
│       └── mirror.html       # Windows-side WebRTC screen viewer
├── run.py                    # Application entry point
├── build.py                  # Standalone .exe and Installer compiler
├── installer.py              # Modern GUI Windows Setup wizard (Windows 10 & 11)
├── AirContinuity.exe         # Ready-to-run standalone application
├── AirContinuity-Setup.exe   # Standalone all-in-one Windows installer
├── PRIVACY_POLICY.md         # Educational disclaimer & privacy commitments
└── release/
    ├── AirContinuity.exe     # Standalone application
    ├── AirContinuity-Setup.exe # All-in-one Windows installer
    ├── blehid/               # Bundled Bluetooth LE HID engine
    └── uxplay/               # Bundled AirPlay mirroring engine
```

---

## 🏃 Running the Application

### Option 1: Direct Run from Main Directory (Zero-Install)
Double-click `AirContinuity.exe` in the main folder.

### Option 2: Run via Python Source
```powershell
python run.py
```

---

## 📦 Windows 10 & 11 Installer (`AirContinuity-Setup.exe`)

A standalone graphical installer is provided at:
`AirContinuity-Setup.exe`

- **Installs anywhere:** Installs to `%LOCALAPPDATA%\Programs\AirContinuity` (or any custom folder chosen by the user) without needing admin privileges.
- **Includes everything:** Bundles `AirContinuity.exe`, `blehid` (Bluetooth LE HID), `uxplay` (AirPlay receiver), and `PRIVACY_POLICY.md`.
- **Desktop & Start Menu Shortcuts:** Creates clean Windows shortcuts for easy launch.
- **Windows Integration:** Registers in Windows Add/Remove Programs (Installed Apps) for clean 1-click uninstallation.

---

## 🛡️ Privacy Policy & Educational Disclaimer

This software is developed **strictly for educational, academic research, and personal device interoperability purposes**.

- **Zero App Monitoring:** AirContinuity **does not** monitor, scan, inspect, or log your installed applications, open windows, process lists, or desktop activities.
- **No Background Keylogging:** Keystrokes and mouse movements are only routed when you explicitly activate **"Capture Input"**, transmitting directly to your paired iPhone over Bluetooth LE HOGP.
- **100% Local Peer-to-Peer:** All communications (AirDrop transfers, AirPlay mirroring, universal clipboard sync, push notifications) operate strictly over your local Wi-Fi and direct Bluetooth LE links. There are **no cloud servers, telemetry, or remote tracking**.
- For full details, see [PRIVACY_POLICY.md](PRIVACY_POLICY.md) or click **View Full Privacy Policy** inside the app's **Settings** tab.
