"""
Apple Notification Center Service (ANCS) client for Windows over Bluetooth LE.
Captures iPhone notifications (iMessage, WhatsApp, incoming calls) and allows
answering/rejecting phone calls directly from Windows.
"""
import asyncio
import struct
import threading
from typing import Callable, Optional, Dict, Any
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

# Official Apple ANCS UUIDs
ANCS_SERVICE_UUID = "7905f431-b5ce-4e99-a40f-4b1e122d00d0"
NOTIFICATION_SOURCE_UUID = "9fbf120d-6301-42d9-8c58-25e699a21dbd"
CONTROL_POINT_UUID = "69d1d8f3-45e1-49a8-9821-9bbdfdaad9d9"
DATA_SOURCE_UUID = "22eac6e9-24d6-4bb5-be44-b36ace7c7bfb"

# Category IDs
CATEGORY_NAMES = {
    0: "Other",
    1: "Incoming Call",
    2: "Missed Call",
    3: "Voicemail",
    4: "Social",
    5: "Schedule",
    6: "Email",
    7: "News",
    8: "Health",
    9: "Business",
    10: "Location",
    11: "Entertainment"
}

EVENT_NAMES = {
    0: "Added",
    1: "Modified",
    2: "Removed"
}

class ANCSClient:
    def __init__(self,
                 on_notification: Optional[Callable[[Dict[str, Any]], None]] = None,
                 on_call: Optional[Callable[[Dict[str, Any]], None]] = None,
                 on_status: Optional[Callable[[str], None]] = None):
        self.on_notification = on_notification
        self.on_call = on_call
        self.on_status = on_status

        self.client: Optional[BleakClient] = None
        self.connected_device: Optional[BLEDevice] = None
        self.is_running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        # Buffering data source chunks
        self._data_buffer = bytearray()
        self._pending_uids = {}

    def start(self):
        """Start the background BLE scanning and ANCS listener."""
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.is_running = False
        if self._loop and self.client and self.client.is_connected:
            asyncio.run_coroutine_threadsafe(self.client.disconnect(), self._loop)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main_worker())

    async def _main_worker(self):
        self._update_status("Searching for paired iPhone (Bluetooth LE)...")
        while self.is_running:
            try:
                # Scan for nearby devices advertising ANCS or Apple Continuity
                devices = await BleakScanner.discover(timeout=5.0)
                target_device = None

                for d in devices:
                    # Check if device has iPhone name or ANCS service in metadata
                    name = d.name or ""
                    uuids = d.metadata.get("uuids", [])
                    if "iPhone" in name or ANCS_SERVICE_UUID.lower() in [u.lower() for u in uuids]:
                        target_device = d
                        break

                if target_device:
                    self._update_status(f"Found iPhone: {target_device.name or target_device.address}. Connecting...")
                    success = await self._connect_and_listen(target_device)
                    if not success:
                        await asyncio.sleep(4.0)
                else:
                    self._update_status("Scanning for iPhone... (Ensure Bluetooth is On)")
                    await asyncio.sleep(3.0)

            except Exception as e:
                self._update_status(f"Bluetooth BLE loop notice: {e}")
                await asyncio.sleep(4.0)

    async def _connect_and_listen(self, device: BLEDevice) -> bool:
        try:
            async with BleakClient(device) as client:
                self.client = client
                self.connected_device = device
                self._update_status(f"Connected to {device.name or 'iPhone'} (BLE)")

                # Verify ANCS service presence
                ancs_service = None
                for service in client.services:
                    if service.uuid.lower() == ANCS_SERVICE_UUID.lower():
                        ancs_service = service
                        break

                if not ancs_service:
                    self._update_status("Device connected, but ANCS GATT is pairing-restricted. Requesting notifications permission...")
                    # Even if not yet bonded, subscribing can trigger iOS system pairing prompt
                
                # Subscribe to Notification Source
                try:
                    await client.start_notify(NOTIFICATION_SOURCE_UUID, self._on_notification_source)
                    await client.start_notify(DATA_SOURCE_UUID, self._on_data_source)
                    self._update_status(f"Active: Listening for Notifications & Calls from {device.name or 'iPhone'}")
                except Exception as ex:
                    self._update_status(f"Pairing needed: Please pair iPhone with PC in Windows Bluetooth settings ({ex})")
                    return False

                # Keep connected while running
                while self.is_running and client.is_connected:
                    await asyncio.sleep(1.0)

                return True
        except Exception as e:
            self._update_status(f"BLE connection lost: {e}")
            return False
        finally:
            self.client = None

    def _update_status(self, msg: str):
        if self.on_status:
            self.on_status(msg)

    def _on_notification_source(self, sender: int, data: bytearray):
        """
        Notification Source format (8 bytes):
        [0]: EventID (0: Added, 1: Modified, 2: Removed)
        [1]: EventFlags
        [2]: CategoryID
        [3]: CategoryCount
        [4..7]: NotificationUID (uint32 little endian)
        """
        if len(data) < 8:
            return

        event_id, event_flags, category_id, category_count, uid = struct.unpack("<BBBB I", data[:8])
        category_name = CATEGORY_NAMES.get(category_id, f"Category {category_id}")
        event_name = EVENT_NAMES.get(event_id, f"Event {event_id}")

        info = {
            "uid": uid,
            "event_id": event_id,
            "event_name": event_name,
            "category_id": category_id,
            "category_name": category_name,
            "is_call": (category_id == 1)
        }

        # If it's an incoming call, alert immediately
        if category_id == 1 and event_id == 0:
            if self.on_call:
                self.on_call(info)

        # Request full notification details (App ID, Title, Message) via Control Point
        if self._loop and self.client and self.client.is_connected and event_id != 2:
            asyncio.run_coroutine_threadsafe(self._request_attributes(uid), self._loop)
        elif event_id == 2:
            # Notification removed
            if self.on_notification:
                self.on_notification(info)

    async def _request_attributes(self, uid: int):
        """
        Send CommandID 0 (Get Notification Attributes) to Control Point.
        Requests: AppIdentifier (0), Title (1), Subtitle (2), Message (3).
        """
        if not self.client:
            return
        try:
            # Build command buffer
            # 0: CommandID (0x00)
            # 1..4: UID
            # 5: AttrID 0 (AppIdentifier)
            # 6: AttrID 1 (Title) + max_len (uint16)
            # 9: AttrID 3 (Message) + max_len (uint16)
            req = struct.pack("<BI B BH BH", 0, uid, 0, 1, 64, 3, 256)
            await self.client.write_gatt_char(CONTROL_POINT_UUID, req, response=True)
        except Exception as e:
            print(f"Error querying notification attributes: {e}")

    def _on_data_source(self, sender: int, data: bytearray):
        """
        Data Source streams attribute responses for the requested UID.
        Format:
        [0]: CommandID (0)
        [1..4]: NotificationUID
        Followed by sequence of: [AttrID (1 byte)][AttrLen (2 bytes)][Value bytes]
        """
        self._data_buffer.extend(data)
        if len(self._data_buffer) < 5:
            return

        cmd_id, uid = struct.unpack("<BI", self._data_buffer[:5])
        offset = 5
        attrs = {}

        try:
            while offset + 3 <= len(self._data_buffer):
                attr_id = self._data_buffer[offset]
                attr_len = struct.unpack("<H", self._data_buffer[offset+1:offset+3])[0]
                offset += 3
                if offset + attr_len > len(self._data_buffer):
                    # Incomplete chunk, wait for next notify packet
                    return
                val_bytes = self._data_buffer[offset:offset+attr_len]
                offset += attr_len
                attrs[attr_id] = val_bytes.decode("utf-8", errors="replace")

            # Finished parsing attributes
            self._data_buffer.clear()
            app_id = attrs.get(0, "Apple Device")
            title = attrs.get(1, "Notification")
            message = attrs.get(3, "")

            notif_data = {
                "uid": uid,
                "app": app_id,
                "title": title,
                "message": message,
                "category": "iPhone",
                "time": "Just now"
            }

            if self.on_notification:
                self.on_notification(notif_data)

        except Exception as e:
            # If parsing fails or truncated, clear buffer
            self._data_buffer.clear()

    def perform_action(self, uid: int, action: str):
        """
        Answer or Decline call / notification.
        action: 'positive' (answer, 0) or 'negative' (decline, 1)
        """
        if not self._loop or not self.client or not self.client.is_connected:
            return
        action_id = 0 if action == "positive" else 1
        cmd = struct.pack("<BIB", 2, uid, action_id)
        asyncio.run_coroutine_threadsafe(
            self.client.write_gatt_char(CONTROL_POINT_UUID, cmd, response=True),
            self._loop
        )
