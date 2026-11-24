# Privacy Policy & Educational Disclaimer

**Last Updated:** November 2026  
**Application:** AirContinuity (Apple Ecosystem Bridge for Windows)

---

## 🎓 1. Educational & Research Purpose
AirContinuity is developed strictly for **educational, academic research, and personal device interoperability** purposes. It demonstrates reverse-engineered implementations of open protocols (such as Apple Wireless Direct Link / mDNS Bonjour, Apple Notification Center Service over Bluetooth LE GATT, AirPlay RTSP/FairPlay receiver specifications, and standard Human Interface Device over GATT / HOGP).

This software is **not** affiliated with, endorsed by, or sponsored by Apple Inc. or Microsoft Corporation. All Apple trademarks (AirDrop, AirPlay, iOS, iPhone, macOS) and Microsoft trademarks (Windows) belong to their respective owners.

---

## 🛡️ 2. No App Monitoring or Snooping
- **Zero App Monitoring:** AirContinuity **does not** monitor, scan, log, or track your installed applications, open windows, process lists, or active desktop activities.
- **Zero Background Keylogging:** The Bluetooth LE HID input controller only redirects keyboard and mouse hardware events when the user explicitly triggers **"Capture Input"** (or command mode), sending standard HID reports solely to the user's paired iPhone. It never logs, captures, or saves keystrokes to disk or memory.
- **Zero Screen Recording / Surveillance:** Screen mirroring features (AirPlay / WebRTC) display an incoming video feed from your own authorized iPhone locally onto your PC display. The app never records, snapshots, or uploads your screen content.

---

## 🔒 3. Direct Peer-to-Peer (Local Network Only)
- **100% Local Communication:** All communications—including file transfers, universal clipboard synchronization, screen mirroring, incoming call alerts, and Bluetooth LE notifications—occur directly and exclusively between your Windows PC and your iPhone over your local Wi-Fi network and direct Bluetooth LE links.
- **No Cloud Servers or Intermediaries:** There are no backend cloud servers, tracking relays, or third-party proxies. No data ever passes through or resides on external servers.
- **No Analytics or Telemetry:** AirContinuity contains zero telemetry, zero analytics SDKs, zero user tracking, and zero advertising trackers.

---

## 📋 4. Data Handling Summary

| Feature | Data Handled | Storage & Transmission |
| :--- | :--- | :--- |
| **AirDrop Transfers** | Files selected by user | Saved directly to user's local `Downloads/AirContinuity` folder. Never sent outside local Wi-Fi. |
| **Notifications & Calls** | Apple ANCS alerts | Read ephemeral from iPhone over BLE; stored in local UI RAM session only. Cleared on close. |
| **Universal Clipboard** | Copied text | Synchronized locally between PC and iPhone over local Wi-Fi. Never stored or logged remotely. |
| **Keyboard & Mouse Control** | HID reports | Dispatched in real time via standard Bluetooth LE HOGP to iPhone. Never logged. |
| **Screen Mirroring** | H.264 video stream | Decoded and rendered directly to desktop window. Never recorded. |

---

## ⚖️ 5. User Consent & Acceptance
By using or installing AirContinuity, you acknowledge and agree that this software is provided for personal educational interoperability purposes only, on an "AS IS" basis without warranties of any kind.

