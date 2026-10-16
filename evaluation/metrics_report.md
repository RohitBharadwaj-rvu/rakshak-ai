# GuardianLine Evaluation & Performance Scorecard

**Status**: `[PASS] ALL SPRINT BARS MET`

> [!IMPORTANT]
> **EVALUATION SCOPE NOTICE:**
> The figures below are measured on an internal **synthetic dev set, not held-out**.
> A blind held-out evaluation set is currently being authored by external contributors to obtain unbiased real-world metrics.

## 1. Core Performance Metrics

| Metric | Target Bar | Measured Result | Evaluation Scope | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **Scam Detection Rate** | $\ge 85.0\%$ | **100.0%** (20 calls) | synthetic dev set, not held-out | PASS |
| **False Positive Rate** | $\le 5.0\%$ | **0.0%** (22 calls) | synthetic dev set, not held-out | PASS |
| **Bait Safety (PII Leakage)** | `0 leaks` (100%) | **0 leaks** | synthetic dev set, not held-out | PASS |
| **Adversarial Safety (OTP/Aadhaar/Remote)** | `0 leaks` (100%) | **0 leaks** | synthetic dev set, not held-out | PASS |
| **Scammer Time Wasted (Avg Turns)** | Sustained honeypot | **7.2 turns / call** | synthetic dev set, not held-out | INFO |
| **Genuine Caller Accuracy** | $\ge 90.0\%$ | **100.0%** | synthetic dev set, not held-out | INFO |

## 2. Evaluation Summary

- **Dataset Scope**: Synthetic dev set, not held-out
- **Total Evaluated Calls**: 42
- **Scam & Red-Team Scenarios**: 20
- **Genuine Service Calls**: 22
- **Honeypot Activations**: 20

> Verified across Hindi, English, and natural Hinglish code-switching on synthetic dev set.