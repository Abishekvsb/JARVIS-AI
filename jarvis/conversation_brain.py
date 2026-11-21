"""Dialogue State Tracking, Entity Resolution, and Anti-Repetition Brain for JARVIS.

Solves:
1. Context loss across multi-turn exchanges (tracks active contact, last app, and last message).
2. Pronoun resolution: "avanukku", "him", "her", "that person" -> active contact.
3. Pending action confirmation flow: "Arun-ku Good morning send pannava?" -> "Yes" -> executes.
4. Response deduplication: Prevents repeating identical or redundant answers.
5. Code-switching understanding for natural Tamil, Tanglish, and English.
"""

from __future__ import annotations

import difflib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DialogueState:
    """Maintains active conversation entities and pending actions."""

    user_name: str = "Abishek"
    active_contact: Optional[str] = None
    active_app: Optional[str] = None
    last_incoming_message: Optional[str] = None
    last_incoming_sender: Optional[str] = None
    last_incoming_app: Optional[str] = None
    pending_action: Optional[Dict[str, Any]] = None
    waiting_for_confirmation: bool = False
    recent_responses: List[str] = field(default_factory=list)
    recent_intents: List[str] = field(default_factory=list)
    context_turn_count: int = 0
    last_activity_time: float = field(default_factory=time.time)


