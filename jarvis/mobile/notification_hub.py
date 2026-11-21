"""Central Notification Hub for Mobile & Device Integrations in JARVIS.

Ingests notifications from Android companion apps, classifies priority,
prevents duplicates, maintains history, updates dialogue context,
and interfaces with the Auto-Reply Engine.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from jarvis.conversation_brain import ConversationBrain
from jarvis.mobile.auto_reply import AutoReplyEngine

logger = logging.getLogger(__name__)


class NotificationPriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class Notification:
    id: str
    app: str
    sender: str
    content: str
    timestamp: float
    priority: NotificationPriority
    read: bool = False
    auto_replied: bool = False
    auto_reply_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["priority"] = self.priority.value
        return d


class NotificationHub:
    """Manages the incoming notification stream from connected mobile devices."""

    _instance: Optional[NotificationHub] = None

    def __init__(self, max_history: int = 100) -> None:
        self.max_history = max_history
        self._notifications: List[Notification] = []
        self._recent_signatures: Dict[str, float] = {}  # (app, sender, content) -> timestamp
        self.dedup_window_seconds = 10.0

    @classmethod
    def get_instance(cls) -> NotificationHub:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def classify_priority(self, app: str, sender: str, content: str) -> NotificationPriority:
        """Classify notification priority into HIGH, MEDIUM, or LOW."""
        content_lower = content.lower()
        sender_lower = sender.lower()

        # HIGH Priority: Security, calls, urgent, emergency
        high_signals = ("emergency", "urgent", "call", "incoming call", "alert", "security", "otp", "code", "warning")
        if any(s in content_lower for s in high_signals) or any(s in sender_lower for s in ("security", "bank", "police")):
            return NotificationPriority.HIGH

        # MEDIUM Priority: Direct personal communication apps
        medium_apps = ("whatsapp", "telegram", "sms", "messages", "messenger", "signal", "instagram")
        if any(m in app.lower() for m in medium_apps):
            return NotificationPriority.MEDIUM

        # LOW Priority: Promotional, store, news, game alerts
        return NotificationPriority.LOW

    def ingest_notification(
        self,
        app: str,
        sender: str,
        content: str,
        timestamp: Optional[float] = None,
    ) -> Tuple[bool, Optional[Notification], str]:
        """Ingest a new incoming mobile notification with deduplication.

        Returns (accepted: bool, notification_obj: Optional[Notification], message: str).
        """
        now = timestamp or time.time()
        sig = f"{app.strip().lower()}|{sender.strip().lower()}|{content.strip().lower()}"

        # 1. Deduplication check
        last_seen = self._recent_signatures.get(sig, 0.0)
        if (now - last_seen) < self.dedup_window_seconds:
            logger.info(f"[NOTIF_HUB] Dropped duplicate notification from {sender} on {app}")
            return False, None, "Duplicate notification dropped."

        self._recent_signatures[sig] = now

        # Clean old signatures
        self._recent_signatures = {
            k: v for k, v in self._recent_signatures.items() if (now - v) < self.dedup_window_seconds * 2
        }

        # 2. Priority classification
        priority = self.classify_priority(app, sender, content)

        # 3. Create Notification record
        notif_id = f"notif_{uuid.uuid4().hex[:8]}"
        notif = Notification(
            id=notif_id,
            app=app.strip(),
            sender=sender.strip(),
            content=content.strip(),
            timestamp=now,
            priority=priority,
        )

        # 4. Update ConversationBrain context so dialogue queries immediately know this contact & message
        ConversationBrain.get_instance().update_incoming_notification(
            app_name=notif.app,
            sender=notif.sender,
            content=notif.content,
        )

        # 5. Evaluate Auto-Reply
        reply_engine = AutoReplyEngine.get_instance()
        should_reply, reply_text, reply_reason = reply_engine.evaluate_reply(
            app=notif.app,
            sender=notif.sender,
            message=notif.content,
        )

        if should_reply and reply_text:
            notif.auto_replied = True
            notif.auto_reply_text = reply_text
            reply_engine.record_reply_sent(notif.sender)
            logger.info(f"[NOTIF_HUB] Auto-replying to {notif.sender}: '{reply_text}' (Reason: {reply_reason})")
            # Trigger dispatch via WhatsApp automation if app is WhatsApp
            try:
                from jarvis.automation.executor import execute_tool
                execute_tool("send_whatsapp_message", {"recipient": notif.sender, "message": reply_text})
            except Exception as e:
                logger.error(f"[NOTIF_HUB] Failed to dispatch auto-reply: {e}")

        # 6. Store in history (newest first)
        self._notifications.insert(0, notif)
        if len(self._notifications) > self.max_history:
            self._notifications.pop()

        return True, notif, "Notification ingested successfully."

    def get_notifications(self, unread_only: bool = False, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve notifications as dictionary records."""
        items = self._notifications
        if unread_only:
            items = [n for n in items if not n.read]
        return [n.to_dict() for n in items[:limit]]

    def get_unread_count(self) -> int:
        """Return total unread notifications count."""
        return sum(1 for n in self._notifications if not n.read)

    def mark_all_read(self) -> int:
        """Mark all notifications as read."""
        count = 0
        for n in self._notifications:
            if not n.read:
                n.read = True
                count += 1
        return count

    def clear(self) -> None:
        """Clear all notification records."""
        self._notifications.clear()
        self._recent_signatures.clear()
