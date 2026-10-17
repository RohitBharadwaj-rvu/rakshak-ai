# Android Screening App (T-AND) Field Verification & Protocol

**Component:** Android Call Screening Service (`ai.guardianline.screening.GuardianCallScreeningService`)  
**Role:** `RoleManager.ROLE_CALL_SCREENING`  
**Minimum Android API:** API 29 (Android 10)  
**Target Telephony:** VoLTE / VoWiFi / 5G (Jio, Airtel, Vi)

---

## 1. Automated Testing
- **JUnit 5:** `android/app/src/test/java/ai/guardianline/screening/CallScreeningLogicTest.kt` verifies:
  - Saved contacts always ring (ALLOW) across spacing/zero/country-code variations.
  - Emergency numbers (112, 100, 108, 1930) ring with zero contacts.
  - Bolna proxy number always rings (prevents device loop on transfer).
  - Withheld/private numbers are screened.
  - International numbers with `00` or `+` prefixes match contacts.
- **Python CI Validation:** `tests/unit/test_android_screening.py` verifies canonical cases against `tests/data/screening_cases.json`.

---

## 2. 8-Step Physical Handset Field Script

Executed by a human researcher holding test devices:

| Step | Action | Expected Behavior | Fail Criteria |
| :--- | :--- | :--- | :--- |
| **1. Role Grant** | Launch app, tap *Enable Screening Protection*, approve system dialog. | Status transitions to `ACTIVE & PROTECTED` in green. | Dialog rejected or crash on role check. |
| **2. Saved Contact Inbound** | Place call from a number saved in Google/Device Contacts. | Device rings instantly with standard incoming call UI. | Device rejects call or fails to ring. |
| **3. Unknown Caller Inbound** | Place call from an unlisted number (e.g. secondary test SIM). | Device does **not** ring or vibrate; call is disallowed and rolls over to carrier forward (`**67*`). | Handset rings or audio connects on handset. |
| **4. Bolna Transfer Inbound** | Trigger a call from the Bolna gateway number. | Handset rings showing Bolna caller ID (genuine caller transfer). | Call rejected or forwarded into recursive loop. |
| **5. Post-Reboot Resilience** | Restart handset. Re-test steps 2 and 3 without opening app. | OS retains `CallScreeningService` bindings; step 2 rings, step 3 screens. | Background service fails to bind after boot. |
| **6. Force-Stop Resilience** | In App Info, press *Force Stop*. Place unknown caller call. | Android OS invokes `CallScreeningService` upon telephony intent. | Call rings handset directly. |
| **7. Battery Saver Mode** | Enable extreme Battery Saver / Doze mode. Place unknown call. | Device screens call silently without background restriction delay. | Screening delayed > 3 seconds causing audible ring. |
| **8. Revocation & Fail-Open** | Go to Settings $\rightarrow$ Default Apps $\rightarrow$ Caller ID & Spam $\rightarrow$ None. Place unknown call. | App warns `PROTECTION INACTIVE`. Inbound call rings normally (**fail-open safety**). | Telephony hangs or drops call. |

---

## 3. 24-Hour Soak Test Specification (Sprint Plan Definition)

- **Duration:** 24 continuous hours on a teammate's active handset.
- **Logging:** Every incoming call is logged to device-private `screening_soak_log.jsonl` (with masked numbers for PII privacy).
- **Pass Bar:** **Zero blocked calls from saved contacts** (100% saved-contact reliability bar).
