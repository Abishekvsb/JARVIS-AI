"""JARVIS 24/7 Cloud Backend Server.

Operates independently of any local laptop or PC.
Provides:
1. 24/7 Notification Ingestion from Android phone.
2. Zero-latency Auto-Reply Engine for standard greetings.
3. Dialogue State & Multi-Turn Context Tracking.
4. Cloud AI Intelligence (Claude API / Cloud LLM).
5. WebSockets & HUD serving for remote laptop/mobile monitoring.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import mimetypes
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import psutil
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jarvis.conversation_brain import ConversationBrain
from jarvis.mobile.auto_reply import AutoReplyEngine
from jarvis.mobile.notification_hub import NotificationHub

logger = logging.getLogger("jarvis.cloud")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

STATIC_DIR = Path(__file__).parent / "ui" / "static"
START_TIME = time.time()


# --- Pydantic Request Models ---

class IngestNotificationRequest(BaseModel):
    app: str
    sender: str
    content: str
    timestamp: Optional[float] = None


class AutoReplySettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    greeting_auto_reply_enabled: Optional[bool] = None
    allowed_apps: Optional[List[str]] = None
    allowed_contacts: Optional[List[str]] = None
    cooldown_seconds: Optional[int] = None


class ChatRequest(BaseModel):
    message: str


class AuthVerifyRequest(BaseModel):
    pin: str


# --- Cloud Auth & Session State Manager ---

class CloudAuthManager:
    """Manages cloud tokens, pairing PINs, and persistent secret keys."""

    _instance: Optional[CloudAuthManager] = None

    def __init__(self) -> None:
        self.secret_key = os.environ.get("JARVIS_SECRET_KEY", "jarvis-stark-mark7-cloud-secure-key")
        env_pin = os.environ.get("JARVIS_PAIRING_PIN") or os.environ.get("JARVIS_AUTH_PIN")
        # Ensure we never use or fall back to the previously exposed PIN '280506'
        if env_pin and env_pin.strip() != "280506":
            self.pairing_pin = env_pin.strip()
        else:
            self.pairing_pin = "560271"
        self.active_tokens: Dict[str, float] = {}

    @classmethod
    def get_instance(cls) -> CloudAuthManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def verify_pin(self, pin: str) -> Optional[str]:
        cleaned = pin.strip()
        # Explicit rejection of obsolete exposed PIN
        if cleaned == "280506":
            logger.warning("[AUTH] Login attempt with obsolete exposed PIN '280506' blocked.")
            return None
        if cleaned in (self.pairing_pin, self.secret_key):
            token = secrets.token_hex(24)
            self.active_tokens[token] = time.time() + (30 * 86400)  # 30 days validity
            return token
        return None

    def is_request_authenticated(self, request: Request) -> bool:
        # Check Authorization: Bearer <token>
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token != "280506" and (token in (self.secret_key, self.pairing_pin) or (token in self.active_tokens and time.time() < self.active_tokens[token])):
                return True

        # Check X-Jarvis-Token
        token = (request.headers.get("X-Jarvis-Token") or "").strip()
        if token and token != "280506" and (token in (self.secret_key, self.pairing_pin) or (token in self.active_tokens and time.time() < self.active_tokens[token])):
            return True

        # Check X-Jarvis-PIN
        pin = (request.headers.get("X-Jarvis-PIN") or "").strip()
        if pin and pin != "280506" and pin in (self.pairing_pin, self.secret_key):
            return True

        # Check Cookie
        cookie = request.cookies.get("jarvis_token", "").strip()
        if cookie and cookie != "280506" and (cookie in (self.secret_key, self.pairing_pin) or (cookie in self.active_tokens and time.time() < self.active_tokens[cookie])):
            return True

        return False


# --- Cloud WebSocket & Telemetry Broadcaster ---

class CloudHubBroadcaster:
    """Tracks connected HUD dashboards (laptop or phone) and broadcasts live events."""

    _instance: Optional[CloudHubBroadcaster] = None

    def __init__(self) -> None:
        self.sockets: Set[WebSocket] = set()

    @classmethod
    def get_instance(cls) -> CloudHubBroadcaster:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def register(self, ws: WebSocket) -> None:
        self.sockets.add(ws)

    async def unregister(self, ws: WebSocket) -> None:
        self.sockets.discard(ws)

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        dead = set()
        for ws in list(self.sockets):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.sockets.discard(ws)


# --- FastAPI Application Factory ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[JARVIS CLOUD] 24/7 Cloud Backend initialized. Listening for mobile & HUD traffic.")
    yield
    logger.info("[JARVIS CLOUD] Shutting down.")


app = FastAPI(title="JARVIS 24/7 Cloud Assistant Backend", version="7.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Static HUD Serving ---

@app.get("/", response_class=Response)
async def serve_index() -> Response:
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return Response(content=index_file.read_bytes(), media_type="text/html; charset=utf-8")


@app.get("/static/{file_path:path}")
async def serve_static(file_path: str) -> Response:
    target_file = STATIC_DIR / file_path
    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail="Static asset not found")
    mime, _ = mimetypes.guess_type(str(target_file))
    mime = mime or "application/octet-stream"
    if "javascript" in mime or "css" in mime or "html" in mime:
        mime += "; charset=utf-8"
    return Response(content=target_file.read_bytes(), media_type=mime)


# --- Health & Telemetry Endpoints ---

@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    uptime_sec = int(time.time() - START_TIME)
    return {
        "status": "healthy",
        "service": "JARVIS Cloud Backend",
        "uptime_seconds": uptime_sec,
        "mode": "24/7 Laptop-Independent Cloud",
        "timestamp": time.time(),
    }


@app.get("/api/telemetry")
async def get_cloud_telemetry() -> Dict[str, Any]:
    mem = psutil.virtual_memory()
    uptime_sec = int(time.time() - START_TIME)
    hours, remainder = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s"

    notif_hub = NotificationHub.get_instance()
    auth_mgr = CloudAuthManager.get_instance()
    broadcaster = CloudHubBroadcaster.get_instance()

    return {
        "status": "success",
        "telemetry": {
            "cpu_percent": f"{psutil.cpu_percent():.1f}%",
            "memory_used_gb": f"{(mem.total - mem.available) / (1024**3):.2f} GB",
            "memory_total_gb": f"{mem.total / (1024**3):.2f} GB",
            "memory_percent": f"{mem.percent}%",
            "battery": "Cloud Server (AC 24/7 Power)",
            "disk_c_free_gb": "Persistent Cloud",
            "disk_d_free_gb": uptime_str,
            "ai_provider": "CLOUD INTELLIGENCE",
            "ai_model": os.environ.get("JARVIS_AI_MODEL", "Claude / Rule Engine"),
        },
        "cloud_status": {
            "connected_dashboards": len(broadcaster.sockets),
            "unread_notifications": notif_hub.get_unread_count(),
            "uptime": uptime_str,
        },
    }


# --- Mobile Ingestion & Notification Endpoints ---

@app.post("/api/notifications/ingest")
async def ingest_notification(req: IngestNotificationRequest, request: Request) -> Dict[str, Any]:
    """Ingest incoming notification from Android phone.

    Evaluates Auto-Reply rule immediately and returns reply instruction to phone.
    """
    auth = CloudAuthManager.get_instance()
    if not auth.is_request_authenticated(request):
        raise HTTPException(status_code=401, detail="Authentication required to ingest notifications.")

    notif_hub = NotificationHub.get_instance()
    accepted, notif, msg = notif_hub.ingest_notification(
        app=req.app,
        sender=req.sender,
        content=req.content,
        timestamp=req.timestamp,
    )

    if accepted and notif:
        # Broadcast event to connected laptop/mobile HUDs
        broadcaster = CloudHubBroadcaster.get_instance()
        await broadcaster.broadcast({
            "type": "notification_received",
            "notification": notif.to_dict(),
            "unread_count": notif_hub.get_unread_count(),
        })
        return {
            "status": "success",
            "message": msg,
            "notification": notif.to_dict(),
            "unread_count": notif_hub.get_unread_count(),
        }

    return {"status": "dropped", "message": msg, "unread_count": notif_hub.get_unread_count()}


@app.get("/api/notifications")
async def get_notifications(unread_only: bool = False, limit: int = 50) -> Dict[str, Any]:
    hub = NotificationHub.get_instance()
    return {
        "status": "success",
        "notifications": hub.get_notifications(unread_only=unread_only, limit=limit),
        "unread_count": hub.get_unread_count(),
    }


@app.post("/api/notifications/clear")
async def clear_notifications() -> Dict[str, Any]:
    hub = NotificationHub.get_instance()
    hub.clear()
    broadcaster = CloudHubBroadcaster.get_instance()
    await broadcaster.broadcast({"type": "notifications_cleared", "unread_count": 0})
    return {"status": "success", "message": "All notifications cleared."}


# --- Auto-Reply Configuration Endpoints ---

@app.get("/api/settings/auto-reply")
async def get_auto_reply_settings() -> Dict[str, Any]:
    engine = AutoReplyEngine.get_instance()
    return {
        "status": "success",
        "enabled": engine.config.enabled,
        "greeting_auto_reply_enabled": engine.config.greeting_auto_reply_enabled,
        "allowed_apps": list(engine.config.allowed_apps),
        "allowed_contacts": engine.config.allowed_contacts,
        "cooldown_seconds": engine.config.cooldown_seconds,
    }


@app.post("/api/settings/auto-reply")
async def update_auto_reply_settings(req: AutoReplySettingsRequest, request: Request) -> Dict[str, Any]:
    auth = CloudAuthManager.get_instance()
    if not auth.is_request_authenticated(request):
        raise HTTPException(status_code=401, detail="Authentication required.")

    engine = AutoReplyEngine.get_instance()
    updates = {}
    if req.enabled is not None:
        updates["enabled"] = req.enabled
    if req.greeting_auto_reply_enabled is not None:
        updates["greeting_auto_reply_enabled"] = req.greeting_auto_reply_enabled
    if req.allowed_apps is not None:
        updates["allowed_apps"] = set(req.allowed_apps)
    if req.allowed_contacts is not None:
        updates["allowed_contacts"] = req.allowed_contacts
    if req.cooldown_seconds is not None:
        updates["cooldown_seconds"] = req.cooldown_seconds

    engine.update_config(**updates)

    broadcaster = CloudHubBroadcaster.get_instance()
    await broadcaster.broadcast({
        "type": "settings_updated",
        "auto_reply": {
            "enabled": engine.config.enabled,
            "greeting_auto_reply_enabled": engine.config.greeting_auto_reply_enabled,
            "allowed_apps": list(engine.config.allowed_apps),
        },
    })
    return {"status": "success", "message": "Auto-reply configuration updated successfully."}


# --- Mobile Pairing & Auth API ---

@app.get("/api/mobile/info")
async def get_mobile_info(request: Request) -> Dict[str, Any]:
    auth = CloudAuthManager.get_instance()
    is_authed = auth.is_request_authenticated(request)
    return {
        "status": "success",
        "authenticated": is_authed,
        "pairing_pin": auth.pairing_pin if is_authed else "******",
        "server_mode": "cloud_24_7",
    }


@app.post("/api/auth/verify")
async def verify_auth(req: AuthVerifyRequest) -> Dict[str, Any]:
    auth = CloudAuthManager.get_instance()
    token = auth.verify_pin(req.pin)
    if token:
        return {"status": "success", "token": token, "message": "Device authenticated with Cloud JARVIS, Sir."}
    return {"status": "error", "message": "Invalid Security PIN or Key."}


# --- Cloud Multi-Turn Chat & AI ---

@app.post("/api/chat")
async def handle_cloud_chat(req: ChatRequest, request: Request) -> Dict[str, Any]:
    auth = CloudAuthManager.get_instance()
    if not auth.is_request_authenticated(request):
        raise HTTPException(status_code=401, detail="Authentication required.")

    msg = req.message.strip()
    if not msg:
        return {"reply": "", "status": "empty"}

    brain = ConversationBrain.get_instance("Abishek")
    notif_hub = NotificationHub.get_instance()

    # 1. Process through dialogue state tracker (entity tracking, confirmations)
    direct_answer, pending_action = brain.handle_dialogue_turn(msg, notification_feed=notif_hub.get_notifications(limit=10))

    if pending_action:
        tool_input = pending_action.get("input", {})
        rec = tool_input.get("recipient", "contact")
        text = tool_input.get("message", "")
        reply = f"Instruction registered: send message '{text}' to {rec} via mobile companion, Sir."
        return {"reply": reply, "pending_action": pending_action, "status": "action_dispatched"}

    if direct_answer:
        filtered = brain.filter_response(direct_answer)
        return {"reply": filtered, "status": "handled_by_brain"}

    # 2. Check Cloud Anthropic API if key is configured
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key and not api_key.startswith("your_"):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model=os.environ.get("CLAUDE_MODEL", "claude-3-5-haiku-20241022"),
                max_tokens=512,
                system="You are JARVIS, an advanced personal AI assistant. Be concise, direct, and respectful.",
                messages=[{"role": "user", "content": msg}],
            )
            ai_text = "".join(b.text for b in resp.content if b.type == "text")
            filtered = brain.filter_response(ai_text)
            return {"reply": filtered, "status": "cloud_ai"}
        except Exception as e:
            logger.warning(f"[CLOUD AI] Claude API call failed: {e}")

    # 3. Rule-based conversational fallback
    fallback_reply = f"Standing by, Sir. I have recorded your message: '{msg}'."
    filtered = brain.filter_response(fallback_reply)
    return {"reply": filtered, "status": "fallback"}


# --- Cloud WebSocket Channel ---

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    broadcaster = CloudHubBroadcaster.get_instance()
    await broadcaster.register(ws)
    try:
        notif_hub = NotificationHub.get_instance()
        auto_reply = AutoReplyEngine.get_instance()
        await ws.send_json({
            "type": "init",
            "state": "IDLE",
            "message": "JARVIS Cloud Online (24/7 Mobile Active).",
            "telemetry": {
                "cpu_percent": f"{psutil.cpu_percent():.1f}%",
                "battery": "Cloud 24/7 Power",
            },
            "notifications": notif_hub.get_notifications(limit=15),
            "unread_count": notif_hub.get_unread_count(),
            "auto_reply": {
                "enabled": auto_reply.config.enabled,
                "greeting_auto_reply_enabled": auto_reply.config.greeting_auto_reply_enabled,
                "allowed_apps": list(auto_reply.config.allowed_apps),
            },
        })

        while True:
            data = await ws.receive_json()
            if data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Cloud WS closed: {e}")
    finally:
        await broadcaster.unregister(ws)
