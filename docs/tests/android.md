# Android Screening App (T-AND) Field Verification & Protocol

**Component:** Android Call Screening Service (`ai.guardianline.screening.GuardianCallScreeningService`)  
**Role:** `RoleManager.ROLE_CALL_SCREENING`  
**Minimum Android API:** API 29 (Android 10)  
**Target Architecture:** Dual-SIM VoLTE / 5G (Jio, Airtel, Vi)

---

## 1. Automated Unit Testing
JUnit 5 tests in `android/app/src/test/java/ai/guardianline/screening/CallScreeningLogicTest.kt` and Python CI mirrors in `tests/unit/test_android_screening.py` verify core decision boundaries:

- **Saved Contacts Ring:** Contact matching is insensitive to whitespace, leading zeroes (`0XXXXXXXXXX`), and country code prefixes (`+91XXXXXXXXXX`).
- **Emergency Whitelist Always Rings:** `112` (Unified Emergency), `100` (Police), `108` (Ambulance), and `1930` (Cybercrime) ring without latency.
- **Bolna Gateway Never Looped:** Inbound calls originating from the Bolna telephony bridge (e.g. genuine call transfers back to the elder) are explicitly whitelisted to prevent carrier busy-forward loops.
- **Withheld Numbers Screened:** Null, blank, or private caller numbers are disallowed and redirected to the honeypot agent.
- **Empty Contact Handling:** System operates safely without crashing when contact book is unpopulated.

Run local unit tests:
```bash
pytest tests/unit/test_android_screening.py
```

---

## 2. 8-Step Physical Field Verification Script

Every test cycle on physical handsets (Jio, Airtel, Vi) must execute this 8-step field script:

| Step | Action | Expected Behavior | Fail Criteria |
| :--- | :--- | :--- | :--- |
| **1. Role Grant** | Launch app, tap *Enable Screening Protection*, approve system dialog. | Status transitions to `ACTIVE & PROTECTED` in green. | Dialog rejected or crash on role check. |
| **2. Saved Contact Inbound** | Place inbound call from a number saved in Google/Device Contacts. | Device rings instantly with standard incoming call UI. | Device rejects call or forwards to Bolna. |
| **3. Unknown Caller Inbound** | Place inbound call from an unlisted number (e.g. secondary test SIM). | Device does **not** ring or vibrate; call is disallowed immediately and rolls over to Bolna (`**67*`) within 1.5s. | Handset rings or audio connects on handset. |
| **4. Bolna Transfer Inbound** | Trigger a call from the Bolna gateway number (`+919988776655`). | Handset rings showing Bolna caller ID (genuine caller transfer). | Call rejected or forwarded into recursive loop. |
| **5. Post-Reboot Resilience** | Restart the Android handset. Re-test steps 2 and 3 without opening the app UI. | OS automatically retains `CallScreeningService` bindings. Step 2 rings, Step 3 screens. | Background service fails to bind after boot. |
| **6. Force-Stop Resilience** | In App Info, press *Force Stop*. Place unknown caller call. | Android OS invokes `CallScreeningService` upon telephony intent even if main activity process was terminated. | Call rings handset directly. |
| **7. Battery Saver Mode** | Enable extreme Battery Saver / Doze mode. Place unknown call. | Device screens call silently without background restriction delay. | Screening delayed > 3 seconds causing audible ring. |
| **8. Revocation & Fail-Open** | Go to Android Settings $\rightarrow$ Default Apps $\rightarrow$ Caller ID & Spam $\rightarrow$ None. Place unknown call. | App status warns `NOT CONFIGURED`. Inbound call rings handset normally (**fail-open safety**). | Telephony hangs or drops call. |

---

## 3. 24-Hour Soak Test Specification

- **Duration:** 24 continuous hours on an active personal handset.
- **Minimum Incoming Call Volume:** $\ge 15$ calls (mix of contacts, unknown deliveries, spam).
- **Pass Bar:**
  - **Zero** missed or screened calls from saved contacts (100% true positive acceptance).
  - All unknown calls intercepted without elder disruption.
  - Zero crashes or ANRs (Application Not Responding) logged in `logcat`.
