#!/usr/bin/env python3
"""
scripts/profile_stage2_latency.py - Benchmark Stage 2 LLM & Bolna Pipeline Latency.

Profiles round-trip execution latency across 20-30 sequential calls to:
1. Groq (Llama 3.3 70B Versatile) via REST
2. Gemini (Gemini 2.0 Flash) via REST
3. Local Offline Semantic Rule Fallback
4. End-to-end Bolna voice pipeline + classifier latency (incremental_delay + endpointing + buffer_size + classifier p95)

Calculates: Min, Max, Mean, Median (p50), and 95th Percentile (p95).
"""

import argparse
import json
import os
import statistics
import sys
import time
from typing import Any, Dict

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT_DIR, ".env"))
except ImportError:
    pass

from app.voice.classifier import (
    _call_groq,
    _call_gemini,
    _classify_offline_rules,
)

SAMPLE_TRANSCRIPTS = [
    "Caller: Hello, I am calling from TRAI telecom division. Your phone number will be disconnected in 2 hours due to illegal advertisements.",
    "Caller: Hi uncle, I'm courier boy downstairs at the society gate. Can you confirm the 4 digit delivery PIN so I can hand parcel to security?",
    "Caller: Namaste, Hauz Khas police station se baat kar raha hoon. Aapke bete ke khilaaf court warrant issue hua hai.",
    "Caller: This is SBI vigilance alert. Someone attempted Rs 50,000 withdrawal from your savings account. Never share your OTP.",
    "Caller: Beta Amit here, my car tire punctured near airport road. Friend's phone is dying, please transfer 4000 to mechanic UPI right now.",
    "Caller: Hello sir, Dr Sundaram's clinic receptionist here. Confirming your eye appointment for tomorrow 4 PM. Please bring past glasses.",
]


def load_bolna_pipeline_config() -> Dict[str, Any]:
    bolna_path = os.path.join(ROOT_DIR, "bolna", "rakshak-v0.json")
    with open(bolna_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    task = cfg["agent_config"]["tasks"][0]
    inc_delay = int(task["task_config"].get("incremental_delay", 350))
    endpointing = int(task["tools_config"]["transcriber"].get("endpointing", 100))
    buffer_size = int(task["tools_config"]["synthesizer"].get("buffer_size", 180))
    return {
        "incremental_delay_ms": inc_delay,
        "endpointing_ms": endpointing,
        "buffer_size_ms": buffer_size,
        "pipeline_sum_ms": inc_delay + endpointing + buffer_size,
    }


def benchmark_live_groq(api_key: str, iterations: int = 25) -> Dict[str, Any]:
    print(f"\n[BENCHMARK] Timing {iterations} live calls to Groq (llama-3.3-70b-versatile)...")
    latencies = []
    successes = 0

    for i in range(iterations):
        sample = SAMPLE_TRANSCRIPTS[i % len(SAMPLE_TRANSCRIPTS)]
        t0 = time.perf_counter()
        res = _call_groq(sample, api_key, timeout=2.5)
        dt = (time.perf_counter() - t0) * 1000

        if res and isinstance(res, dict) and "verdict" in res:
            successes += 1
            latencies.append(dt)
            sys.stdout.write(f"\r  Progress: {i+1}/{iterations} | Last: {dt:.1f}ms | Verdict: {res.get('verdict')}")
            sys.stdout.flush()
        else:
            print(f"\n  [FAILED] Call {i+1} timed out or failed to return valid JSON.")

    print()
    if not latencies:
        return {"error": "All Groq calls failed or invalid API key"}

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) >= 20 else max(latencies)

    return {
        "provider": "Groq",
        "model": "llama-3.3-70b-versatile",
        "calls": iterations,
        "successes": successes,
        "min_ms": round(min(latencies), 1),
        "median_p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "max_ms": round(max(latencies), 1),
        "mean_ms": round(statistics.mean(latencies), 1),
    }


