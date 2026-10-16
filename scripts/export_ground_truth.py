#!/usr/bin/env python3
"""
scripts/export_ground_truth.py - Generate Unified Ground-Truth Registry for Evaluation.

Aggregates all scam, genuine, and red-team caller scenarios in `evaluation/scenarios/`
into a unified `evaluation/ground_truth.json` file.
Used by Lane B to benchmark extraction accuracy (T-EXT), number normalization (T-NORM),
and classification metrics (T-CLS) without manual data entry.
"""

import glob
import json
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCENARIOS_DIR = os.path.join(ROOT_DIR, "evaluation", "scenarios")
OUTPUT_PATH = os.path.join(ROOT_DIR, "evaluation", "ground_truth.json")


def generate_ground_truth():
    scenario_files = sorted(glob.glob(os.path.join(SCENARIOS_DIR, "*.json")))
    registry = {
        "metadata": {
            "version": "1.0.0",
            "total_scenarios": len(scenario_files),
            "languages": ["hi", "en", "hinglish"],
        },
        "scenarios": {},
    }

    for fpath in scenario_files:
        with open(fpath, "r", encoding="utf-8") as f:
            sc = json.load(f)

        sc_id = sc["id"]
        planted = sc.get("planted_details", {})
        script = sc.get("caller_script", [])

        # Detect adversarial flags
        intents = [turn.get("intent", "") for turn in script]
        demands_otp = any("otp" in i for i in intents)
        demands_aadhaar = any("aadhaar" in i for i in intents)
        demands_screenshare = any("screenshare" in i for i in intents)
        demands_videocall = any("videocall" in i for i in intents)

        registry["scenarios"][sc_id] = {
            "id": sc_id,
            "name": sc.get("name", ""),
            "language": sc.get("language", "hi"),
            "type": sc.get("type", "scam"),
            "expected_verdict": sc.get("expected_verdict", "scam"),
            "max_turns": sc.get("max_turns", len(script)),
            "planted_upi_ids": planted.get("upi_ids", []),
            "planted_account_numbers": planted.get("account_numbers", []),
            "planted_phone_numbers": planted.get("phone_numbers", []),
            "planted_callback_numbers": planted.get("callback_numbers", []),
            "adversarial_demands": {
                "demands_otp": demands_otp,
                "demands_aadhaar": demands_aadhaar,
                "demands_screenshare": demands_screenshare,
                "demands_videocall": demands_videocall,
            },
            "total_turns": len(script),
        }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
        json.dump(registry, out, indent=2, ensure_ascii=False)

    print(f"[GroundTruth] Exported {len(scenario_files)} labeled scenarios to {OUTPUT_PATH}")
    return registry


if __name__ == "__main__":
    generate_ground_truth()
