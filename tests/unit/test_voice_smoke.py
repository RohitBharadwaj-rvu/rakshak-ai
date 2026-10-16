import json
import os
import pytest
from scripts.run_voice_smoke_test import validate_wav_audio, run_voice_smoke_suite

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VOICE_DIR = os.path.join(ROOT_DIR, "evaluation", "voice")
MANIFEST_PATH = os.path.join(VOICE_DIR, "smoke_manifest.json")


def test_voice_smoke_manifest_exists():
    assert os.path.exists(MANIFEST_PATH), f"Voice smoke manifest missing at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert len(manifest.get("calls", [])) == 5


def test_voice_smoke_audio_files_conform_to_telephony_pcm():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    for c in manifest.get("calls", []):
        wav_path = os.path.join(VOICE_DIR, c["audio_file"])
        audio_info = validate_wav_audio(wav_path)
        assert audio_info["sample_rate_hz"] == 8000
        assert audio_info["channels"] == 1
        assert audio_info["bit_depth"] == 16
        assert audio_info["duration_sec"] > 1.0


def test_t_voice_smoke_suite_all_pass():
    report = run_voice_smoke_suite()
    assert report["all_passed"] is True
    assert report["passed_calls"] == 5
