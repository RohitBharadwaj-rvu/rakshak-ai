import json
import os
import tempfile
import pytest

from scripts.run_held_out_eval import (
    load_held_out_dataset,
    evaluate_scenario,
    compute_held_out_metrics,
    generate_markdown_report,
)


def test_load_held_out_dataset_list():
    sample = [
        {"id": "t1", "expected_verdict": "scam", "turns": []},
        {"id": "t2", "expected_verdict": "genuine", "turns": []},
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(sample, f)
        temp_name = f.name

    try:
        loaded = load_held_out_dataset(temp_name)
        assert len(loaded) == 2
        assert loaded[0]["id"] == "t1"
    finally:
        os.remove(temp_name)


def test_load_held_out_dataset_dict():
    sample = {
        "version": "1.0",
        "scenarios": [
            {"id": "t1", "expected_verdict": "scam", "turns": []},
        ],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(sample, f)
        temp_name = f.name

    try:
        loaded = load_held_out_dataset(temp_name)
        assert len(loaded) == 1
        assert loaded[0]["id"] == "t1"
    finally:
        os.remove(temp_name)


def test_evaluate_scenario_scam():
    scenario = {
        "id": "heldout_test_cbi",
        "category": "police",
        "expected_verdict": "scam",
        "language": "en",
        "turns": [
            {"role": "caller", "content": "This is CBI officer. You are under digital arrest. Transfer fifty thousand rupees right now."}
        ],
    }
    res = evaluate_scenario(scenario)
    assert res["id"] == "heldout_test_cbi"
    assert res["expected_verdict"] == "scam"
    assert res["actual_verdict"] == "scam"
    assert res["is_correct"] is True
    assert res["is_false_negative"] is False


def test_evaluate_scenario_genuine():
    scenario = {
        "id": "heldout_test_clinic",
        "category": "medical",
        "expected_verdict": "genuine",
        "language": "hi",
        "turns": [
            {"role": "caller", "content": "नमस्ते, मैं डॉक्टर क्लिनिक से बोल रहा हूँ। आपका कल का अपॉइंटमेंट कन्फर्म है, पुरानी पर्ची साथ लाएं।"}
        ],
    }
    res = evaluate_scenario(scenario)
    assert res["expected_verdict"] == "genuine"
    assert res["actual_verdict"] == "genuine"
    assert res["is_correct"] is True
    assert res["is_false_positive"] is False


def test_compute_held_out_metrics_and_markdown():
    eval_results = [
        {
            "id": "s1",
            "category": "police",
            "expected_verdict": "scam",
            "actual_verdict": "scam",
            "latency_ms": 1.2,
            "is_correct": True,
            "is_false_positive": False,
            "is_false_negative": False,
        },
        {
            "id": "g1",
            "category": "courier",
            "expected_verdict": "genuine",
            "actual_verdict": "genuine",
            "latency_ms": 0.8,
            "is_correct": True,
            "is_false_positive": False,
            "is_false_negative": False,
        },
    ]

    metrics = compute_held_out_metrics(eval_results)
    assert metrics["total_scenarios"] == 2
    assert metrics["scam_detection_rate_pct"] == 100.0
    assert metrics["false_positive_rate_pct"] == 0.0
    assert metrics["overall_accuracy_pct"] == 100.0
    assert metrics["sprint_bar_verdict"]["detection_rate"] == "PASS"

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        temp_md = f.name

    try:
        generate_markdown_report(metrics, temp_md)
        with open(temp_md, "r", encoding="utf-8") as f:
            content = f.read()
        assert "GuardianLine Blind Held-Out Evaluation Scorecard" in content
        assert "100.0%" in content
    finally:
        os.remove(temp_md)
