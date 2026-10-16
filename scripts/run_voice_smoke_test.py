#!/usr/bin/env python3
"""
scripts/run_voice_smoke_test.py - Run and Evaluate T-VOICE Audio Smoke Set.

Executes the 5-call telephony audio smoke suite against:
  1. Audio file format integrity (8kHz mono 16-bit PCM WAV)
  2. Sequential turn classification & honeypot transition
  3. Zero bait leak and zero adversarial OTP/Aadhaar leak verification

Enforces the Sprint 2 Gate:
  "T-VOICE smoke set: the reliability checks pass on all 5 calls."
"""

import json
import os
import sys
import wave
from typing import Any, Dict

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from app.voice.classifier import classify_caller
from scripts.text_harness import default_guardian_agent_policy, check_bait_safety, check_adversarial_safety, APPROVED_BAIT

VOICE_DIR = os.path.join(ROOT_DIR, "evaluation", "voice")
MANIFEST_PATH = os.path.join(VOICE_DIR, "smoke_manifest.json")
RESULTS_PATH = os.path.join(VOICE_DIR, "smoke_results.json")


def validate_wav_audio(wav_path: str) -> Dict[str, Any]:
    """Verifies telephony audio meets standard 8kHz 16-bit mono PCM specifications."""
    assert os.path.exists(wav_path), f"Missing audio file: {wav_path}"
    with wave.open(wav_path, "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        frames = wf.getnframes()
        duration_s = frames / float(framerate)

    assert channels == 1, f"Expected mono audio, got {channels} channels"
    assert sampwidth == 2, f"Expected 16-bit audio, got {sampwidth * 8} bits"
    assert framerate == 8000, f"Expected 8000Hz telephony sample rate, got {framerate}Hz"

    return {
        "channels": channels,
        "sample_rate_hz": framerate,
        "bit_depth": sampwidth * 8,
        "duration_sec": round(duration_s, 2),
    }


def run_voice_smoke_suite():
    if not os.path.exists(MANIFEST_PATH):
        from scripts.generate_voice_smoke_set import build_voice_smoke_set
        build_voice_smoke_set()

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    calls = manifest.get("calls", [])
    results = []
    all_passed = True

    approved_digits = [p["account_number"] for p in APPROVED_BAIT.values()]

    print("\n" + "=" * 70)
    print("           GUARDIANLINE T-VOICE AUDIO SMOKE TEST RUN")
    print("=" * 70)

    for c in calls:
        call_id = c["call_id"]
        wav_file = os.path.join(VOICE_DIR, c["audio_file"])
        audio_info = validate_wav_audio(wav_file)

        state = {
            "call_id": call_id,
            "mode": "screening",
            "conversation": [],
            "bait_leaks": 0,
            "adversarial_leaks": 0,
            "switched_to_honeypot": False,
        }

        # Step through dialogue turns
        for t in c["turns"]:
            caller_text = t["content"]
            agent_resp = default_guardian_agent_policy(state, caller_text, {"language": c["language"]})
            agent_text = agent_resp.get("text", "")

            if not check_bait_safety(agent_text, approved_digits):
                state["bait_leaks"] += 1
            if not check_adversarial_safety(agent_text, caller_text):
                state["adversarial_leaks"] += 1
            if agent_resp.get("mode") == "honeypot":
                state["switched_to_honeypot"] = True

        final_verdict = state.get("last_verdict", "unsure")
        expected_verdict = c["expected_verdict"]

        verdict_ok = final_verdict == expected_verdict
        safety_ok = state["bait_leaks"] == 0 and state["adversarial_leaks"] == 0
        call_passed = verdict_ok and safety_ok
        if not call_passed:
            all_passed = False

        status_tag = "[PASS]" if call_passed else "[FAIL]"
        print(f"  {status_tag} {call_id:<32} | Exp: {expected_verdict:<8} | Got: {final_verdict:<8} | Honeypot: {str(state['switched_to_honeypot']):<5} | Audio: {audio_info['sample_rate_hz']}Hz/{audio_info['duration_sec']}s")

        results.append({
            "call_id": call_id,
            "name": c["name"],
            "expected_verdict": expected_verdict,
            "final_verdict": final_verdict,
            "switched_to_honeypot": state["switched_to_honeypot"],
            "bait_leaks": state["bait_leaks"],
            "adversarial_leaks": state["adversarial_leaks"],
            "audio_specs": audio_info,
            "passed": call_passed,
        })

    print("-" * 70)
    suite_status = "[SUCCESS] T-VOICE RELIABILITY CHECKS PASSED (5/5)" if all_passed else "[FAILED] SMOKE CALLS FAILED"
    print(f"Suite Status: {suite_status}")
    print("=" * 70 + "\n")

    report = {
        "total_calls": len(calls),
        "passed_calls": sum(1 for r in results if r["passed"]),
        "all_passed": all_passed,
        "results": results,
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as rf:
        json.dump(report, rf, indent=2)
    print(f"[VoiceSmoke] Saved smoke results to {RESULTS_PATH}")

    return report


if __name__ == "__main__":
    run_voice_smoke_suite()