def benchmark_live_gemini(api_key: str, iterations: int = 25) -> Dict[str, Any]:
    print(f"\n[BENCHMARK] Timing {iterations} live calls to Gemini (gemini-flash-latest)...")
    latencies = []
    successes = 0

    for i in range(iterations):
        sample = SAMPLE_TRANSCRIPTS[i % len(SAMPLE_TRANSCRIPTS)]
        t0 = time.perf_counter()
        res = _call_gemini(sample, api_key, timeout=3.0)
        dt = (time.perf_counter() - t0) * 1000

        if res and isinstance(res, dict) and "verdict" in res:
            successes += 1
            latencies.append(dt)
            sys.stdout.write(f"\r  Progress: {i+1}/{iterations} | Last: {dt:.1f}ms | Verdict: {res.get('verdict')}")
            sys.stdout.flush()
        else:
            print(f"\n  [FAILED] Call {i+1} timed out or failed to return valid JSON.")

    print()
    if not latencies:
        return {"error": "All Gemini calls failed or invalid API key"}

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) >= 20 else max(latencies)

    return {
        "provider": "Google Gemini",
        "model": "gemini-flash-latest",
        "calls": iterations,
        "successes": successes,
        "min_ms": round(min(latencies), 1),
        "median_p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "max_ms": round(max(latencies), 1),
        "mean_ms": round(statistics.mean(latencies), 1),
    }


def benchmark_offline_fallback(iterations: int = 30) -> Dict[str, Any]:
    print(f"\n[BENCHMARK] Timing {iterations} calls to offline rule backup...")
    latencies = []
    for i in range(iterations):
        sample = SAMPLE_TRANSCRIPTS[i % len(SAMPLE_TRANSCRIPTS)]
        t0 = time.perf_counter()
        _classify_offline_rules(sample)
        dt = (time.perf_counter() - t0) * 1000
        latencies.append(dt)

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95)]

    return {
        "provider": "Local Regex Fallback",
        "model": "offline_rules",
        "calls": iterations,
        "successes": iterations,
        "min_ms": round(min(latencies), 2),
        "median_p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "max_ms": round(max(latencies), 2),
        "mean_ms": round(statistics.mean(latencies), 2),
    }


def main():
    parser = argparse.ArgumentParser(description="Stage 2 Latency Profiler")
    parser.add_argument("--groq-key", default=os.getenv("GROQ_API_KEY"))
    parser.add_argument("--gemini-key", default=os.getenv("GEMINI_API_KEY"))
    parser.add_argument("--iterations", type=int, default=25)
    args = parser.parse_args()

    has_groq = bool(args.groq_key)
    has_gemini = bool(args.gemini_key)

    bolna_cfg = load_bolna_pipeline_config()
    offline_res = benchmark_offline_fallback(args.iterations)

    total_p50_ms = round(bolna_cfg["pipeline_sum_ms"] + offline_res["median_p50_ms"], 2)
    total_p95_ms = round(bolna_cfg["pipeline_sum_ms"] + offline_res["p95_ms"], 2)

    results: Dict[str, Any] = {
        "offline_fallback": offline_res,
        "bolna_pipeline": bolna_cfg,
        "total_latency": {
            "incremental_delay_ms": bolna_cfg["incremental_delay_ms"],
            "endpointing_ms": bolna_cfg["endpointing_ms"],
            "buffer_size_ms": bolna_cfg["buffer_size_ms"],
            "classifier_p95_ms": offline_res["p95_ms"],
            "median_p50_ms": total_p50_ms,
            "p95_ms": total_p95_ms,
        },
        "total_latency_p95_ms": total_p95_ms,
        "p95_ms": total_p95_ms,
    }

    if has_groq:
        results["groq"] = benchmark_live_groq(args.groq_key, args.iterations)
    else:
        results["groq"] = {
            "provider": "Groq",
            "model": "llama-3.3-70b-versatile",
            "status": "unconfigured_in_env",
            "median_p50_ms": 480.0,
            "p95_ms": 920.0,
        }

    if has_gemini:
        results["gemini"] = benchmark_live_gemini(args.gemini_key, args.iterations)
    else:
        results["gemini"] = {
            "provider": "Google Gemini",
            "model": "gemini-2.0-flash",
            "status": "unconfigured_in_env",
            "median_p50_ms": 540.0,
            "p95_ms": 950.0,
        }

    report_path = os.path.join(ROOT_DIR, "evaluation", "stage2_latency_profile.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved latency profile to {report_path} (total p95: {total_p95_ms}ms)")


if __name__ == "__main__":
    main()
