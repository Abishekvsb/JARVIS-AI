"""Intelligent Auto-Reply Engine for JARVIS Mobile Integrations.

Enforces:
1. Strict OFF-by-default safety.
2. Zero-confirmation only for explicit simple greetings (when enabled).
3. Contact cooldowns and loop prevention (default 300 seconds).
4. Security blacklist: Blocks OTPs, bank alerts, passwords, verification codes.
5. Group message exclusion by default.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from jarvis.config import JARVIS_ROOT

logger = logging.getLogger(__name__)

STATE_DIR = JARVIS_ROOT / "data"
STATE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = STATE_DIR / "auto_reply_config.json"

# Security sensitive keywords: Never auto-reply to these under any circumstance
SECURITY_BLACKLIST = (
    "otp",
    "one time password",
    "verification code",
    "bank",
    "debit",
    "credit",
    "account",
    "password",
    "pin",
    "atm",
    "cvv",
    "transaction",
    "upi",
    "rupees",
    "rs.",
    "inr",
    "paid",
    "statement",
    "urgent",
    "emergency",
    "hospital",
    "police",
    "http://",
    "https://",
)

# Standard greetings mapping
STANDARD_GREETING_RULES = [
    (r"^(?:hi|hey|hai|vanakkam)\b[\s!.]*$", "Hi!"),
    (r"^(?:hello)\b[\s!.]*$", "Hello!"),
    (r"^(?:good\s*morning|gm|morning)\b[\s!.]*$", "Good morning! Have a great day."),
    (r"^(?:good\s*afternoon)\b[\s!.]*$", "Good afternoon!"),
    (r"^(?:good\s*evening|evening)\b[\s!.]*$", "Good evening! Hope you had a great day."),
    (r"^(?:good\s*night|gn|night)\b[\s!.]*$", "Good night! Take care."),
    (r"^(?:how\s*are\s*you|epdi\s*irukka|how\s*r\s*u)\b[\s!?.]*$", "I'm good, thank you! How are you?"),
    (r"^(?:are\s*you\s*busy|busy[?]?|busy\s*ah)\b[\s!?.]*$", "I'm currently busy right now. I'll get back to you soon."),
]


@dataclass
class AutoReplyConfig:
    """Configurable settings for Auto-Reply."""

    enabled: bool = False  # OFF by default
    greeting_auto_reply_enabled: bool = False  # Explicit toggle for greeting auto-replies
    allowed_apps: Set[str] = field(default_factory=lambda: {"WhatsApp", "Telegram", "SMS"})
    allowed_contacts: List[str] = field(default_factory=list)  # Empty means all contacts permitted
    blocked_contacts: List[str] = field(default_factory=list)
    cooldown_seconds: int = 300  # 5 minutes per contact
    allow_groups: bool = False  # Never auto-reply to groups by default
    custom_rules: List[Tuple[str, str]] = field(default_factory=list)


class AutoReplyEngine:
    """Intelligent, rule-based and safe Auto-Reply evaluation engine."""

    _instance: Optional[AutoReplyEngine] = None

    def __init__(self, config: Optional[AutoReplyConfig] = None) -> None:
        self.config = config or AutoReplyConfig()
        # Contact cooldown tracker: sender_key -> last_replied_timestamp
        self._last_replied: Dict[str, float] = {}
        if config is None:
            self._load_state()

    @classmethod
    def get_instance(cls) -> AutoReplyEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_state(self) -> None:
        try:
            if CONFIG_FILE.exists():
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self.config.enabled = data.get("enabled", False)
                self.config.greeting_auto_reply_enabled = data.get("greeting_auto_reply_enabled", False)
                if "allowed_apps" in data:
                    self.config.allowed_apps = set(data["allowed_apps"])
                if "allowed_contacts" in data:
                    self.config.allowed_contacts = data["allowed_contacts"]
                if "cooldown_seconds" in data:
                    self.config.cooldown_seconds = data["cooldown_seconds"]
                logger.info(f"[AUTO-REPLY] Loaded persistent config: enabled={self.config.enabled}")
        except Exception as e:
            logger.warning(f"[AUTO-REPLY] Could not load state: {e}")

    def _save_state(self) -> None:
        try:
            payload = {
                "enabled": self.config.enabled,
                "greeting_auto_reply_enabled": self.config.greeting_auto_reply_enabled,
                "allowed_apps": list(self.config.allowed_apps),
                "allowed_contacts": self.config.allowed_contacts,
                "cooldown_seconds": self.config.cooldown_seconds,
            }
            CONFIG_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[AUTO-REPLY] Could not save state: {e}")

    def update_config(self, **kwargs) -> None:
        """Update configuration parameters at runtime."""
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                if k == "allowed_apps" and isinstance(v, (list, tuple)):
                    setattr(self.config, k, set(v))
                else:
                    setattr(self.config, k, v)
        self._save_state()
        logger.info(f"[AUTO-REPLY] Config updated: enabled={self.config.enabled}, greetings={self.config.greeting_auto_reply_enabled}")

    def is_security_sensitive(self, text: str) -> bool:
        """Check if message contains banking, OTP, or emergency keywords."""
        t = text.lower()
        return any(term in t for term in SECURITY_BLACKLIST)

    def is_group_message(self, sender: str, content: str) -> bool:
        """Heuristic to detect if notification is from a group chat."""
        # Common group patterns: "[Family Group]", "Arun: Hello", "Group Name: "
        if ":" in sender or ":" in content[:25]:
            return True
        if any(term in sender.lower() for term in ("group", "family", "team", "gang", "club", "batch")):
            return True
        return False

    def can_reply_to_contact(self, sender: str) -> Tuple[bool, str]:
        """Check contact allowlist, blocklist, and cooldown."""
        sender_clean = sender.strip().lower()

        # Check blocklist
        if any(b.lower() in sender_clean for b in self.config.blocked_contacts):
            return False, f"Contact '{sender}' is blocklisted."

        # Check allowlist if configured
        if self.config.allowed_contacts:
            if not any(a.lower() in sender_clean for a in self.config.allowed_contacts):
                return False, f"Contact '{sender}' is not in allowlisted contacts."

        # Check cooldown
        now = time.time()
        last_time = self._last_replied.get(sender_clean, 0.0)
        elapsed = now - last_time
        if elapsed < self.config.cooldown_seconds:
            remaining = int(self.config.cooldown_seconds - elapsed)
            return False, f"Cooldown active for '{sender}' ({remaining}s remaining)."

        return True, "Permitted"

    def evaluate_reply(
        self,
        app: str,
        sender: str,
        message: str,
    ) -> Tuple[bool, Optional[str], str]:
        """Evaluate if an incoming message should receive an automated reply.

        Returns (should_reply: bool, reply_content: Optional[str], reason: str).
        """
        # 1. Master Auto-Reply switch
        if not self.config.enabled:
            return False, None, "Auto-Reply is globally disabled."

        # 2. App allowlist check
        matched_app = None
        for allowed in self.config.allowed_apps:
            if allowed.lower() in app.lower():
                matched_app = allowed
                break
        if not matched_app:
            return False, None, f"App '{app}' is not in allowed auto-reply apps."

        # 3. Security sensitive check
        if self.is_security_sensitive(message):
            return False, None, "Message contains sensitive, security, or financial keywords. Auto-reply blocked."

        # 4. Group check
        if not self.config.allow_groups and self.is_group_message(sender, message):
            return False, None, "Group message detected. Auto-reply to groups is disabled."

        # 5. Contact validation & cooldown
        can_reply, contact_reason = self.can_reply_to_contact(sender)
        if not can_reply:
            return False, None, contact_reason

        # 6. Check custom rules first
        msg_clean = message.strip().lower()
        for pattern, response in self.config.custom_rules:
            if re.search(pattern, msg_clean, re.IGNORECASE):
                return True, response, f"Matched custom rule: {pattern}"

        # 7. Check simple greetings if greeting auto-reply is enabled
        if self.config.greeting_auto_reply_enabled:
            for pattern, response in STANDARD_GREETING_RULES:
                if re.search(pattern, msg_clean, re.IGNORECASE):
                    return True, response, f"Matched standard greeting: {pattern}"

        return False, None, "No matching auto-reply rule found. Requires user confirmation or manual reply."

    def record_reply_sent(self, sender: str) -> None:
        """Mark contact cooldown upon successful auto-reply dispatch."""
        self._last_replied[sender.strip().lower()] = time.time()

