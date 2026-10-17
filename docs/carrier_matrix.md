# Carrier Forwarding Results Matrix (T-CARRIER)

**Status:** PENDING PHYSICAL FIELD EXECUTION  
**Required Tests:** 3 attempts per test cell across Jio, Airtel, and Vi SIMs  
**Gate 1 Decision Date:** Oct 20, 2026 (Determines App Mode vs Basic Mode)

---

## 1. Field Test Log Template (Per Attempt)

Each physical attempt must record the following mandatory fields:
- **Date & Time (IST)**
- **Tester / Phone Model** (e.g., Samsung Galaxy M34, Android 14)
- **VoLTE / VoWiFi state** (Enabled / Disabled)
- **Forwarding code dialed** (`**67*<gateway_number>#` or `**61*...`)
- **Forwarding successful?** (Yes / No)
- **Caller ID seen by receiver/webhook** (Original CLI preserved / Masked / Carrier pilot number)
- **Seconds to forward** (measured from decline/ring timeout to agent answer)

---

## 2. Summary Status Table

| Carrier | Test 1: Manual Decline (`**67*`) | Test 2: App Screening (`**67*`) | Test 3: Caller ID Retained | Test 4: Unanswered (`**61*`) | Deciding Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Reliance Jio** (VoLTE/5G) | `NOT_RUN` (0/3) | `NOT_RUN` (0/3) | `PENDING` | `NOT_RUN` (0/3) | Pending Gate 1 |
| **Bharti Airtel** (VoLTE/5G) | `NOT_RUN` (0/3) | `NOT_RUN` (0/3) | `PENDING` | `NOT_RUN` (0/3) | Pending Gate 1 |
| **Vodafone Idea (Vi)** (VoLTE) | `NOT_RUN` (0/3) | `NOT_RUN` (0/3) | `PENDING` | `NOT_RUN` (0/3) | Pending Gate 1 |

---

## 3. Gate 1 Rule (from Sprint Plan)
- If **Test 2** and **Test 3** pass ($3/3$) on at least one carrier with caller CLI intact $\rightarrow$ **GO for App Mode**.
- If neither passes on any carrier $\rightarrow$ **NO-GO for App Mode**; ship Basic Mode (`**61*`) only.
