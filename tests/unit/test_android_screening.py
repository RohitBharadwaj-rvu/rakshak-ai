import json
import os
import pytest

CASES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "screening_cases.json"
)


def test_screening_canonical_cases_file_exists_and_valid():
    assert os.path.exists(CASES_PATH), "screening_cases.json must exist"

    with open(CASES_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    assert len(cases) >= 6, "Must define at least 6 canonical screening cases"

    actions = {c["expected_action"] for c in cases}
    assert "ALLOW" in actions
    assert "SCREEN" in actions

    reasons = {c["expected_reason"] for c in cases}
    assert "SAVED_CONTACT" in reasons
    assert "BOLNA_AGENT_PROXY" in reasons
    assert "UNKNOWN_CALLER_SCREEN" in reasons
    assert "WITHHELD_NUMBER_SCREEN" in reasons
    assert "EMERGENCY_WHITELIST" in reasons

    for case in cases:
        assert "expected_action" in case
        assert "expected_reason" in case
        assert "contacts" in case
        assert isinstance(case["contacts"], list)
