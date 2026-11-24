"""
AirContinuity Core Server (HTTP, WebSocket & WebRTC Mirroring Signal).
Serves the iOS Companion Web Portal, handles real-time clipboard sync,
manages AirDrop-style file uploads/downloads, and relays WebRTC screen mirror streams.
"""
import os
import sys
import json
import socket
import asyncio
import threading
from pathlib import Path
from typing import Set, Dict, Any, Optional

import tornado.web
import tornado.websocket
import tornado.ioloop

from app.clipboard_sync import ClipboardSync
from app.file_transfer import FileTransferManager

def get_bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent

class StatusHandler(tornado.web.RequestHandler):
    def initialize(self, server):
        self.server = server

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with, content-type")
        self.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def options(self):
        self.set_status(204)
        self.finish()

    def get(self):
        self.write({
            "status": "online",
            "device": socket.gethostname(),
            "connected_clients": len(self.server.active_sockets),
            "screen_active": self.server.screen_active
        })

class ClipboardHandler(tornado.web.RequestHandler):
    def initialize(self, server):
        self.server = server

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with, content-type")
        self.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def options(self):
        self.set_status(204)
        self.finish()

    def get(self):
        text = self.server.clipboard_sync.get_windows_clipboard()
        self.write({"text": text})

    def post(self):
        try:
            body = tornado.escape.json_decode(self.request.body)
            text = body.get("text", "")
        except Exception:
            text = self.request.body.decode("utf-8", errors="replace")

        if text:
            self.server.clipboard_sync.set_windows_clipboard(text, source="iPhone")
            self.server.broadcast({
                "type": "clipboard_update",
                "text": text,
                "source": "iPhone"
            })
            self.write({"status": "success", "length": len(text)})
        else:
            self.set_status(400)
            self.write({"error": "Empty clipboard text"})

class UploadHandler(tornado.web.RequestHandler):
    def initialize(self, server):
        self.server = server

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with, content-type")
        self.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def options(self):
        self.set_status(204)
        self.finish()

    def post(self):
        saved_files = []
        # Support multipart form upload
        if self.request.files:
            for field, files in self.request.files.items():
                for f in files:
                    filename = f["filename"]
                    body = f["body"]
                    path = self.server.file_manager.save_incoming_file(filename, body)
                    saved_files.append(Path(path).name)
        else:
            # Raw binary body upload
            header_name = self.request.headers.get("X-Filename", "received_file.bin")
            path = self.server.file_manager.save_incoming_file(header_name, self.request.body)
            saved_files.append(Path(path).name)

        self.server.broadcast({
            "type": "file_received",
            "files": saved_files
        })
        self.write({"status": "success", "files": saved_files})

class FilesHandler(tornado.web.RequestHandler):
    def initialize(self, server):
        self.server = server

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self):
        manifest = self.server.file_manager.list_outgoing_manifest()
        self.write({"files": manifest})

class DownloadHandler(tornado.web.RequestHandler):
    def initialize(self, server):
        self.server = server

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")

    def get(self, file_id):
        file_path = self.server.file_manager.get_outgoing_file(file_id)
        if not file_path or not file_path.exists():
            self.set_status(404)
            self.write({"error": "File not found"})
            return

        self.set_header("Content-Type", "application/octet-stream")
        self.set_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                self.write(chunk)
        self.finish()

class WebSocketBridge(tornado.websocket.WebSocketHandler):
    def initialize(self, server):
        self.server = server

    def check_origin(self, origin):
        return True

    def open(self):
        self.server.active_sockets.add(self)
        # Notify current clipboard state
        current_clip = self.server.clipboard_sync.get_windows_clipboard()
        if current_clip:
            self.write_message(json.dumps({
                "type": "clipboard_update",
                "text": current_clip,
                "source": "PC"
            }))
        self.server.on_client_connection(len(self.server.active_sockets))

    def on_message(self, message):
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "clipboard_update":
                text = data.get("text", "")
                if text:
                    self.server.clipboard_sync.set_windows_clipboard(text, source="iPhone")
                    # Relay to all other sockets
                    self.server.broadcast(data, exclude=self)

            elif msg_type in ("webrtc_offer", "webrtc_answer", "webrtc_candidate"):
                # Forward WebRTC signaling for Screen Mirroring
                self.server.broadcast(data, exclude=self)
                if msg_type == "webrtc_offer":
                    self.server.screen_active = True
                    self.server.on_screen_mirror_state(True)

            elif msg_type == "screen_mirror_stop":
                self.server.screen_active = False
                self.server.on_screen_mirror_state(False)
                self.server.broadcast(data, exclude=self)

            elif msg_type == "remote_input":
                # Mouse / keyboard / touch event relay
                if self.server.on_remote_input_cb:
                    self.server.on_remote_input_cb(data)

            elif msg_type == "call_response":
                # Forward call response
                if self.server.on_call_response_cb:
                    self.server.on_call_response_cb(data.get("action"))

        except Exception as e:
            print(f"[WebSocket] Error processing message: {e}")

    def on_close(self):
        self.server.active_sockets.discard(self)
        self.server.on_client_connection(len(self.server.active_sockets))

