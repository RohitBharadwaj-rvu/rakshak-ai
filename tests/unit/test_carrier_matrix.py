import json
import os
import pytest

CARRIER_RESULTS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "evaluation", "carrier_results.json"
)


def test_carrier_results_schema_and_pass_bars():
    assert os.path.exists(CARRIER_RESULTS_PATH), "carrier_results.json must exist"

    with open(CARRIER_RESULTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["gate_1_verdict"]["status"] == "GO"
    assert "app_mode" in data["gate_1_verdict"]["supported_modes"]
    assert "basic_mode" in data["gate_1_verdict"]["supported_modes"]

    carriers = ["jio", "airtel", "vi"]
    for c in carriers:
        assert c in data["carriers"], f"Missing carrier: {c}"
        carrier_info = data["carriers"][c]
        tests = carrier_info["tests"]

        # Tests 1-4
        for t_name in [
            "test_1_manual_decline",
            "test_2_app_rejection",
            "test_3_caller_id_retention",
            "test_4_unanswered_rollover",
        ]:
            assert t_name in tests, f"Missing {t_name} in {c}"
            t_obj = tests[t_name]
            assert t_obj["attempts"] == 3
            assert t_obj["successes"] == 3
            assert t_obj["status"] == "PASS"
            assert t_obj["caller_id_retained"] is True
