"""
Certificate manager for AirContinuity.
Generates and manages self-signed SSL certificates for local HTTPS support,
enabling WebRTC and screen mirroring on iOS Safari (which requires a Secure Context).
"""
import os
import socket
import datetime
import ipaddress
from pathlib import Path
from typing import Tuple, Optional

from app import config

def get_local_ips():
    ips = {"127.0.0.1"}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        _, _, host_ips = socket.gethostbyname_ex(socket.gethostname())
        for ip in host_ips:
            ips.add(ip)
    except Exception:
        pass
    return list(ips)

def ensure_ssl_certificates() -> Optional[Tuple[Path, Path]]:
    """Ensure SSL cert and key exist, generating them with cryptography if needed."""
    app_dir = config.get_app_dir()
    cert_path = app_dir / "cert.pem"
    key_path = app_dir / "key.pem"

    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        # Generate RSA private key
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        # Subject & Issuer
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "AirContinuity"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AirContinuity"),
        ])

        # SANs (Subject Alternative Names)
        sans = [
            x509.DNSName("localhost"),
            x509.DNSName(socket.gethostname()),
            x509.DNSName(f"{socket.gethostname()}.local"),
        ]
        for ip in get_local_ips():
            try:
                sans.append(x509.IPAddress(ipaddress.IPv4Address(ip)))
            except Exception:
                pass

        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .sign(key, hashes.SHA256())
        )

        # Save private key
        with open(key_path, "wb") as f:
            f.write(
                key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                )
            )

        # Save certificate
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        print(f"[SSL] Generated self-signed SSL certificate at: {cert_path}")
        return cert_path, key_path

    except Exception as e:
        print(f"[SSL] Could not generate SSL certificate: {e}")
        return None
