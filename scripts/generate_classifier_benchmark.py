#!/usr/bin/env python3
"""
generate_classifier_benchmark.py - Build and run the T-CLS benchmark dataset.

Cuts every scenario in evaluation/scenarios/ at turns 2, 4, and 6 to produce
evaluation/classifier/classifier_set.jsonl. Runs classification over each cut,
measuring recall on scams, false-positive rate on genuine calls, and latency.
"""

import glob
import json
import os
import sys
from typing import Any, Dict, List

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from app.voice.classifier import classify_caller

SCENARIOS_DIR = os.path.join(ROOT_DIR, "evaluation", "scenarios")
OUTPUT_DIR = os.path.join(ROOT_DIR, "evaluation", "classifier")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "classifier_set.jsonl")


def load_json(filepath: str) -> Dict[str, Any]:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def build_benchmark_cuts() -> List[Dict[str, Any]]:
    scenario_files = sorted(glob.glob(os.path.join(SCENARIOS_DIR, "*.json")))
    benchmark_cases = []

    for fpath in scenario_files:
        sc = load_json(fpath)
        sc_id = sc["id"]
        sc_name = sc.get("name", sc_id)
        sc_type = sc["type"]
        expected_verdict = sc["expected_verdict"]
        lang = sc.get("language", "hi")
        script = sc.get("caller_script", [])

        # Cut points: turn 2 (early), turn 4 (if available), and final turn
        total_turns = len(script)
        candidate_cuts = [2, 4, 6]
        cut_points = [c for c in candidate_cuts if c < total_turns]
        if total_turns not in cut_points:
            cut_points.append(total_turns)
        cut_points = sorted(list(set(cut_points)))

        for cut in cut_points:
            sub_turns = script[:cut]
            # Convert to conversation format
            conversation = []
            for item in sub_turns:
                conversation.append({
                    "role": "user",
                    "content": item.get("text", ""),
                })

            case_id = f"{sc_id}_cut_{cut}"
            benchmark_cases.append({
                "case_id": case_id,
                "scenario_id": sc_id,
                "scenario_name": sc_name,
                "type": sc_type,
                "language": lang,
                "cut_turn": cut,
                "expected_verdict": expected_verdict,
                "conversation": conversation,
            })

    return benchmark_cases


def run_benchmark(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    print(f"\n[T-CLS Benchmark] Saved {len(cases)} benchmark cuts to {OUTPUT_FILE}")

    total_scams_all_cuts = 0
    scams_detected_all_cuts = 0
    final_scams = 0
    final_scams_detected = 0
    total_genuine_cuts = 0
    false_positives = 0
    latencies = []

    for c in cases:
        call_id = c["case_id"]
        exp_verdict = c["expected_verdict"]
        res = classify_caller(
            call_id=call_id,
            caller_number="+919876543210",
            conversation=c["conversation"],
            language=c["language"],
        )
        latencies.append(res.latency_ms)

        is_final_cut = c["case_id"].endswith(f"_cut_{c['cut_turn']}") and c["cut_turn"] >= 3

        if exp_verdict == "scam":
            total_scams_all_cuts += 1
            if res.verdict == "scam":
                scams_detected_all_cuts += 1
            if is_final_cut or c["cut_turn"] >= 3:
                final_scams += 1
                if res.verdict == "scam":
                    final_scams_detected += 1
        elif exp_verdict == "genuine":
            total_genuine_cuts += 1
            if res.verdict == "scam":
                false_positives += 1

    final_recall = (final_scams_detected / final_scams) * 100 if final_scams else 0
    overall_recall = (scams_detected_all_cuts / total_scams_all_cuts) * 100 if total_scams_all_cuts else 0
    fpr = (false_positives / total_genuine_cuts) * 100 if total_genuine_cuts else 0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    sorted_lat = sorted(latencies)
    p95_latency = sorted_lat[int(len(sorted_lat) * 0.95)] if sorted_lat else 0

    print(f"\n--- T-CLS Benchmark Results ---")
    print(f"Total Evaluated Cuts  : {len(cases)}")
    print(f"Scam Recall (Final)   : {final_scams_detected}/{final_scams} ({final_recall:.1f}%)")
    print(f"Scam Recall (All cuts): {scams_detected_all_cuts}/{total_scams_all_cuts} ({overall_recall:.1f}%)")
    print(f"False Positive Rate   : {false_positives}/{total_genuine_cuts} ({fpr:.1f}%)")
    print(f"Average Latency       : {avg_latency:.2f} ms")
    print(f"p95 Latency           : {p95_latency:.2f} ms\n")

    # Pass Sprint Bar: Final scam recall >= 85%, False Positives <= 5%, p95 Latency <= 1000ms
    passes = final_recall >= 85.0 and fpr <= 5.0 and p95_latency <= 1000.0
    metrics = {
        "total_cases": len(cases),
        "final_scam_recall": round(final_recall, 2),
        "overall_scam_recall": round(overall_recall, 2),
        "false_positive_rate": round(fpr, 2),
        "avg_latency_ms": round(avg_latency, 2),
        "p95_latency_ms": round(p95_latency, 2),
        "pass_sprint_bar": passes,
    }

    baseline_file = os.path.join(OUTPUT_DIR, "baseline.json")
    with open(baseline_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    return metrics


def main():
    cases = build_benchmark_cuts()
    metrics = run_benchmark(cases)
    if not metrics["pass_sprint_bar"]:
        print("[T-CLS] Warning: Benchmark did not meet sprint targets!")
        sys.exit(1)
    print("[T-CLS] [SUCCESS] All sprint bars PASSED!")
    sys.exit(0)


if __name__ == "__main__":
    main()
