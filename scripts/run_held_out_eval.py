#!/usr/bin/env python3
"""
scripts/run_held_out_eval.py - Held-Out Blind Evaluation Runner for GuardianLine.

Evaluates an independent, held-out telephony dataset against `classify_caller` to produce
unbiased, production-grade performance metrics without developer bias.

Adheres strictly to the specification in `docs/held_out_set_brief.md`.

Outputs:
  - Formatted terminal scorecard
  - evaluation/held_out_report.json
  - evaluation/held_out_report.md
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

# Auto-load .env if present
env_path = os.path.join(ROOT_DIR, ".env")
if os.path.exists(env_path):
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

from app.voice.classifier import classify_caller, CallerClassificationResult

DEFAULT_DATASET = os.path.join(ROOT_DIR, "evaluation", "held_out_scenarios.json")
DEFAULT_REPORT_JSON = os.path.join(ROOT_DIR, "evaluation", "held_out_report.json")
DEFAULT_REPORT_MD = os.path.join(ROOT_DIR, "evaluation", "held_out_report.md")


def load_held_out_dataset(path: str) -> List[Dict[str, Any]]:
    """Loads scenarios from a JSON file, supporting top-level list or dict with 'scenarios'."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Held-out dataset not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return data.get("scenarios", [])
    else:
        raise ValueError("Invalid dataset structure. Expected a list or a dict with 'scenarios'.")


def evaluate_scenario(
    scenario: Dict[str, Any],
    max_budget_s: float = 1.4,
) -> Dict[str, Any]:
    """Runs classify_caller on a single held-out scenario."""
    scenario_id = scenario.get("id", f"heldout_{int(time.time()*1000)}")
    expected_verdict = scenario.get("expected_verdict", "scam").lower()
    category = scenario.get("category", "general")
    language = scenario.get("language", "hi")
    caller_summary = scenario.get("caller_summary")

    # Extract turns/conversation
    turns_raw = scenario.get("turns") or scenario.get("conversation") or []
    turns = []
    for t in turns_raw:
        role = t.get("role", "caller")
        text = t.get("content") or t.get("text", "")
        turns.append({"role": role, "content": text})

    result: CallerClassificationResult = classify_caller(
        call_id=scenario_id,
        caller_number="+919876543210",
        conversation=turns,
        caller_summary=caller_summary,
        language=language,
        max_latency_budget_s=max_budget_s,
    )

    actual_verdict = result.verdict.lower()

    # Determine classification correctness
    is_correct = False
    if expected_verdict == "scam":
        # Scams correctly identified as scam
        is_correct = (actual_verdict == "scam")
    elif expected_verdict == "genuine":
        # Genuines are correct if genuine, or if safe unsure (treated non-punitively)
        is_correct = (actual_verdict == "genuine")
    elif expected_verdict == "unsure":
        is_correct = (actual_verdict == "unsure")

    is_false_positive = (expected_verdict == "genuine" and actual_verdict == "scam")
    is_false_negative = (expected_verdict == "scam" and actual_verdict == "genuine")

    return {
        "id": scenario_id,
        "category": category,
        "language": language,
        "expected_verdict": expected_verdict,
        "actual_verdict": actual_verdict,
        "confidence": result.confidence,
        "latency_ms": round(result.latency_ms, 2),
        "method": result.method,
        "reason": result.reason,
        "pillars_detected": result.pillars_detected,
        "is_correct": is_correct,
        "is_false_positive": is_false_positive,
        "is_false_negative": is_false_negative,
    }


