"""
AirContinuity — Main Entry Point.
Launches the background Apple ecosystem bridge services, System Tray handler,
and CustomTkinter desktop interface.
"""
import sys
import os

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import config
from app.ancs_service import ANCSClient
from app.clipboard_sync import ClipboardSync
from app.file_transfer import FileTransferManager
from app.mirror_server import MirrorServer
from app.airplay_bonjour import BonjourService
from app.airplay_receiver import AirPlayReceiver
from app.input_control import InputController
from app.ui.main_window import MainWindow
from app.ui.tray import SystemTrayApp

def main():
    # Check if launched on Windows boot
    is_startup = "--startup" in sys.argv or "--tray" in sys.argv

    # 1. Load settings
    cfg = config.load_config()

    # Sync startup registry key if needed
    if cfg.get("start_on_boot", True) and not config.is_run_at_startup():
        config.set_run_at_startup(True)

    # 2. Initialize Core Services
    file_manager = FileTransferManager(download_dir=cfg.get("download_dir"))
    clipboard_sync = ClipboardSync()
    mirror_server = MirrorServer(
        port=cfg.get("server_port", 8089),
        clipboard_sync=clipboard_sync,
        file_manager=file_manager
    )
    bonjour_service = BonjourService(port=cfg.get("server_port", 8089))
    airplay_receiver = AirPlayReceiver(
        server_name=f"AirContinuity-{bonjour_service.host_name}",
        fps=60
    )
    ancs_client = ANCSClient()
    input_controller = InputController()

    # 3. Start Background Daemons
    clipboard_sync.start()
    mirror_server.start()
    bonjour_service.start()
    ancs_client.start()
    input_controller.start()
    # AirPlay receiver is started lazily from the UI (user clicks Start)

    # 4. Create Desktop UI
    window = MainWindow(
        cfg=cfg,
        ancs_client=ancs_client,
        clipboard_sync=clipboard_sync,
        file_manager=file_manager,
        mirror_server=mirror_server,
        bonjour_service=bonjour_service,
        airplay_receiver=airplay_receiver,
        input_controller=input_controller
    )

    def on_app_exit():
        # Clean teardown
        try:
            input_controller.stop()
            airplay_receiver.stop()
            bonjour_service.stop()
            ancs_client.stop()
            clipboard_sync.stop()
            mirror_server.stop()
        except Exception:
            pass
        window.destroy()
        sys.exit(0)

    # 5. Initialize System Tray
    tray = SystemTrayApp(window, on_exit_callback=on_app_exit)
    tray.start()

    # 6. If started on boot, stay in tray, otherwise show window
    if is_startup:
        window.withdraw()
    else:
        window.show_window()

    try:
        window.mainloop()
    except KeyboardInterrupt:
        on_app_exit()

if __name__ == "__main__":
    main()
