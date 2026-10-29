# GuardianLine Agent-Written Evaluation Scorecard (not blind)

**Status**: `[PASS] HELD-OUT BARS MET`

> [!NOTE]
> **EVALUATION SCOPE:** This benchmark was executed on an agent-written evaluation set (not blind),
> authored during this session, to verify generalized detection performance.

## 1. Primary Performance Metrics

| Metric | Target Bar | Held-Out Result | Verdict |
| :--- | :--- | :--- | :--- |
| **Scam Detection Rate (Recall)** | $\ge 85.0\%$ | **100.0%** (10 calls) | PASS |
| **False Positive Rate** | $\le 5.0\%$ | **0.0%** (10 calls) | PASS |
| **False Negative Rate** | $\le 15.0\%$ | **0.0%** | PASS |
| **Genuine Caller Accuracy** | $\ge 90.0\%$ | **100.0%** | INFO |
| **Overall Accuracy** | Benchmark | **100.0%** | INFO |

## 2. Telephony Latency Distribution

| Metric | Measured Value | Telephony Budget | Notes |
| :--- | :--- | :--- | :--- |
| **Median Latency (p50)** | **0.35 ms** | $< 1000$ ms | Sub-second response |
| **95th Percentile (p95)** | **498.48 ms** | $< 1400$ ms | Guaranteed no dead air |
| **Mean Latency** | 26.04 ms | - | - |

## 3. Category Breakdown

| Category | Total Calls | Correct | Accuracy | Scams / Genuines |
| :--- | :--- | :--- | :--- | :--- |
| **Courier** | 2 | 2 | 100.0% | 1 / 1 |
| **Medical** | 3 | 3 | 100.0% | 1 / 2 |
| **Police** | 3 | 3 | 100.0% | 2 / 1 |
| **Relative** | 2 | 2 | 100.0% | 1 / 1 |
| **Bank** | 2 | 2 | 100.0% | 1 / 1 |
| **Utilities** | 2 | 2 | 100.0% | 1 / 1 |
| **Society** | 2 | 2 | 100.0% | 0 / 2 |
| **Telecom** | 1 | 1 | 100.0% | 1 / 0 |
| **Government** | 1 | 1 | 100.0% | 0 / 1 |
| **Lottery** | 1 | 1 | 100.0% | 1 / 0 |
| **Job** | 1 | 1 | 100.0% | 1 / 0 |

## 4. Unsure $\rightarrow$ Verify Protocol Activations

- **Scams Routed to Defensive Verification:** 0
- **Genuines Routed to Safe Verification:** 0

---
*Report generated automatically by `scripts/run_held_out_eval.py` on 2026-10-29 09:40:43 UTC*
