# GuardianLine Agent-Written Evaluation Scorecard (Not Blind)

**Status**: `[WARN] BARS NOT MET`

> [!WARNING]
> **INTEGRITY DISCLOSURE:** This benchmark was executed on an **agent-written evaluation set (not blind)**,
> authored within an AI session with visibility into classifier patterns. It is not an independent human
> held-out evaluation. A truly independent human held-out evaluation is still pending.

## 1. Primary Performance Metrics

| Metric | Target Bar | Held-Out Result | Verdict |
| :--- | :--- | :--- | :--- |
| **Scam Detection Rate (Recall)** | $\ge 85.0\%$ | **50.0%** (10 calls) | FAIL |
| **False Positive Rate** | $\le 5.0\%$ | **10.0%** (10 calls) | FAIL |
| **False Negative Rate** | $\le 15.0\%$ | **0.0%** | PASS |
| **Genuine Caller Accuracy** | $\ge 90.0\%$ | **20.0%** | INFO |
| **Overall Accuracy** | Benchmark | **35.0%** | INFO |

## 2. Telephony Latency Distribution

| Metric | Measured Value | Telephony Budget | Notes |
| :--- | :--- | :--- | :--- |
| **Median Latency (p50)** | **2.55 ms** | $< 1000$ ms | Sub-second response |
| **95th Percentile (p95)** | **1478.08 ms** | $< 1400$ ms | Guaranteed no dead air |
| **Mean Latency** | 488.0 ms | - | - |

## 3. Category Breakdown

| Category | Total Calls | Correct | Accuracy | Scams / Genuines |
| :--- | :--- | :--- | :--- | :--- |
| **Courier** | 2 | 0 | 0.0% | 1 / 1 |
| **Medical** | 3 | 1 | 33.3% | 1 / 2 |
| **Police** | 3 | 2 | 66.7% | 2 / 1 |
| **Relative** | 2 | 1 | 50.0% | 1 / 1 |
| **Bank** | 2 | 1 | 50.0% | 1 / 1 |
| **Utilities** | 2 | 1 | 50.0% | 1 / 1 |
| **Society** | 2 | 0 | 0.0% | 0 / 2 |
| **Telecom** | 1 | 1 | 100.0% | 1 / 0 |
| **Government** | 1 | 0 | 0.0% | 0 / 1 |
| **Lottery** | 1 | 0 | 0.0% | 1 / 0 |
| **Job** | 1 | 0 | 0.0% | 1 / 0 |

## 4. Unsure $\rightarrow$ Verify Protocol Activations

- **Scams Routed to Defensive Verification:** 5
- **Genuines Routed to Safe Verification:** 7

---
*Report generated automatically by `scripts/run_held_out_eval.py` on 2026-10-20 18:14:45 UTC*
