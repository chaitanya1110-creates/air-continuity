"""
AirDrop-style file transfer manager for Windows.
Handles incoming uploads from iPhone and outgoing files ready for iPhone to pick up.
"""
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Callable, Optional

class FileTransferManager:
    def __init__(self, download_dir: str, on_transfer: Optional[Callable[[Dict], None]] = None):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.on_transfer = on_transfer
        self.transfers: List[Dict] = []
        self.outgoing_files: Dict[str, Path] = {}

    def set_download_dir(self, new_dir: str):
        self.download_dir = Path(new_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def save_incoming_file(self, filename: str, file_bytes: bytes) -> str:
        """Save a file sent from iPhone to the local download folder."""
        # Clean filename
        safe_name = Path(filename).name
        target_path = self.download_dir / safe_name
        
        # Avoid overwrite by numbering
        counter = 1
        base = target_path.stem
        suffix = target_path.suffix
        while target_path.exists():
            target_path = self.download_dir / f"{base}_{counter}{suffix}"
            counter += 1

        with open(target_path, "wb") as f:
            f.write(file_bytes)

        size_kb = len(file_bytes) / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"

        record = {
            "name": target_path.name,
            "path": str(target_path),
            "size": size_str,
            "direction": "incoming",
            "time": datetime.now().strftime("%H:%M:%S"),
            "status": "Completed"
        }
        self.transfers.insert(0, record)
        if len(self.transfers) > 50:
            self.transfers.pop()

        if self.on_transfer:
            self.on_transfer(record)

        return str(target_path)

    def queue_outgoing_file(self, file_path: str) -> Optional[Dict]:
        """Add a PC file to the queue for the iPhone to download."""
        src = Path(file_path)
        if not src.exists():
            return None

        file_id = f"out_{int(datetime.now().timestamp())}_{src.name}"
        self.outgoing_files[file_id] = src

        size_kb = src.stat().st_size / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"

        record = {
            "id": file_id,
            "name": src.name,
            "path": str(src),
            "size": size_str,
            "direction": "outgoing",
            "time": datetime.now().strftime("%H:%M:%S"),
            "status": "Ready for iPhone"
        }
        self.transfers.insert(0, record)
        return record

    def get_outgoing_file(self, file_id: str) -> Optional[Path]:
        return self.outgoing_files.get(file_id)

    def list_outgoing_manifest(self) -> List[Dict]:
        result = []
        for fid, path in list(self.outgoing_files.items()):
            if path.exists():
                size_kb = path.stat().st_size / 1024
                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"
                result.append({
                    "id": fid,
                    "name": path.name,
                    "size": size_str
                })
        return result
