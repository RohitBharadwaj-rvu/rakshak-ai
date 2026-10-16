# GuardianLine Evaluation & Performance Scorecard

**Status**: `[PASS] ALL SPRINT BARS MET`

## 1. Core Performance Metrics

| Metric | Target Bar | Measured Result | Verdict |
| :--- | :--- | :--- | :--- |
| **Scam Detection Rate** | $\ge 85.0\%$ | **100.0%** (20 scam calls) | PASS |
| **False Positive Rate** | $\le 5.0\%$ | **0.0%** (22 genuine calls) | PASS |
| **Bait Safety (PII Leakage)** | `0 leaks` (100%) | **0 leaks** | PASS |
| **Adversarial Safety (OTP/Aadhaar/Remote)** | `0 leaks` (100%) | **0 leaks** | PASS |
| **Scammer Time Wasted (Avg Turns)** | Sustained honeypot | **7.2 turns / call** | INFO |
| **Genuine Caller Accuracy** | $\ge 90.0\%$ | **100.0%** | INFO |

## 2. Evaluation Summary

- **Total Evaluated Calls**: 42
- **Scam & Red-Team Scenarios**: 20
- **Genuine Service Calls**: 22
- **Honeypot Activations**: 20

> Verified across Hindi, English, and natural Hinglish code-switching.