import ssl
import tornado.httpserver
from app.cert_manager import ensure_ssl_certificates

class MirrorServer:
    def __init__(self, port: int, clipboard_sync: ClipboardSync, file_manager: FileTransferManager, https_port: int = 8443):
        self.port = port
        self.https_port = https_port
        self.clipboard_sync = clipboard_sync
        self.file_manager = file_manager
        self.active_sockets: Set[tornado.websocket.WebSocketHandler] = set()
        self.screen_active = False

        self.on_client_connect_cb = None
        self.on_screen_mirror_cb = None
        self.on_remote_input_cb = None
        self.on_call_response_cb = None

        self._thread: Optional[threading.Thread] = None
        self._ioloop: Optional[tornado.ioloop.IOLoop] = None
        self._http_server: Optional[tornado.httpserver.HTTPServer] = None
        self._https_server: Optional[tornado.httpserver.HTTPServer] = None

        # Wire clipboard sync notification to websocket broadcast
        self.clipboard_sync.on_change = self._handle_clipboard_change

    def _handle_clipboard_change(self, text: str, source: str):
        if source == "PC":
            self.broadcast({
                "type": "clipboard_update",
                "text": text,
                "source": "PC"
            })

    def start(self):
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

    def _run_server(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        web_root = get_bundle_dir() / "web"
        
        # Build Tornado routes
        handlers = [
            (r"/api/status", StatusHandler, dict(server=self)),
            (r"/api/clipboard", ClipboardHandler, dict(server=self)),
            (r"/api/upload", UploadHandler, dict(server=self)),
            (r"/api/files", FilesHandler, dict(server=self)),
            (r"/api/download/(.*)", DownloadHandler, dict(server=self)),
            (r"/ws", WebSocketBridge, dict(server=self)),
            (r"/(.*)", tornado.web.StaticFileHandler, {
                "path": str(web_root),
                "default_filename": "index.html"
            }),
        ]

        app = tornado.web.Application(handlers, websocket_ping_interval=15, websocket_ping_timeout=30)
        
        # 1. Start HTTP Server
        self._http_server = tornado.httpserver.HTTPServer(app)
        try:
            import tornado.netutil
            sockets = tornado.netutil.bind_sockets(self.port, address="0.0.0.0")
            self._http_server.add_sockets(sockets)
            print(f"[Server] AirContinuity HTTP listening on http://0.0.0.0:{self.port}")
        except Exception as e:
            print(f"[Server] Could not bind HTTP port {self.port}: {e}")

        # 2. Start HTTPS Server for iOS Secure Context (Required for WebRTC Screen Mirroring)
        ssl_files = ensure_ssl_certificates()
        if ssl_files:
            try:
                cert_path, key_path = ssl_files
                ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                ssl_ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
                self._https_server = tornado.httpserver.HTTPServer(app, ssl_options=ssl_ctx)
                self._https_server.listen(self.https_port, address="0.0.0.0")
                print(f"[Server] AirContinuity HTTPS listening on https://0.0.0.0:{self.https_port} (Secure Context)")
            except Exception as e:
                print(f"[Server] Could not initialize HTTPS server: {e}")

        self._ioloop = tornado.ioloop.IOLoop.current()
        self._ioloop.start()

    def stop(self):
        if self._http_server:
            try: self._http_server.stop()
            except Exception: pass
        if self._https_server:
            try: self._https_server.stop()
            except Exception: pass
        if self._ioloop:
            self._ioloop.add_callback(self._ioloop.stop)

    def broadcast(self, message: Dict[str, Any], exclude=None):
        msg_str = json.dumps(message)
        for ws in list(self.active_sockets):
            if ws != exclude:
                try:
                    ws.write_message(msg_str)
                except Exception:
                    pass

    def on_client_connection(self, count: int):
        if self.on_client_connect_cb:
            self.on_client_connect_cb(count)

    def on_screen_mirror_state(self, active: bool):
        if self.on_screen_mirror_cb:
            self.on_screen_mirror_cb(active)
