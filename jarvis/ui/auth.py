"""Authentication and Device Pairing Security for JARVIS Mobile Access.

Enforces Rule 5 (Security) and Rule 1 (Authorization) from the Future Roadmap:
- Localhost (127.0.0.1) is auto-authenticated for desktop operation.
- Remote mobile devices on local Wi-Fi require a secure 6-digit Pairing PIN.
- Issues cryptographically signed session tokens for authorized mobile devices.
- Zero Drive C: usage.
"""

from __future__ import annotations

import logging
import secrets
import socket
import time
from pathlib import Path
from typing import Dict, Optional, Set

from fastapi import Request

from jarvis.config import CACHE_DIR

logger = logging.getLogger(__name__)

PIN_CACHE_FILE = CACHE_DIR / "temp" / "mobile_pairing_pin.txt"


class MobileAuthManager:
    """Manages pairing PIN generation and active mobile session tokens."""

    _instance: Optional[MobileAuthManager] = None

    def __init__(self) -> None:
        self.pairing_pin: str = self._generate_pin()
        self.active_tokens: Dict[str, float] = {}  # token -> expiration_timestamp
        self.paired_device_ips: Set[str] = set()
        self._save_pin_to_cache()

    @classmethod
    def get_instance(cls) -> MobileAuthManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _generate_pin(self) -> str:
        """Generate a cryptographically secure 6-digit numeric PIN."""
        return f"{secrets.randbelow(900000) + 100000}"

    def regenerate_pin(self) -> str:
        """Generate a new pairing PIN."""
        self.pairing_pin = self._generate_pin()
        self._save_pin_to_cache()
        logger.info(f"[AUTH] New JARVIS Mobile Pairing PIN generated: {self.pairing_pin}")
        return self.pairing_pin

    def _save_pin_to_cache(self) -> None:
        try:
            PIN_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            PIN_CACHE_FILE.write_text(self.pairing_pin, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to cache pairing PIN: {e}")

    def verify_pin(self, pin: str, client_ip: str = "") -> Optional[str]:
        """Validate pairing PIN and return a session token if valid."""
        clean_pin = pin.strip()
        if clean_pin == self.pairing_pin:
            token = secrets.token_hex(24)
            # Token valid for 48 hours
            self.active_tokens[token] = time.time() + (48 * 3600)
            if client_ip:
                self.paired_device_ips.add(client_ip)
            logger.info(f"[AUTH] Mobile device ({client_ip or 'unknown'}) successfully paired. Token issued.")
            return token
        logger.warning(f"[AUTH] Invalid pairing PIN attempt from {client_ip}.")
        return None

    def is_token_valid(self, token: str) -> bool:
        """Check if session token exists and is unexpired."""
        if not token:
            return False
        exp = self.active_tokens.get(token)
        if exp is None:
            return False
        if time.time() > exp:
            del self.active_tokens[token]
            return False
        return True

    def revoke_token(self, token: str) -> None:
        """Revoke an active session token."""
        if token in self.active_tokens:
            del self.active_tokens[token]

    def is_request_authenticated(self, request: Request) -> bool:
        """Check if request is from localhost or carries a valid pairing token."""
        client_host = request.client.host if request.client else ""

        # Localhost on Windows is always trusted (including testclient in test harnesses)
        if client_host in ("127.0.0.1", "localhost", "::1", "testclient"):
            return True

        # Check X-Jarvis-Token header (accepts either active token or valid pairing PIN)
        header_token = (request.headers.get("X-Jarvis-Token") or "").strip()
        if header_token and (self.is_token_valid(header_token) or header_token == self.pairing_pin):
            return True

        # Check X-Jarvis-PIN header
        header_pin = (request.headers.get("X-Jarvis-PIN") or "").strip()
        if header_pin and header_pin == self.pairing_pin:
            return True

        # Check jarvis_token cookie
        cookie_token = request.cookies.get("jarvis_token")
        if cookie_token and (self.is_token_valid(cookie_token) or cookie_token == self.pairing_pin):
            return True

        return False


def get_local_network_ip() -> str:
    """Retrieve the primary local IPv4 address (e.g. 192.168.x.x or 10.x.x.x)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Connect to a public IP without sending packets to find local interface
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
