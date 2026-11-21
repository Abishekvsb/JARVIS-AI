"""Stage D Live Verification Test Suite for Local Ollama Brain Integration.

Runs actual live inference against local Ollama running 'qwen2.5:1.5b' on Drive D:.
Tests:
1. Health & Model Discovery
2. English, Tanglish, and Tamil Conversational Generation
3. Multi-turn Context Memory
4. Allowlisted Tool Calling (Screenshot tool)
5. Safety controls (Arbitrary command block & Emergency Stop)
6. Voice Pipeline (Whisper -> Ollama -> Edge TTS)
"""

import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.config import get_config, JarvisConfig, JARVIS_ROOT, CACHE_DIR
from jarvis.conversation import JarvisConversation
from jarvis.providers.ollama_provider import LocalOllamaProvider
from jarvis.automation.agent import AutomationAgent
from jarvis.automation.safety import (
    EmergencyStopManager,
    PermissionGuard,
    EmergencyStopException,
    PermissionDeniedException,
)
from jarvis.voice.stt import JarvisSTT
from jarvis.voice.tts import JarvisTTS


def run_stage_d_tests():
    print("=" * 70)
    print("JARVIS PHASE 7: STAGE D LIVE VERIFICATION")
    print("Local AI Brain (Ollama) with qwen2.5:1.5b on Drive D:")
    print("=" * 70)

    config = get_config()
    print(f"Config AI Provider : {config.ai_provider}")
    print(f"Config Model       : {config.ollama_model}")
    print(f"Config Base URL    : {config.ollama_base_url}")
    print(f"Ollama Models Dir  : {config.ollama_models_dir}")

    results = {}

    # -------------------------------------------------------------
    # 1. Health & Model Discovery
    # -------------------------------------------------------------
    print("\n--- Test 1: Provider Health & Model Discovery ---")
    provider = LocalOllamaProvider(
        model=config.ollama_model,
        base_url=config.ollama_base_url,
    )
    is_healthy, health_msg = provider.check_health()
    print(f"Health Status: {is_healthy} -> {health_msg}")
    models = provider.list_installed_models()
    print(f"Installed Models: {models}")

    assert is_healthy, f"Ollama is not healthy: {health_msg}"
    assert any("qwen2.5:1.5b" in m for m in models), f"qwen2.5:1.5b not found in {models}"
    results["Test 1: Health & Models"] = "PASS"

    # -------------------------------------------------------------
    # 2. Conversational Generation (English, Tanglish, Tamil)
    # -------------------------------------------------------------
    print("\n--- Test 2: Multilingual Conversational Generation ---")
    conv = JarvisConversation(config=config, provider=provider)

    # 2A: English
    t0 = time.time()
    reply_en = conv.ask("Hello Jarvis, introduce yourself in one short sentence.")
    dt_en = time.time() - t0
    print(f"[English Prompt] -> 'Hello Jarvis, introduce yourself in one short sentence.'")
    print(f"[JARVIS Reply ({dt_en:.2f}s)]: {reply_en}\n")
    assert len(reply_en.strip()) > 5, "English reply was empty or too short"

    # 2B: Tanglish
    t0 = time.time()
    reply_tanglish = conv.ask("Jarvis, innaiku work schedule enna? Briefly tell me in one sentence.")
    dt_tanglish = time.time() - t0
    print(f"[Tanglish Prompt] -> 'Jarvis, innaiku work schedule enna? Briefly tell me in one sentence.'")
    print(f"[JARVIS Reply ({dt_tanglish:.2f}s)]: {reply_tanglish}\n")
    assert len(reply_tanglish.strip()) > 5, "Tanglish reply was empty or too short"

    # 2C: Tamil
    t0 = time.time()
    reply_ta = conv.ask("வணக்கம் ஜார்விஸ், நீங்கள் எனக்கு எவ்வாறு உதவ முடியும்?")
    dt_ta = time.time() - t0
    print(f"[Tamil Prompt] -> 'வணக்கம் ஜார்விஸ், நீங்கள் எனக்கு எவ்வாறு உதவ முடியும்?'")
    print(f"[JARVIS Reply ({dt_ta:.2f}s)]: {reply_ta}\n")
    assert len(reply_ta.strip()) > 5, "Tamil reply was empty or too short"

    results["Test 2: Multilingual Generation (EN/Tanglish/TA)"] = "PASS"

    # -------------------------------------------------------------
    # 3. Multi-turn Context Memory
    # -------------------------------------------------------------
    print("\n--- Test 3: Multi-turn Context Memory ---")
    conv_multi = JarvisConversation(config=config, provider=provider)
    r1 = conv_multi.ask("Sir's primary project codename is Project Stark. Remember this.")
    print(f"[Turn 1] -> {r1}")
    r2 = conv_multi.ask("What is my primary project codename?")
    print(f"[Turn 2] -> {r2}")
    assert "stark" in r2.lower(), f"Failed to retain multi-turn context! Response was: {r2}"
    results["Test 3: Multi-turn Context"] = "PASS"

    # -------------------------------------------------------------
    # 4. Allowlisted Tool Calling (Screenshot tool)
    # -------------------------------------------------------------
    print("\n--- Test 4: Desktop Tool Calling via Local Ollama ---")
    agent = AutomationAgent(conversation=conv)
    agent_reply, actions = agent.execute_user_command("Jarvis, take a screenshot of my screen right now.")
    print(f"[Tool Execution Result]: {agent_reply}")
    print(f"[Actions Executed]: {actions}")

    # Check that a screenshot was actually generated in D:\JARVIS\screenshots
    screenshots = list((config.project_root / "screenshots").glob("*.png"))
    print(f"Screenshots count: {len(screenshots)}")
    assert len(screenshots) > 0, "No screenshot found in D:\\JARVIS\\screenshots"
    results["Test 4: Allowlisted Tool Calling (Screenshot)"] = "PASS"

    # -------------------------------------------------------------
    # 5. Safety Controls Verification
    # -------------------------------------------------------------
    print("\n--- Test 5: Safety Controls & Killswitch ---")
    guard = PermissionGuard()
    esm = EmergencyStopManager.get_instance()
    esm.reset()

    # 5A: Sensitive action block without confirmation
    blocked = False
    try:
        guard.verify_action("delete_file", {"path": "D:\\test.txt"})
    except PermissionDeniedException:
        blocked = True
    print(f"Sensitive action delete_file blocked by default: {blocked}")
    assert blocked, "PermissionGuard did not block sensitive delete_file!"

    # 5B: Emergency Stop killswitch
    assert not esm.is_stopped()
    esm.trigger_stop("Stage D Test Killswitch")
    assert esm.is_stopped()

    stopped_blocked = False
    try:
        esm.assert_can_proceed()
    except EmergencyStopException:
        stopped_blocked = True
    assert stopped_blocked, "EmergencyStopException was not raised while stopped!"
    print("Emergency stop successfully blocked execution.")

    esm.reset()
    assert not esm.is_stopped()
    print("Emergency stop reset verified.")
    results["Test 5: Safety Controls & Killswitch"] = "PASS"

    # -------------------------------------------------------------
    # 6. Voice Pipeline with Local Ollama
    # -------------------------------------------------------------
    print("\n--- Test 6: Voice Pipeline Integration (STT -> Ollama -> TTS) ---")
    tts = JarvisTTS()
    test_voice_file = tts.synthesize("Jarvis, what is two plus two?")
    assert test_voice_file.exists() and test_voice_file.stat().st_size > 0

    # STT Transcribe
    stt = JarvisSTT()
    transcription, detected_lang, prob = stt.transcribe(test_voice_file)
    print(f"[Whisper STT Transcribed]: '{transcription}' (lang={detected_lang}, prob={prob:.2f})")
    assert len(transcription.strip()) > 0

    # Local Ollama Answer
    ollama_answer = conv.ask(transcription)
    print(f"[Local Ollama Response]: {ollama_answer}")
    assert len(ollama_answer.strip()) > 0

    # Neural TTS Speak
    reply_voice_file = tts.synthesize(ollama_answer)
    assert reply_voice_file.exists() and reply_voice_file.stat().st_size > 0
    print(f"[Neural TTS Synthesized]: {reply_voice_file} ({reply_voice_file.stat().st_size} bytes)")
    results["Test 6: Voice Pipeline Integration"] = "PASS"

    # -------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------
    print("\n" + "=" * 70)
    print("STAGE D LIVE TEST SUMMARY:")
    print("=" * 70)
    all_passed = True
    for test_name, status in results.items():
        print(f"  {test_name.ljust(50)}: [{status}]")
        if status != "PASS":
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("ALL STAGE D VERIFICATION TESTS PASSED SUCCESSFULLY!")
    else:
        print("SOME TESTS FAILED.")
    print("=" * 70)
    return all_passed


if __name__ == "__main__":
    success = run_stage_d_tests()
    sys.exit(0 if success else 1)
