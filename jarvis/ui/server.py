"""FastAPI Server and WebSocket Hub for JARVIS Futuristic Desktop UI."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import mimetypes
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jarvis.automation.agent import AutomationAgent
from jarvis.automation.safety import EmergencyStopManager
from jarvis.config import CACHE_DIR, JARVIS_ROOT
from jarvis.conversation import JarvisConversation
from jarvis.mobile.auto_reply import AutoReplyEngine
from jarvis.mobile.notification_hub import NotificationHub
from jarvis.ui.auth import MobileAuthManager, get_local_network_ip
from jarvis.ui.state import UIState, UIStateManager
from jarvis.voice.audio_io import play_audio, record_until_silence
from jarvis.voice.stt import JarvisSTT
from jarvis.voice.tts import JarvisTTS

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class ChatRequest(BaseModel):
    message: str
    speak: Optional[bool] = None


class AuthVerifyRequest(BaseModel):
    pin: str


class VoiceListenRequest(BaseModel):
    max_seconds: float = 12.0
    speak: Optional[bool] = None


class IngestNotificationRequest(BaseModel):
    app: str
    sender: str
    content: str
    timestamp: Optional[float] = None


class AutoReplySettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    greeting_auto_reply_enabled: Optional[bool] = None
    allowed_apps: Optional[list[str]] = None
    allowed_contacts: Optional[list[str]] = None
    cooldown_seconds: Optional[int] = None


def create_ui_app(
    agent: Optional[AutomationAgent] = None,
    stt: Optional[JarvisSTT] = None,
    tts: Optional[JarvisTTS] = None,
) -> FastAPI:
    """Create and configure the FastAPI application for the JARVIS HUD."""
    state_mgr = UIStateManager.get_instance()
    automation_agent = agent or AutomationAgent()
    voice_stt = stt or JarvisSTT(model_size="base")
    voice_tts = tts or JarvisTTS()

    async def _telemetry_broadcast_loop() -> None:
        """Broadcast live psutil telemetry every 1.0 second."""
        while True:
            try:
                await asyncio.sleep(1.0)
                if state_mgr.connected_websockets:
                    await state_mgr.broadcast_telemetry()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Telemetry broadcast loop error: {e}")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        telemetry_task = asyncio.create_task(_telemetry_broadcast_loop())
        state_mgr.set_state(UIState.IDLE, "JARVIS Desktop HUD online. All systems nominal.")
        logger.info("JARVIS Desktop UI Server online.")
        try:
            yield
        finally:
            if telemetry_task and not telemetry_task.done():
                telemetry_task.cancel()

    app = FastAPI(title="JARVIS Futuristic Desktop UI", version="6.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Static File Serving (Self-contained, zero extra dependencies) ---

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
        # Guess mime type
        mime, _ = mimetypes.guess_type(str(target_file))
        mime = mime or "application/octet-stream"
        if "javascript" in mime or "css" in mime or "html" in mime:
            mime += "; charset=utf-8"
        return Response(content=target_file.read_bytes(), media_type=mime)

    @app.get("/manifest.json", response_class=Response)
    async def serve_manifest() -> Response:
        manifest_file = STATIC_DIR / "manifest.json"
        if not manifest_file.exists():
            raise HTTPException(status_code=404, detail="manifest.json not found")
        return Response(content=manifest_file.read_bytes(), media_type="application/manifest+json; charset=utf-8")

    @app.get("/sw.js", response_class=Response)
    async def serve_sw() -> Response:
        sw_file = STATIC_DIR / "sw.js"
        if not sw_file.exists():
            raise HTTPException(status_code=404, detail="sw.js not found")
        return Response(content=sw_file.read_bytes(), media_type="application/javascript; charset=utf-8")

    # --- Mobile Pairing & Authentication Endpoints ---

    @app.post("/api/auth/verify")
    async def verify_pairing_pin(req: AuthVerifyRequest, request: Request) -> Dict[str, Any]:
        """Verify the 6-digit PIN and issue a session token for mobile device access."""
        auth_mgr = MobileAuthManager.get_instance()
        client_ip = request.client.host if request.client else ""
        token = auth_mgr.verify_pin(req.pin, client_ip=client_ip)
        if token:
            return {"status": "success", "token": token, "message": "Device successfully paired, Sir."}
        return {"status": "error", "message": "Invalid pairing PIN. Access denied."}

    @app.get("/api/auth/status")
    async def get_auth_status(request: Request) -> Dict[str, Any]:
        """Check if client is authenticated."""
        auth_mgr = MobileAuthManager.get_instance()
        is_auth = auth_mgr.is_request_authenticated(request)
        client_ip = request.client.host if request.client else ""
        return {"authenticated": is_auth, "client_ip": client_ip}

    @app.get("/api/mobile/info")
    async def get_mobile_info(request: Request) -> Dict[str, Any]:
        """Provide local network connection info for mobile access."""
        auth_mgr = MobileAuthManager.get_instance()
        client_ip = request.client.host if request.client else ""
        is_localhost = client_ip in ("127.0.0.1", "localhost", "::1", "testclient")
        return {
            "local_ip": get_local_network_ip(),
            "pairing_pin": auth_mgr.pairing_pin if (is_localhost or auth_mgr.is_request_authenticated(request)) else None,
            "paired_devices": len(auth_mgr.paired_device_ips),
            "authenticated": auth_mgr.is_request_authenticated(request),
        }

    @app.get("/api/voice/audio/{filename}")
    async def get_spoken_audio(filename: str) -> Response:
        """Stream generated audio response to mobile client."""
        clean_name = Path(filename).name
        if not (clean_name.endswith(".mp3") or clean_name.endswith(".wav")):
            raise HTTPException(status_code=400, detail="Invalid audio format")
        target_file = CACHE_DIR / "temp" / clean_name
        if not target_file.exists():
            raise HTTPException(status_code=404, detail="Audio file not found")
        media_type = "audio/mpeg" if clean_name.endswith(".mp3") else "audio/wav"
        return Response(content=target_file.read_bytes(), media_type=media_type)

    @app.post("/api/voice/mobile-upload")
    async def handle_mobile_voice_upload(
        request: Request,
        audio: UploadFile = File(...),
        speak: Optional[bool] = Form(True),
    ) -> Dict[str, Any]:
        """Receive audio recorded from mobile phone microphone, process through Whisper and Ollama."""
        auth_mgr = MobileAuthManager.get_instance()
        if not auth_mgr.is_request_authenticated(request):
            raise HTTPException(status_code=401, detail="Mobile Pairing Authentication Required")

        state_mgr.set_state(UIState.PROCESSING, "Receiving audio stream from mobile device...")
        await state_mgr.broadcast_state()

        # Save incoming audio to D:\\JARVIS\\.cache\\temp
        temp_dir = CACHE_DIR / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename_orig = audio.filename or "mobile_voice.wav"
        ext = Path(filename_orig).suffix or ".wav"
        save_path = temp_dir / f"mobile_upload_{int(time.time())}{ext}"

        audio_bytes = await audio.read()
        save_path.write_bytes(audio_bytes)

        # Transcribe with Whisper
        loop = asyncio.get_running_loop()
        state_mgr.set_state(UIState.PROCESSING, "Transcribing mobile speech with Faster-Whisper...")
        await state_mgr.broadcast_state()

        try:
            user_text, detected_lang, prob = await loop.run_in_executor(
                None, voice_stt.transcribe, save_path
            )
        except Exception as e:
            logger.error(f"Mobile voice transcription failed: {e}")
            state_mgr.set_state(UIState.ERROR, f"Transcription error: {e}")
            await state_mgr.broadcast_state()
            return {"status": "error", "message": f"Transcription failed: {e}", "user_text": ""}

        if not user_text.strip():
            state_mgr.set_state(UIState.IDLE, "No clear speech detected from mobile.")
            await state_mgr.broadcast_state()
            return {
                "status": "empty",
                "user_text": "",
                "reply": "I did not detect any speech from your device, Sir.",
                "audio_url": None,
            }

        # Execute through AutomationAgent
        state_mgr.set_state(UIState.THINKING, f"Mobile Command: '{user_text}'")
        await state_mgr.broadcast_state()

        try:
            reply, actions = await loop.run_in_executor(
                None, automation_agent.execute_user_command, user_text
            )

            # Synthesize reply for mobile playback
            audio_url = None
            if speak and reply:
                state_mgr.set_state(UIState.SPEAKING, "Synthesizing spoken response for mobile...")
                await state_mgr.broadcast_state()
                audio_file = await loop.run_in_executor(
                    None, voice_tts.synthesize, reply
                )
                audio_url = f"/api/voice/audio/{audio_file.name}"

            state_mgr.set_state(UIState.IDLE, "Standing by, Sir.")
            await state_mgr.broadcast_state()

            return {
                "status": "success",
                "user_text": user_text,
                "detected_lang": detected_lang,
                "reply": reply,
                "actions": actions,
                "audio_url": audio_url,
            }
        except Exception as e:
            logger.error(f"Mobile command execution error: {e}")
            state_mgr.set_state(UIState.ERROR, f"Error: {e}")
            await state_mgr.broadcast_state()
            return {
                "status": "error",
                "user_text": user_text,
                "reply": f"An error occurred, Sir: {e}",
                "actions": [],
                "audio_url": None,
            }

    # --- REST Endpoints ---

    @app.get("/api/telemetry")
    async def get_telemetry() -> Dict[str, Any]:
        """Fetch current system statistics."""
        data = state_mgr.update_telemetry()
        return {
            "status": "success",
            "telemetry": data,
            "ai_state": state_mgr.current_state,
            "state_message": state_mgr.state_message,
            "ai_provider": getattr(automation_agent.conv.provider, "name", "ollama").upper(),
            "ai_model": getattr(automation_agent.conv.provider, "model_name", "qwen2.5:1.5b"),
        }

    @app.get("/api/state")
    async def get_state() -> Dict[str, Any]:
        """Fetch current AI state and recent activity."""
        return {
            "state": state_mgr.current_state,
            "message": state_mgr.state_message,
            "active_action": state_mgr.active_action,
            "action_history": state_mgr.action_history[:20],
            "emergency_stop": EmergencyStopManager.get_instance().is_stopped(),
            "voice_output_enabled": state_mgr.voice_output_enabled,
        }

    @app.post("/api/emergency-stop/trigger")
    async def trigger_emergency_stop() -> Dict[str, Any]:
        """Trigger emergency stop killswitch."""
        EmergencyStopManager.get_instance().trigger_stop("UI Emergency Stop button pressed")
        state_mgr.set_state(UIState.ERROR, "EMERGENCY STOP ACTIVATED: All automation halted immediately.")
        state_mgr.add_action("emergency_stop", {}, "STOPPED", "Emergency stop killswitch triggered by user.")
        await state_mgr.broadcast_state()
        return {
            "status": "stopped",
            "message": "Emergency stop activated immediately, Sir. All ongoing automation has been halted.",
        }

    @app.post("/api/emergency-stop/reset")
    async def reset_emergency_stop() -> Dict[str, Any]:
        """Reset emergency stop killswitch."""
        EmergencyStopManager.get_instance().reset()
        state_mgr.set_state(UIState.IDLE, "Emergency stop reset. All automation systems online.")
        state_mgr.add_action("reset_killswitch", {}, "ACTIVE", "Emergency stop reset. Systems restored.")
        await state_mgr.broadcast_state()
        return {
            "status": "active",
            "message": "Emergency stop has been reset, Sir. Desktop automation is now ready.",
        }

    @app.post("/api/chat")
    async def handle_chat(req: ChatRequest, request: Request) -> Dict[str, Any]:
        """Process a text command via Claude AI and Automation Agent."""
        auth_mgr = MobileAuthManager.get_instance()
        if not auth_mgr.is_request_authenticated(request):
            raise HTTPException(
                status_code=401,
                detail="Mobile Pairing Authentication Required. Enter the 6-digit PIN shown on your Laptop HUD.",
            )

        user_msg = req.message.strip()
        if not user_msg:
            return {"reply": "", "actions": [], "status": "empty"}

        # 1. Update state to THINKING
        state_mgr.set_state(UIState.THINKING, f"Analyzing: '{user_msg[:30]}...'")
        await state_mgr.broadcast_state()

        try:
            # Check for direct emergency stop intent
            if any(term in user_msg.lower() for term in ("emergency stop", "stop immediately", "abort all")):
                EmergencyStopManager.get_instance().trigger_stop("User chat emergency stop")
                state_mgr.set_state(UIState.ERROR, "EMERGENCY STOP ACTIVATED.")
                state_mgr.add_action("emergency_stop", {}, "STOPPED", "Emergency stop triggered via chat command.")
                await state_mgr.broadcast_state()
                return {
                    "reply": "Emergency stop activated, Sir. All ongoing automation has been halted immediately.",
                    "actions": [{"tool": "emergency_stop", "success": True}],
                    "emergency_stop": True,
                }

            # 2. Execute via AutomationAgent (runs tools + Claude)
            reply, actions = automation_agent.execute_user_command(user_msg)

            # Record actions
            if actions:
                state_mgr.set_state(UIState.EXECUTING, f"Executed {len(actions)} action(s).")
                for act in actions:
                    t_name = act.get("tool", "action")
                    t_res = act.get("result", {})
                    t_success = "SUCCESS" if (isinstance(t_res, dict) and t_res.get("success", True)) else "FAILED"
                    t_msg = t_res.get("message", "Completed") if isinstance(t_res, dict) else str(t_res)
                    state_mgr.add_action(t_name, act.get("input", {}), t_success, t_msg)
                await state_mgr.broadcast_state()

            # 3. Optional Voice Speaking
            should_speak = req.speak if req.speak is not None else state_mgr.voice_output_enabled
            if should_speak and reply:
                state_mgr.set_state(UIState.SPEAKING, "Speaking response aloud...")
                await state_mgr.broadcast_state()
                # Run speech in thread to avoid blocking loop
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, voice_tts.speak, reply)

            state_mgr.set_state(UIState.IDLE, "Standing by, Sir.")
            await state_mgr.broadcast_state()

            return {
                "reply": reply,
                "actions": actions,
                "status": "success",
                "emergency_stop": EmergencyStopManager.get_instance().is_stopped(),
            }

        except Exception as e:
            logger.error(f"Error handling chat command: {e}")
            state_mgr.set_state(UIState.ERROR, f"Error: {e}")
            await state_mgr.broadcast_state()
            return {
                "reply": f"An error occurred, Sir: {e}",
                "actions": [],
                "status": "error",
                "error": str(e),
            }

    @app.post("/api/voice/listen")
    async def handle_voice_listen(req: VoiceListenRequest, request: Request) -> Dict[str, Any]:
        """Record audio from user's microphone, transcribe with Whisper, and execute."""
        auth_mgr = MobileAuthManager.get_instance()
        if not auth_mgr.is_request_authenticated(request):
            raise HTTPException(
                status_code=401,
                detail="Mobile Pairing Authentication Required. Enter the 6-digit PIN shown on your Laptop HUD.",
            )

        state_mgr.set_state(UIState.LISTENING, "Listening to microphone input (Speak now)...")
        await state_mgr.broadcast_state()

        loop = asyncio.get_running_loop()

        # 1. Record audio in thread
        try:
            audio_path = await loop.run_in_executor(
                None,
                lambda: record_until_silence(
                    max_seconds=req.max_seconds,
                    silence_seconds=1.5,
                    silence_threshold=400,
                    startup_silence_seconds=3.5,
                ),
            )
        except Exception as e:
            state_mgr.set_state(UIState.ERROR, f"Microphone error: {e}")
            await state_mgr.broadcast_state()
            return {"status": "error", "message": f"Microphone capture failed: {e}", "user_text": ""}

        # 2. Transcribe with Whisper
        state_mgr.set_state(UIState.PROCESSING, "Transcribing speech with Faster-Whisper...")
        await state_mgr.broadcast_state()

        try:
            user_text, detected_lang, prob = await loop.run_in_executor(
                None, voice_stt.transcribe, audio_path
            )
        except Exception as e:
            state_mgr.set_state(UIState.ERROR, f"Transcription error: {e}")
            await state_mgr.broadcast_state()
            return {"status": "error", "message": f"Speech transcription failed: {e}", "user_text": ""}

        if not user_text.strip():
            state_mgr.set_state(UIState.IDLE, "No clear speech detected. Standing by.")
            await state_mgr.broadcast_state()
            return {
                "status": "empty",
                "user_text": "",
                "reply": "I did not detect any speech, Sir. Please try again.",
            }

        # 3. Process via AutomationAgent
        state_mgr.set_state(UIState.THINKING, f"Analyzing: '{user_text}'")
        await state_mgr.broadcast_state()

        try:
            reply, actions = await loop.run_in_executor(
                None, automation_agent.execute_user_command, user_text
            )

            if actions:
                state_mgr.set_state(UIState.EXECUTING, f"Executed {len(actions)} action(s).")
                for act in actions:
                    t_name = act.get("tool", "action")
                    t_res = act.get("result", {})
                    t_success = "SUCCESS" if (isinstance(t_res, dict) and t_res.get("success", True)) else "FAILED"
                    t_msg = t_res.get("message", "Completed") if isinstance(t_res, dict) else str(t_res)
                    state_mgr.add_action(t_name, act.get("input", {}), t_success, t_msg)
                await state_mgr.broadcast_state()

            # 4. Speak response aloud
            should_speak = req.speak if req.speak is not None else state_mgr.voice_output_enabled
            if should_speak and reply:
                state_mgr.set_state(UIState.SPEAKING, "Speaking response aloud...")
                await state_mgr.broadcast_state()
                await loop.run_in_executor(None, voice_tts.speak, reply)

            state_mgr.set_state(UIState.IDLE, "Standing by, Sir.")
            await state_mgr.broadcast_state()

            return {
                "status": "success",
                "user_text": user_text,
                "detected_lang": detected_lang,
                "reply": reply,
                "actions": actions,
            }

        except Exception as e:
            logger.error(f"Voice interaction execution error: {e}")
            state_mgr.set_state(UIState.ERROR, f"Error: {e}")
            await state_mgr.broadcast_state()
            return {
                "status": "error",
                "user_text": user_text,
                "reply": f"An error occurred, Sir: {e}",
                "actions": [],
            }

    # --- Mobile Notification & Auto-Reply Endpoints ---

    @app.post("/api/notifications/ingest")
    async def ingest_notification(req: IngestNotificationRequest, request: Request) -> Dict[str, Any]:
        """Ingest incoming notification from mobile phone (WhatsApp, Telegram, SMS, etc.)."""
        auth_mgr = MobileAuthManager.get_instance()
        if not auth_mgr.is_request_authenticated(request):
            raise HTTPException(status_code=401, detail="Authentication required to ingest notifications.")

        notif_hub = NotificationHub.get_instance()
        accepted, notif, msg = notif_hub.ingest_notification(
            app=req.app,
            sender=req.sender,
            content=req.content,
            timestamp=req.timestamp,
        )

        if accepted and notif:
            # Broadcast to HUD via WebSocket
            await state_mgr.broadcast({
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
        """Retrieve active notifications and unread count."""
        hub = NotificationHub.get_instance()
        return {
            "status": "success",
            "notifications": hub.get_notifications(unread_only=unread_only, limit=limit),
            "unread_count": hub.get_unread_count(),
        }

    @app.post("/api/notifications/clear")
    async def clear_notifications() -> Dict[str, Any]:
        """Mark all notifications as read or clear feed."""
        hub = NotificationHub.get_instance()
        hub.clear()
        await state_mgr.broadcast({
            "type": "notifications_cleared",
            "unread_count": 0,
        })
        return {"status": "success", "message": "All notifications cleared."}

    @app.get("/api/settings/auto-reply")
    async def get_auto_reply_settings() -> Dict[str, Any]:
        """Get current auto-reply settings."""
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
        """Update auto-reply settings."""
        auth_mgr = MobileAuthManager.get_instance()
        if not auth_mgr.is_request_authenticated(request):
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
        await state_mgr.broadcast({
            "type": "settings_updated",
            "auto_reply": {
                "enabled": engine.config.enabled,
                "greeting_auto_reply_enabled": engine.config.greeting_auto_reply_enabled,
                "allowed_apps": list(engine.config.allowed_apps),
            },
        })
        return {"status": "success", "message": "Auto-reply configuration updated successfully."}

    # --- WebSocket Channel ---

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        await state_mgr.register_ws(ws)
        try:
            notif_hub = NotificationHub.get_instance()
            auto_reply_eng = AutoReplyEngine.get_instance()
            # Send initial state snapshot
            await ws.send_json({
                "type": "init",
                "state": state_mgr.current_state,
                "message": state_mgr.state_message,
                "active_action": state_mgr.active_action,
                "action_history": state_mgr.action_history[:25],
                "telemetry": state_mgr.update_telemetry(),
                "voice_output_enabled": state_mgr.voice_output_enabled,
                "emergency_stop": EmergencyStopManager.get_instance().is_stopped(),
                "notifications": notif_hub.get_notifications(limit=15),
                "unread_count": notif_hub.get_unread_count(),
                "auto_reply": {
                    "enabled": auto_reply_eng.config.enabled,
                    "greeting_auto_reply_enabled": auto_reply_eng.config.greeting_auto_reply_enabled,
                    "allowed_apps": list(auto_reply_eng.config.allowed_apps),
                },
            })

            while True:
                data = await ws.receive_json()
                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await ws.send_json({"type": "pong"})

                elif msg_type == "emergency_stop":
                    EmergencyStopManager.get_instance().trigger_stop("WebSocket emergency stop")
                    state_mgr.set_state(UIState.ERROR, "EMERGENCY STOP ACTIVATED.")
                    state_mgr.add_action("emergency_stop", {}, "STOPPED", "Emergency stop triggered via WebSocket.")
                    await state_mgr.broadcast_state()

                elif msg_type == "reset_emergency_stop":
                    EmergencyStopManager.get_instance().reset()
                    state_mgr.set_state(UIState.IDLE, "Emergency stop reset.")
                    state_mgr.add_action("reset_killswitch", {}, "ACTIVE", "Emergency stop reset.")
                    await state_mgr.broadcast_state()

                elif msg_type == "toggle_voice_output":
                    state_mgr.voice_output_enabled = bool(data.get("enabled", True))
                    await state_mgr.broadcast({
                        "type": "voice_toggle",
                        "enabled": state_mgr.voice_output_enabled,
                    })

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.debug(f"WebSocket closed: {e}")
        finally:
            await state_mgr.unregister_ws(ws)

    return app
