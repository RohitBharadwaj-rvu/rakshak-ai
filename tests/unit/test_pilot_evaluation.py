import json
import os
import pytest
from datetime import datetime

PILOT_RESULTS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "evaluation", "pilot_results.json"
)


def test_pilot_evaluation_schema_structure():
    """
    Validates pilot results template structure and rules.
    Does NOT assert outcomes of unexecuted field tests.
    """
    assert os.path.exists(PILOT_RESULTS_PATH), "pilot_results.json must exist"

    with open(PILOT_RESULTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "pilot_version" in data
    assert "status" in data
    assert "cohort_target" in data
    assert data["cohort_target"]["min_participants"] == 3
    assert data["cohort_target"]["min_genuine_calls"] >= 9
    assert data["cohort_target"]["consent_required_before_first_call"] is True
    assert isinstance(data["participants"], list)
    if not data["participants"]:
        assert data["status"] == "NOT_DONE"
        assert "not done" in str(data.get("honest_disclosure", "")).lower()


    # When participants are logged by human researchers:
    for p in data["participants"]:
        assert "id" in p
        assert "consent_form_signed" in p
        assert "consent_timestamp" in p
        assert "calls" in p

        # Consent timestamp must precede first call timestamp
        consent_dt = datetime.fromisoformat(p["consent_timestamp"].replace("Z", "+00:00"))
        for call in p["calls"]:
            assert "call_id" in call, "Every test call must link to a CallRecord call_id"
            assert "verdict" in call
            if "timestamp" in call:
                call_dt = datetime.fromisoformat(call["timestamp"].replace("Z", "+00:00"))
                assert consent_dt <= call_dt, f"Consent for {p['id']} was not recorded prior to call {call['call_id']}"
