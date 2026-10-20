# Carrier forwarding results matrix (T-CARRIER)

**Status:** NOT VERIFIED (No physical SIM tested in automated environment)  
**Gate 1 decision:** NO-GO for App Mode in demo -> **Basic Mode only**  
**Undo forwarding code:** Dial `##002#` after any SIM forwarding test to cancel all call forwarding.

---

## 1. Field test log template (per attempt)

If you borrow a physical SIM to run Carrier Test 1 (`**21*<gateway_number>#` or `**67*<gateway_number>#`), record:
- **Date & Time (IST)**
- **Tester / Phone model**
- **VoLTE / VoWiFi state**
- **Forwarding code dialed**
- **Forwarding successful?** (Yes / No)
- **Caller ID seen by receiver/webhook**
- **Seconds to forward**
- **Cleanup:** Dial `##002#` immediately after the test to undo all call forwarding.

---

## 2. Summary status table

| Carrier | Test 1: Forwarding (`**21*` / `**67*`) | Test 2: App screening (`**67*`) | Test 3: Caller ID retained | Test 4: Unanswered (`**61*`) | Deciding status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Reliance Jio** (VoLTE/5G) | `NOT_VERIFIED` (0/3) | `NOT_VERIFIED` (0/3) | `NOT_VERIFIED` | `NOT_VERIFIED` (0/3) | Basic mode only |
| **Bharti Airtel** (VoLTE/5G) | `NOT_VERIFIED` (0/3) | `NOT_VERIFIED` (0/3) | `NOT_VERIFIED` | `NOT_VERIFIED` (0/3) | Basic mode only |
| **Vodafone Idea (Vi)** (VoLTE) | `NOT_VERIFIED` (0/3) | `NOT_VERIFIED` (0/3) | `NOT_VERIFIED` | `NOT_VERIFIED` (0/3) | Basic mode only |

---

## 3. Gate 1 decision and demo scope

- **Decision:** App Mode is cut from the live demo. The demo shows **Basic Mode only**.
- **Carrier Test 1:** Marked `NOT_VERIFIED`. If a physical SIM is borrowed for manual verification, dial `##002#` afterwards to clear all forwarding rules.
