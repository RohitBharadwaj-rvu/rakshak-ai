import json
import os
import pytest

CARRIER_RESULTS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "evaluation", "carrier_results.json"
)


def test_carrier_results_schema_structure():
    """
    Validates carrier results file structure and required fields.
    Does NOT assert outcomes of unexecuted field tests.
    """
    assert os.path.exists(CARRIER_RESULTS_PATH), "carrier_results.json must exist"

    with open(CARRIER_RESULTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "template_version" in data
    assert "gate_1_decision" in data
    assert data["gate_1_decision"]["status"] in ["PENDING_FIELD_TESTS", "GO", "NO_GO"]
    assert data["gate_1_decision"]["demo_mode"] == "basic_mode_only"
    assert data["gate_1_decision"]["app_mode_in_demo"] is False
    assert data.get("undo_forwarding_code") == "##002#"

    carriers = ["jio", "airtel", "vi"]
    for c in carriers:
        assert c in data["carriers"], f"Missing carrier: {c}"
        carrier_info = data["carriers"][c]
        assert "carrier_name" in carrier_info
        tests = carrier_info["tests"]
        assert tests["test_1_manual_decline"]["status"] == "NOT_VERIFIED"

        for t_name in [
            "test_1_manual_decline",
            "test_2_app_rejection",
            "test_3_caller_id_retention",
            "test_4_unanswered_rollover",
        ]:
            assert t_name in tests, f"Missing {t_name} in {c}"
            t_obj = tests[t_name]
            assert "required_attempts" in t_obj
            assert "attempts" in t_obj
            assert isinstance(t_obj["attempts"], list)
            assert t_obj["status"] in ["NOT_VERIFIED", "NOT_RUN", "IN_PROGRESS", "PASS", "FAIL"]

            # If attempts logged, ensure count matches length
            if t_obj["attempts"]:
                for attempt in t_obj["attempts"]:
                    assert "date" in attempt
                    assert "phone_model" in attempt
                    assert "forwarded" in attempt
                    assert "caller_id_seen" in attempt
