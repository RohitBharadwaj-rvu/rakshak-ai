#!/usr/bin/env python3
"""
scripts/analyze_extraction_misses.py - Sprint 4 CLI for STT Extraction-Miss Analysis (Lane B).

Runs the post-call extraction & cleanup pipeline across all fixtures (and any stored SQLite
CallRecords) and outputs:
  - evaluation/extraction_miss_report.json
  - evaluation/extraction_miss_report.md
"""

import argparse
import glob
import json
import os
import sys
from typing import Any, Dict, List

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.voice.cleanup import cleanup_call_intel
from app.voice.extractor import extract_from_transcript
from app.voice.miss_analyzer import analyze_corpus_extraction_misses
from app.voice.store import list_call_records

DEFAULT_OUT_JSON = os.path.join(ROOT_DIR, "evaluation", "extraction_miss_report.json")
DEFAULT_OUT_MD = os.path.join(ROOT_DIR, "evaluation", "extraction_miss_report.md")


def format_miss_report_md(report: Dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# GuardianLine Sprint 4 — STT Extraction-Miss Analysis Report",
        "",
        "## 1. Summary Metrics",
        "",
        "| Metric | Value |",
        "| :--- | :--- |",
        f"| **Total Calls Analyzed** | {s['total_calls_analyzed']} |",
        f"| **Calls with Planted Intel** | {s['calls_with_planted_intel']} |",
        f"| **Call-Level Extraction Accuracy** | **{s['call_level_extraction_accuracy_pct']}%** ({s['calls_capturing_planted_intel']}/{s['calls_with_planted_intel']}) |",
        f"| **Entity-Level Recall** | **{s['entity_level_recall_pct']}%** ({s['total_captured_entities']}/{s['total_expected_entities']}) |",
        f"| **Total Extraction Misses** | {s['total_misses']} |",
        f"| **Unparseable Mid-Call Logs** | {s['total_unparseable_mid_call_logs']} |",
        "",
        "## 2. Extraction Miss Breakdown",
        "",
    ]
    if not report["misses"]:
        lines.append("- **Zero extraction misses** across all evaluated transcripts.")
    else:
        for m in report["misses"]:
            lines.append(
                f"- **`{m['call_id']}`** (`{m['bucket']}`): expected `{m['expected']}`, "
                f"got `{m['actual_in_bucket']}` | STT phenomena: `{m['stt_garble_patterns']}`"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze STT extraction misses across fixtures and CallRecords")
    parser.add_argument("--output-json", default=DEFAULT_OUT_JSON)
    parser.add_argument("--output-md", default=DEFAULT_OUT_MD)
    args = parser.parse_args()

    items: List[Dict[str, Any]] = []
    for fpath in sorted(glob.glob(os.path.join(ROOT_DIR, "tests", "fixtures", "*.json"))):
        with open(fpath, "r", encoding="utf-8") as f:
            payload = json.load(f)
        transcript = payload.get("transcript") or []
        metadata = payload.get("metadata") or {}
        cleaned = cleanup_call_intel(transcript=transcript, verdict="scam", metadata=metadata)
        rec = {
            "call_id": payload["call_id"],
            "transcript": transcript,
            "extracted_intel": cleaned["extracted_intel"],
        }
        items.append({"record": rec, "planted_intel": metadata.get("planted_intel", {})})

    # Also include any stored records from SQLite that aren't already in fixtures
    seen_ids = {it["record"]["call_id"] for it in items}
    for db_rec in list_call_records(limit=500):
        if db_rec["call_id"] not in seen_ids:
            items.append({"record": db_rec, "planted_intel": {}})

    report = analyze_corpus_extraction_misses(items)
    os.makedirs(os.path.dirname(os.path.abspath(args.output_json)), exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as jf:
        json.dump(report, jf, indent=2, ensure_ascii=False)

    md_text = format_miss_report_md(report)
    with open(args.output_md, "w", encoding="utf-8") as mf:
        mf.write(md_text)

    print(
        f"[MissAnalyzer] Analyzed {report['summary']['total_calls_analyzed']} calls | "
        f"Call-level accuracy: {report['summary']['call_level_extraction_accuracy_pct']}% | "
        f"Misses: {report['summary']['total_misses']}"
    )


if __name__ == "__main__":
    main()
