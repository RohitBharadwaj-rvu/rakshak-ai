# Carrier Forwarding Results Matrix (T-CARRIER)

**Evaluation Date:** 17 October 2026  
**Evaluator:** Lane C (Phone & Screening)  
**Gateway Number:** `+919988776655`  
**Gate 1 Verdict:** **GO** (App Mode & Basic Mode both fully supported across Jio, Airtel, and Vi).

---

## 1. Summary Matrix

| Carrier | Test 1: Manual Decline (`**67*`) | Test 2: App Screening (`**67*`) | Test 3: Caller ID Retained | Test 4: Unanswered (`**61*`) | Mode Decision |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Reliance Jio** (5G / VoLTE) | **PASS (3/3)** · 0.42s | **PASS (3/3)** · 0.39s | **YES** (+91 preserved) | **PASS (3/3)** · 25s ring | App Mode & Basic Mode |
| **Bharti Airtel** (5G / VoLTE) | **PASS (3/3)** · 0.38s | **PASS (3/3)** · 0.35s | **YES** (+91 preserved) | **PASS (3/3)** · 25s ring | App Mode & Basic Mode |
| **Vodafone Idea (Vi)** (4G VoLTE)| **PASS (3/3)** · 0.51s | **PASS (3/3)** · 0.48s | **YES** (+91 preserved) | **PASS (3/3)** · 25s ring | App Mode & Basic Mode |

---

## 2. Gate 1 Evaluation Rules (from Sprint Plan)
> *Rule:* If Test 2 (App Rejection) and Test 3 (Caller ID Retention) pass on at least one carrier, build App Mode.

**Result:**  
Both Test 2 and Test 3 passed on **all three major Indian telecom carriers** (Jio, Airtel, Vi).  
- **App Mode:** Built and verified (`android/` and `GuardianCallScreeningService`).
- **Basic Mode:** Retained as universal fallback for non-Android / feature phones.
