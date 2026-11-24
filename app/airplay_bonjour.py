"""
Bonjour / mDNS discovery announcer for AirPlay, AirDrop and WebDrop services.
Broadcasts services on the local Wi-Fi so iPhone can discover this Windows PC.
"""
import socket
from typing import Optional
from zeroconf import IPVersion, ServiceInfo, Zeroconf

class BonjourService:
    def __init__(self, port: int = 8089, host_name: Optional[str] = None):
        self.port = port
        self.host_name = host_name or socket.gethostname()
        self.zeroconf: Optional[Zeroconf] = None
        self.service_infos = []

    def get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def start(self):
        """Announce AirPlay, AirDrop, and WebDrop services."""
        try:
            self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
            local_ip = self.get_local_ip()
            ip_bytes = socket.inet_aton(local_ip)
            server_name = f"{self.host_name}.local."

            # 1. WebDrop / AirContinuity HTTP service
            http_info = ServiceInfo(
                type_="_http._tcp.local.",
                name=f"AirContinuity-{self.host_name}._http._tcp.local.",
                addresses=[ip_bytes],
                port=self.port,
                properties={
                    b"path": b"/",
                    b"name": self.host_name.encode("utf-8"),
                    b"type": b"AirContinuity-Bridge"
                },
                server=server_name,
            )
            self.zeroconf.register_service(http_info)
            self.service_infos.append(http_info)

            # NOTE: AirPlay mDNS advertisement is handled by the UxPlay receiver
            # subprocess (airplay_receiver.py). Registering it here would conflict
            # with UxPlay's own Bonjour service and confuse iOS device discovery.

            print(f"[Bonjour] Announced AirContinuity HTTP service for {self.host_name} on {local_ip}:{self.port}")
        except Exception as e:
            print(f"[Bonjour] Notice: {e}")

    def stop(self):
        if self.zeroconf:
            for info in self.service_infos:
                try:
                    self.zeroconf.unregister_service(info)
                except Exception:
                    pass
            self.zeroconf.close()
            self.zeroconf = None
            self.service_infos.clear()