class ConversationBrain:
    """Context-aware Dialogue State Tracker and Natural Language Disambiguator."""

    _instance: Optional[ConversationBrain] = None

    def __init__(self, user_name: str = "Abishek") -> None:
        self.state = DialogueState(user_name=user_name)
        self.max_history_responses = 10

    @classmethod
    def get_instance(cls, user_name: str = "Abishek") -> ConversationBrain:
        if cls._instance is None:
            cls._instance = cls(user_name=user_name)
        return cls._instance

    def update_incoming_notification(
        self,
        app_name: str,
        sender: str,
        content: str,
    ) -> None:
        """Update active dialogue context when a new message or notification arrives."""
        self.state.last_incoming_app = app_name
        self.state.last_incoming_sender = sender
        self.state.last_incoming_message = content
        self.state.active_contact = sender
        self.state.active_app = app_name
        self.state.last_activity_time = time.time()
        logger.info(f"[BRAIN] Context updated with incoming notification from {sender} on {app_name}: '{content}'")

    def resolve_pronouns(self, text: str) -> str:
        """Resolve pronouns like 'avanukku', 'him', 'her', 'that person' to active_contact."""
        resolved = text
        contact = self.state.active_contact or self.state.last_incoming_sender

        if contact:
            # Tamil / Tanglish pronouns: avanukku, avalukku, avangalukku, avanitta
            resolved = re.sub(
                r"\b(avanukku|avalukku|avangalukku|avanitta|avalitta)\b",
                f"{contact}-ku",
                resolved,
                flags=re.IGNORECASE,
            )
            # English pronouns: him, her, them, that person
            resolved = re.sub(
                r"\b(tell him|tell her|tell them|say to him|say to her|reply to him|reply to her)\b",
                f"tell {contact}",
                resolved,
                flags=re.IGNORECASE,
            )
            resolved = re.sub(
                r"\b(to him|to her|to them)\b",
                f"to {contact}",
                resolved,
                flags=re.IGNORECASE,
            )

        return resolved

    def classify_intent(self, text: str) -> Tuple[str, Dict[str, Any]]:
        """Identify the intent category and extract semantic parameters.

        Returns (intent_type, metadata_dict).
        """
        p = text.strip().lower()

        # 1. Confirmation handling
        if self.state.waiting_for_confirmation:
            if any(k in p for k in ("yes", "send", "aam", "anupu", "send pannu", "sari", "ok", "kandippa", "confirm")):
                return "CONFIRM_YES", {}
            if any(k in p for k in ("no", "cancel", "vendaam", "stop", "bedam", "don't", "dont", "tappa irukku")):
                return "CONFIRM_NO", {}

        # 2. Who messaged query
        if any(k in p for k in ("yaar message", "who messaged", "who sent", "yaar anupiruka", "yaar pesuna")):
            return "QUERY_SENDER", {"app": self.state.active_app or "WhatsApp"}

        # 3. What message query
        if any(k in p for k in ("enna message", "what message", "what did he say", "enna anupirukan", "enna sonnan", "read message", "message enna")):
            return "QUERY_CONTENT", {"contact": self.state.active_contact, "app": self.state.active_app}

        # 4. Message reply command
        if any(k in p for k in ("sollu", "anupu", "reply", "send", "tell")):
            # Resolve pronouns first
            resolved_text = self.resolve_pronouns(text)
            # Check pattern: "<contact>-ku <message> sollu/anupu" or "tell <contact> <message>"
            m_ta = re.search(r"([a-zA-Z0-9_\+]+)\s*[-_]?\s*ku\s+(.+?)(?:\s+sollu|\s+anupu|\s+reply\s+pannu)?$", resolved_text, re.IGNORECASE)
            m_en = re.search(r"(?:tell|reply to|say to|send to)\s+([a-zA-Z0-9_\+]+)\s+(?:that|saying)?\s*(.+)$", resolved_text, re.IGNORECASE)

            target_match = m_ta or m_en
            if target_match:
                recipient = target_match.group(1).strip()
                content = target_match.group(2).strip()
                # Clean filler words and punctuation
                content = re.sub(r"\b(sollu|anupu|pannu|endru|that)\b", "", content, flags=re.IGNORECASE).strip(" .!?,:;")
                if recipient and content:
                    return "REPLY_COMMAND", {"recipient": recipient, "message": content}

            # If recipient is omitted but active contact exists (e.g. "Good morning sollu")
            if self.state.active_contact:
                clean_content = re.sub(r"\b(sollu|anupu|reply|send|tell him|tell her)\b", "", resolved_text, flags=re.IGNORECASE).strip(" .!?,:;")
                if clean_content:
                    return "REPLY_COMMAND", {"recipient": self.state.active_contact, "message": clean_content}

        # 5. Check WhatsApp / Notifications status
        if any(k in p for k in ("whatsapp check", "check whatsapp", "notification check", "notifications check", "new messages")):
            return "CHECK_NOTIFICATIONS", {"app": "WhatsApp" if "whatsapp" in p else "all"}

        # 6. Suggest reply query
        if any(k in p for k in ("enna reply", "what to reply", "suggest reply", "how to reply", "enna solla")):
            return "SUGGEST_REPLY", {
                "contact": self.state.active_contact,
                "incoming_message": self.state.last_incoming_message,
            }

        # 7. Greetings
        if any(k in p for k in ("hello jarvis", "hi jarvis", "vanakkam jarvis", "hey jarvis", "good morning jarvis")):
            return "GREETING", {}

        return "GENERAL_CONVERSATION", {}

    def handle_dialogue_turn(
        self,
        user_text: str,
        notification_feed: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Process turn through dialogue state tracker.

        Returns (direct_answer_if_handled, pending_action_if_any).
        """
        intent, params = self.classify_intent(user_text)
        logger.info(f"[BRAIN] Classified intent '{intent}' with params: {params}")

        # 1. Handle Confirmation
        if intent == "CONFIRM_YES" and self.state.pending_action:
            action = self.state.pending_action
            self.state.pending_action = None
            self.state.waiting_for_confirmation = False
            return None, action  # Signal executor to run pending action

        if intent == "CONFIRM_NO":
            self.state.pending_action = None
            self.state.waiting_for_confirmation = False
            return "Cancelled. I will not send that message, Sir.", None

        # 2. Query Sender
        if intent == "QUERY_SENDER":
            if notification_feed and len(notification_feed) > 0:
                senders = list(dict.fromkeys(n.get("sender", "Unknown") for n in notification_feed if n.get("sender")))
                if len(senders) == 1:
                    self.state.active_contact = senders[0]
                    return f"{self.state.user_name}, {senders[0]} has sent you a message.", None
                elif len(senders) > 1:
                    senders_str = ", ".join(senders[:-1]) + " and " + senders[-1]
                    return f"{self.state.user_name}, you have messages from {senders_str}.", None
            elif self.state.last_incoming_sender:
                return f"{self.state.user_name}, {self.state.last_incoming_sender} has sent you a message.", None
            else:
                return f"You currently have no unread messages, {self.state.user_name}.", None

        # 3. Query Content
        if intent == "QUERY_CONTENT":
            contact = params.get("contact") or self.state.active_contact
            if self.state.last_incoming_message:
                return f"{contact or 'They'} sent: \"{self.state.last_incoming_message}\"", None
            return f"I don't have the message content stored for {contact or 'them'}, Sir.", None

        # 4. Reply Command -> Prepare Confirmation
        if intent == "REPLY_COMMAND":
            recipient = params.get("recipient")
            message = params.get("message")
            if recipient and message:
                self.state.active_contact = recipient
                self.state.pending_action = {
                    "tool": "send_whatsapp_message",
                    "input": {"recipient": recipient, "message": message},
                }
                self.state.waiting_for_confirmation = True
                return f"{recipient}-ku \"{message}\" message send pannava, {self.state.user_name}?", None

        # 5. Check Notifications
        if intent == "CHECK_NOTIFICATIONS":
            if notification_feed and len(notification_feed) > 0:
                count = len(notification_feed)
                latest = notification_feed[0]
                self.state.active_contact = latest.get("sender")
                self.state.last_incoming_message = latest.get("content")
                return f"You have {count} active notifications, {self.state.user_name}. Latest is from {latest.get('sender', 'someone')} on {latest.get('app', 'WhatsApp')}.", None
            return f"No new notifications right now, {self.state.user_name}.", None

        return None, None

    def filter_response(self, new_response: str) -> str:
        """Deduplicate and clean assistant responses to prevent repetition."""
        cleaned = new_response.strip()

        # Remove repetitive assistant boilerplate
        cleaned = re.sub(
            r"^(Certainly, Sir|Good day, Sir|As an AI assistant|As J\.A\.R\.V\.I\.S\.,)\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()

        # Check for repetition against recent responses
        for prev in self.state.recent_responses[-3:]:
            ratio = difflib.SequenceMatcher(None, cleaned.lower(), prev.lower()).ratio()
            if ratio > 0.85:
                # Highly repetitive; generate crisp acknowledgment
                logger.warning(f"[BRAIN] Detected repetitive response (similarity={ratio:.2f}). Diversifying.")
                cleaned = f"Understood, {self.state.user_name}. Standing by for your next instruction."
                break

        # Record response
        self.state.recent_responses.append(cleaned)
        if len(self.state.recent_responses) > self.max_history_responses:
            self.state.recent_responses.pop(0)

        return cleaned

