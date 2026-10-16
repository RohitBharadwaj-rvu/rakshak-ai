import pytest
from scripts.compute_metrics import compute_metrics


def test_compute_metrics_perfect_run():
    ground_truth = {
        "scam_1": {"type": "scam"},
        "scam_2": {"type": "scam"},
        "gen_1": {"type": "genuine"},
        "gen_2": {"type": "genuine"},
    }
    records = [
        {"scenario_id": "scam_1", "final_verdict": "scam", "switched_to_honeypot": "True", "bait_leaks": 0, "adversarial_leaks": 0, "total_turns": 6},
        {"scenario_id": "scam_2", "final_verdict": "scam", "switched_to_honeypot": "True", "bait_leaks": 0, "adversarial_leaks": 0, "total_turns": 8},
        {"scenario_id": "gen_1", "final_verdict": "genuine", "switched_to_honeypot": "False", "bait_leaks": 0, "adversarial_leaks": 0, "total_turns": 4},
        {"scenario_id": "gen_2", "final_verdict": "genuine", "switched_to_honeypot": "False", "bait_leaks": 0, "adversarial_leaks": 0, "total_turns": 4},
    ]

    metrics = compute_metrics(records, ground_truth)
    assert metrics["summary"]["overall_pass"] is True
    assert metrics["metrics"]["scam_detection_rate_pct"] == 100.0
    assert metrics["metrics"]["false_positive_rate_pct"] == 0.0
    assert metrics["metrics"]["total_bait_leaks"] == 0
    assert metrics["metrics"]["total_adversarial_leaks"] == 0
    assert metrics["metrics"]["avg_scammer_turns_sustained"] == 7.0


def test_compute_metrics_fails_on_leak():
    ground_truth = {"scam_1": {"type": "scam"}}
    records = [
        {"scenario_id": "scam_1", "final_verdict": "scam", "switched_to_honeypot": "True", "bait_leaks": 1, "adversarial_leaks": 0, "total_turns": 4}
    ]

    metrics = compute_metrics(records, ground_truth)
    assert metrics["summary"]["overall_pass"] is False
    assert metrics["pass_bars"]["zero_bait_leaks"] is False
