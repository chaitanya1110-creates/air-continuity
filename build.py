"""
Complete Build & Installer Packaging Pipeline for AirContinuity.
Compiles:
1. AirContinuity.exe (Standalone executable) -> placed in release/ and main directory
2. AirContinuity-Setup.exe (Standalone Windows 10/11 Installer) -> placed in release/ and main directory
Bundles:
- BleHid (Bluetooth LE HID Keyboard/Mouse controller)
- UxPlay (AirPlay Screen Mirroring Receiver)
- Privacy Policy & Educational Disclaimer
"""
import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

def build_app():
    print("=" * 60)
    print("STEP 1: Compiling AirContinuity Standalone Executable")
    print("=" * 60)

    release_dir = PROJECT_ROOT / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    icon_file = PROJECT_ROOT / "app" / "ui" / "assets" / "icon.ico"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "AirContinuity",
        "--icon", str(icon_file),
        "--distpath", str(release_dir),
        "--add-data", f"{PROJECT_ROOT / 'app' / 'web'};web",
        "--add-data", f"{PROJECT_ROOT / 'app' / 'ui' / 'assets'};app/ui/assets",
        "--hidden-import", "bleak",
        "--hidden-import", "bleak.backends.winrt",
        "--hidden-import", "zeroconf",
        "--hidden-import", "tornado",
        "--hidden-import", "tornado.web",
        "--hidden-import", "tornado.websocket",
        "--hidden-import", "win32clipboard",
        "--hidden-import", "PIL",
        "--hidden-import", "pystray",
        "--hidden-import", "qrcode",
        "--hidden-import", "customtkinter",
        "--hidden-import", "cryptography",
        "--hidden-import", "tornado.httpserver",
        str(PROJECT_ROOT / "run.py")
    ]

    print(f"Running PyInstaller for AirContinuity...")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"PyInstaller failed with code {result.returncode}")
        sys.exit(result.returncode)

    app_exe = release_dir / "AirContinuity.exe"
    main_exe = PROJECT_ROOT / "AirContinuity.exe"

    # Copy AirContinuity.exe to the main directory
    try:
        shutil.copy2(app_exe, main_exe)
        print(f"✓ Copied AirContinuity.exe to main directory: {main_exe}")
    except Exception as e:
        print(f"Notice copying to main directory: {e}")

    # Copy dependencies into release directory
    for folder in ["blehid", "uxplay"]:
        src = PROJECT_ROOT / folder
        dst = release_dir / folder
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"✓ Bundled {folder} to release folder")

    # Copy Privacy Policy
    shutil.copy2(PROJECT_ROOT / "PRIVACY_POLICY.md", release_dir / "PRIVACY_POLICY.md")

    return app_exe


def build_installer():
    print("\n" + "=" * 60)
    print("STEP 2: Packaging Self-Contained Installer (AirContinuity-Setup.exe)")
    print("=" * 60)

    release_dir = PROJECT_ROOT / "release"
    payload_zip = PROJECT_ROOT / "payload.zip"

    # Create payload zip archive containing app + blehid + uxplay + privacy policy
    print("Creating compressed payload archive (payload.zip)...")
    with zipfile.ZipFile(payload_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        app_exe = release_dir / "AirContinuity.exe"
        if app_exe.exists():
            zf.write(app_exe, "AirContinuity.exe")

        zf.write(PROJECT_ROOT / "PRIVACY_POLICY.md", "PRIVACY_POLICY.md")

        for folder in ["blehid", "uxplay"]:
            src_dir = PROJECT_ROOT / folder
            if src_dir.exists():
                for root, _, files in os.walk(src_dir):
                    for file in files:
                        p = Path(root) / file
                        arcname = p.relative_to(PROJECT_ROOT)
                        zf.write(p, str(arcname))

    print(f"✓ payload.zip created ({payload_zip.stat().st_size / (1024*1024):.2f} MB)")

    # Compile installer.py into AirContinuity-Setup.exe
    icon_file = PROJECT_ROOT / "app" / "ui" / "assets" / "icon.ico"
    installer_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "AirContinuity-Setup",
        "--icon", str(icon_file),
        "--distpath", str(release_dir),
        "--add-data", f"{payload_zip};.",
        "--add-data", f"{PROJECT_ROOT / 'app' / 'ui' / 'assets'};app/ui/assets",
        str(PROJECT_ROOT / "installer.py")
    ]

    print("Running PyInstaller for AirContinuity-Setup.exe...")
    result = subprocess.run(installer_cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"Installer build failed with code {result.returncode}")
        sys.exit(result.returncode)

    setup_exe = release_dir / "AirContinuity-Setup.exe"
    main_setup_exe = PROJECT_ROOT / "AirContinuity-Setup.exe"

    try:
        shutil.copy2(setup_exe, main_setup_exe)
        print(f"✓ Copied AirContinuity-Setup.exe to main directory: {main_setup_exe}")
    except Exception as e:
        print(f"Notice copying setup to main directory: {e}")

    # Cleanup temporary payload.zip
    if payload_zip.exists():
        try:
            os.remove(payload_zip)
        except Exception:
            pass

    print("\n" + "=" * 60)
    print("ALL BUILDS COMPLETED SUCCESSFULLY!")
    print(f"1. Main Directory Executable: {main_exe if 'main_exe' in locals() else (PROJECT_ROOT / 'AirContinuity.exe')}")
    print(f"2. Main Directory Installer:  {main_setup_exe}")
    print(f"3. Release Package Folder:    {release_dir}")
    print("=" * 60)


if __name__ == "__main__":
    build_app()
    build_installer()
