#!/usr/bin/env python3
"""
scripts/run_voice_smoke_test.py - DEPRECATED / ALIAS to scripts/run_audio_format_check.py

[AUDIT NOTICE]
This script has been relabeled to run_audio_format_check.py.
The 5 WAV files in evaluation/voice/ are synthetic sine tones verifying 8kHz mono PCM
telephony container formatting. This script evaluates text from the manifest, NOT
live acoustic speech-to-text (STT) transcription.
"""

import sys
import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from scripts.run_audio_format_check import validate_wav_audio, run_audio_format_check_suite as run_voice_smoke_suite

if __name__ == "__main__":
    print("[NOTICE] Running audio format and codec verification (formerly voice smoke test)...")
    rep = run_voice_smoke_suite()
    sys.exit(0 if rep["all_passed"] else 1)
