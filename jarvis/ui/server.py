"""FastAPI Server and WebSocket Hub for JARVIS Futuristic Desktop UI."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import mimetypes
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jarvis.automation.agent import AutomationAgent
from jarvis.automation.safety import EmergencyStopManager
from jarvis.config import JARVIS_ROOT
from jarvis.conversation import JarvisConversation
from jarvis.ui.state import UIState, UIStateManager
from jarvis.voice.audio_io import play_audio, record_until_silence
from jarvis.voice.stt import JarvisSTT
from jarvis.voice.tts import JarvisTTS

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class ChatRequest(BaseModel):
    message: str
    speak: Optional[bool] = None


class VoiceListenRequest(BaseModel):
    max_seconds: float = 12.0
    speak: Optional[bool] = None


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
    async def handle_chat(req: ChatRequest) -> Dict[str, Any]:
        """Process a text command via Claude AI and Automation Agent."""
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
    async def handle_voice_listen(req: VoiceListenRequest) -> Dict[str, Any]:
        """Record audio from user's microphone, transcribe with Whisper, and execute."""
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

    # --- WebSocket Channel ---

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        await state_mgr.register_ws(ws)
        try:
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
