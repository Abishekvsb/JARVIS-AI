"""Live Interactive Verification Script for JARVIS Phase 6 Desktop HUD."""

import json
import time
import urllib.request
import psutil

BASE_URL = "http://127.0.0.1:8000"

def post_json(endpoint: str, data: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get_json(endpoint: str) -> dict:
    req = urllib.request.Request(f"{BASE_URL}{endpoint}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

print("=== STARTING LIVE HUD VERIFICATION ===")

# 1. Telemetry verification
telem = get_json("/api/telemetry")
print(f"\n[1] Telemetry Status: {telem['status']}")
print(f"    CPU: {telem['telemetry']['cpu_percent']}")
print(f"    RAM: {telem['telemetry']['memory_percent']} ({telem['telemetry']['memory_used_gb']} used)")
print(f"    Battery: {telem['telemetry']['battery']}")
print(f"    Drive D: {telem['telemetry']['disk_d_free_gb']}")

# 2. English Chat
print("\n[2] Testing English Chat ...")
c1 = post_json("/api/chat", {"message": "Hello Jarvis, introduce yourself", "speak": False})
print(f"    Reply: {c1['reply']}")

# 3. Automation Application Launch (Notepad)
print("\n[3] Testing Automation: Launch Notepad ...")
c2 = post_json("/api/chat", {"message": "Jarvis, open notepad", "speak": False})
print(f"    Reply: {c2['reply']}")
print(f"    Actions: {c2['actions']}")

# Verify process
time.sleep(1.0)
notepad_procs = [p for p in psutil.process_iter(["name"]) if "notepad" in p.info["name"].lower()]
print(f"    Running Notepad instances: {len(notepad_procs)}")
assert len(notepad_procs) > 0, "Notepad should be running on Windows."

# 4. Tanglish Automation Command (Screenshot)
print("\n[4] Testing Tanglish Automation: Take Screenshot ...")
c3 = post_json("/api/chat", {"message": "Jarvis, screenshot eduthu save pannu", "speak": False})
print(f"    Reply: {c3['reply']}")
print(f"    Actions: {c3['actions']}")

# 5. Tamil Command
print("\n[5] Testing Tamil Language Command ...")
c4 = post_json("/api/chat", {"message": "ஜார்விஸ், வால்யூம் அதிகப்படுத்து", "speak": False})
print(f"    Reply: {c4['reply']}")

# Clean up: close notepad
print("\n[6] Cleaning up Notepad instance ...")
c_close = post_json("/api/chat", {"message": "Jarvis, close notepad", "speak": False})
print(f"    Close Reply: {c_close['reply']}")

# Check UI state
state_data = get_json("/api/state")
print(f"\n[7] Current UI State: {state_data['state']}")
print(f"    Recent Activity Feed Items: {len(state_data['action_history'])}")
for idx, act in enumerate(state_data['action_history'][:4]):
    print(f"      {idx+1}. [{act['status']}] {act['tool']}: {act['message']}")

print("\n=== LIVE HUD VERIFICATION TESTS COMPLETED SUCCESSFULLY ===")

