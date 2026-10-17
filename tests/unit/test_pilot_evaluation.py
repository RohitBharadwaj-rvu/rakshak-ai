import json
import os
import pytest

PILOT_RESULTS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "evaluation", "pilot_results.json"
)


def test_pilot_evaluation_meets_pass_bar():
    assert os.path.exists(PILOT_RESULTS_PATH), "pilot_results.json must exist"

    with open(PILOT_RESULTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    summary = data["cohort_summary"]
    metrics = data["metrics"]
    participants = data["participants"]

    # Pass bar 1: At least 5 participants
    assert summary["completed_participants"] >= 5
    assert len(participants) >= 5

    # Pass bar 2: At least 15 genuine calls
    assert metrics["total_calls"] >= 15

    # Pass bar 3: 100% consent recorded before test calls
    assert summary["consent_recorded_percentage"] == 100.0
    for p in participants:
        assert p["consent_form_signed"] is True, f"Participant {p['id']} missing consent"

    # Pass bar 4: False positives tracked and under 10%
    assert metrics["false_positive_rate"] <= 0.10
    assert metrics["scam_false_positives"] == 0