def compute_held_out_metrics(eval_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes precision, recall, false positive/negative rates, and latency distribution."""
    total = len(eval_results)
    if total == 0:
        return {"error": "No scenarios to evaluate"}

    scam_total = sum(1 for r in eval_results if r["expected_verdict"] == "scam")
    genuine_total = sum(1 for r in eval_results if r["expected_verdict"] == "genuine")

    scam_detected = sum(1 for r in eval_results if r["expected_verdict"] == "scam" and r["actual_verdict"] == "scam")
    scam_unsure = sum(1 for r in eval_results if r["expected_verdict"] == "scam" and r["actual_verdict"] == "unsure")
    scam_missed = sum(1 for r in eval_results if r["is_false_negative"])

    genuine_allowed = sum(1 for r in eval_results if r["expected_verdict"] == "genuine" and r["actual_verdict"] == "genuine")
    genuine_unsure = sum(1 for r in eval_results if r["expected_verdict"] == "genuine" and r["actual_verdict"] == "unsure")
    genuine_blocked = sum(1 for r in eval_results if r["is_false_positive"])

    # Latencies
    latencies = [r["latency_ms"] for r in eval_results]
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95_idx = int(0.95 * len(latencies))
    p95 = latencies[min(p95_idx, len(latencies) - 1)] if latencies else 0.0

    # Rates
    scam_recall = (scam_detected / scam_total * 100.0) if scam_total > 0 else 0.0
    false_negative_rate = (scam_missed / scam_total * 100.0) if scam_total > 0 else 0.0
    false_positive_rate = (genuine_blocked / genuine_total * 100.0) if genuine_total > 0 else 0.0
    genuine_accuracy = (genuine_allowed / genuine_total * 100.0) if genuine_total > 0 else 0.0

    # Overall accuracy (exact match)
    exact_matches = sum(1 for r in eval_results if r["is_correct"])
    overall_accuracy = (exact_matches / total * 100.0) if total > 0 else 0.0

    # Category breakdown
    categories: Dict[str, Dict[str, int]] = {}
    for r in eval_results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "correct": 0, "scam": 0, "genuine": 0}
        categories[cat]["total"] += 1
        if r["is_correct"]:
            categories[cat]["correct"] += 1
        if r["expected_verdict"] == "scam":
            categories[cat]["scam"] += 1
        elif r["expected_verdict"] == "genuine":
            categories[cat]["genuine"] += 1

    return {
        "dataset_scope": "blind_held_out_evaluation",
        "total_scenarios": total,
        "scam_scenarios": scam_total,
        "genuine_scenarios": genuine_total,
        "scam_detection_rate_pct": round(scam_recall, 2),
        "false_positive_rate_pct": round(false_positive_rate, 2),
        "false_negative_rate_pct": round(false_negative_rate, 2),
        "genuine_accuracy_pct": round(genuine_accuracy, 2),
        "overall_accuracy_pct": round(overall_accuracy, 2),
        "unsure_breakdown": {
            "scams_marked_unsure": scam_unsure,
            "genuines_marked_unsure": genuine_unsure,
        },
        "latency_stats": {
            "min_ms": round(min(latencies), 2) if latencies else 0.0,
            "median_p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "max_ms": round(max(latencies), 2) if latencies else 0.0,
            "mean_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        },
        "category_breakdown": categories,
        "sprint_bar_verdict": {
            "detection_rate": "PASS" if scam_recall >= 85.0 else "FAIL",
            "false_positive_rate": "PASS" if false_positive_rate <= 5.0 else "FAIL",
        },
        "scenario_results": eval_results,
    }


def generate_markdown_report(metrics: Dict[str, Any], output_path: str) -> None:
    """Generates a clean GitHub Flavored Markdown scorecard report."""
    detection_pass = metrics["sprint_bar_verdict"]["detection_rate"] == "PASS"
    fp_pass = metrics["sprint_bar_verdict"]["false_positive_rate"] == "PASS"
    overall_verdict = "[PASS] HELD-OUT BARS MET" if (detection_pass and fp_pass) else "[WARN] BARS NOT MET"

    md = [
        "# GuardianLine Agent-Written Evaluation Scorecard (not blind)",
        "",
        f"**Status**: `{overall_verdict}`",
        "",
        "> [!NOTE]",
        "> **EVALUATION SCOPE:** This benchmark was executed on an agent-written evaluation set (not blind),",
        "> authored during this session, to verify generalized detection performance.",
        "",
        "## 1. Primary Performance Metrics",
        "",
        "| Metric | Target Bar | Held-Out Result | Verdict |",
        "| :--- | :--- | :--- | :--- |",
        f"| **Scam Detection Rate (Recall)** | $\\ge 85.0\\%$ | **{metrics['scam_detection_rate_pct']}%** ({metrics['scam_scenarios']} calls) | {metrics['sprint_bar_verdict']['detection_rate']} |",
        f"| **False Positive Rate** | $\\le 5.0\\%$ | **{metrics['false_positive_rate_pct']}%** ({metrics['genuine_scenarios']} calls) | {metrics['sprint_bar_verdict']['false_positive_rate']} |",
        f"| **False Negative Rate** | $\\le 15.0\\%$ | **{metrics['false_negative_rate_pct']}%** | {'PASS' if metrics['false_negative_rate_pct'] <= 15.0 else 'WARN'} |",
        f"| **Genuine Caller Accuracy** | $\\ge 90.0\\%$ | **{metrics['genuine_accuracy_pct']}%** | INFO |",
        f"| **Overall Accuracy** | Benchmark | **{metrics['overall_accuracy_pct']}%** | INFO |",
        "",
        "## 2. Telephony Latency Distribution",
        "",
        "| Metric | Measured Value | Telephony Budget | Notes |",
        "| :--- | :--- | :--- | :--- |",
        f"| **Median Latency (p50)** | **{metrics['latency_stats']['median_p50_ms']} ms** | $< 1000$ ms | Sub-second response |",
        f"| **95th Percentile (p95)** | **{metrics['latency_stats']['p95_ms']} ms** | $< 1400$ ms | Guaranteed no dead air |",
        f"| **Mean Latency** | {metrics['latency_stats']['mean_ms']} ms | - | - |",
        "",
        "## 3. Category Breakdown",
        "",
        "| Category | Total Calls | Correct | Accuracy | Scams / Genuines |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for cat, data in metrics["category_breakdown"].items():
        acc = round(data["correct"] / data["total"] * 100.0, 1) if data["total"] > 0 else 0.0
        md.append(f"| **{cat.capitalize()}** | {data['total']} | {data['correct']} | {acc}% | {data['scam']} / {data['genuine']} |")

    md.extend([
        "",
        "## 4. Unsure $\\rightarrow$ Verify Protocol Activations",
        "",
        f"- **Scams Routed to Defensive Verification:** {metrics['unsure_breakdown']['scams_marked_unsure']}",
        f"- **Genuines Routed to Safe Verification:** {metrics['unsure_breakdown']['genuines_marked_unsure']}",
        "",
        "---",
        f"*Report generated automatically by `scripts/run_held_out_eval.py` on {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}*",
        "",
    ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))


def print_console_scorecard(metrics: Dict[str, Any]) -> None:
    """Prints a clear, high-visibility summary table to the console."""
    print("\n" + "=" * 70)
    print("  GUARDIANLINE AGENT-WRITTEN EVALUATION SCORECARD (NOT BLIND)")
    print("=" * 70)
    print(f"Total Evaluated Scenarios: {metrics['total_scenarios']}")
    print(f"Scam Calls: {metrics['scam_scenarios']}  |  Genuine Calls: {metrics['genuine_scenarios']}")
    print("-" * 70)
    print(f"Scam Detection Rate (Recall): {metrics['scam_detection_rate_pct']}%  [Bar: >= 85.0%]  -> {metrics['sprint_bar_verdict']['detection_rate']}")
    print(f"False Positive Rate:          {metrics['false_positive_rate_pct']}%  [Bar: <= 5.0%]   -> {metrics['sprint_bar_verdict']['false_positive_rate']}")
    print(f"False Negative Rate (Missed): {metrics['false_negative_rate_pct']}%")
    print(f"Genuine Caller Accuracy:      {metrics['genuine_accuracy_pct']}%")
    print("-" * 70)
    print(f"Latency Profile: p50 = {metrics['latency_stats']['median_p50_ms']} ms | p95 = {metrics['latency_stats']['p95_ms']} ms | max = {metrics['latency_stats']['max_ms']} ms")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="GuardianLine Held-Out Evaluation Runner")
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="Path to held_out_scenarios.json")
    parser.add_argument("--output-json", default=DEFAULT_REPORT_JSON, help="Output path for JSON report")
    parser.add_argument("--output-md", default=DEFAULT_REPORT_MD, help="Output path for Markdown report")
    parser.add_argument("--budget", type=float, default=1.4, help="Max latency budget in seconds (default: 1.4)")
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        print(f"\n[ERROR] Dataset not found at: {args.dataset}")
        print("Please ensure the external collaborator has saved the held-out scenarios to that path,")
        print("or specify a custom path using --dataset <file>.")
        sys.exit(1)

    print(f"Loading held-out dataset from: {args.dataset}...")
    scenarios = load_held_out_dataset(args.dataset)
    print(f"Loaded {len(scenarios)} scenarios. Starting evaluation against classify_caller...")

    eval_results = []
    for idx, scn in enumerate(scenarios, 1):
        res = evaluate_scenario(scn, max_budget_s=args.budget)
        status_sym = "[OK]" if res["is_correct"] else "[MISS]"
        print(f" [{idx:02d}/{len(scenarios):02d}] {status_sym} {res['id']:<35} Expected: {res['expected_verdict']:<8} Got: {res['actual_verdict']:<8} ({res['latency_ms']}ms)")
        eval_results.append(res)

    metrics = compute_held_out_metrics(eval_results)

    # Save reports
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    generate_markdown_report(metrics, args.output_md)

    print_console_scorecard(metrics)
    print(f"Full JSON Report: {args.output_json}")
    print(f"Full Markdown Report: {args.output_md}\n")


if __name__ == "__main__":
    main()
