# GuardianLine app mode setup guide (Android CallScreeningService)

> [!IMPORTANT]
> **Demo cut notice:** App Mode is cut from the live demo per Gate 1 rules. The demo runs **Basic Mode only** (`docs/setup/basic_mode_guide.md`). The Android screening service (`BOLNA_GATEWAY_NUMBER` configured in `android/gradle.properties` and `android/app/build.gradle.kts`) is verified via emulator and unit test suites.

**Intended users:** Android smartphone users (Android 10 / API 29 or higher).  
**Mechanism:** Native `CallScreeningService` + conditional busy forwarding (`**67*`).

---

## How app mode works (emulator and unit test scope)

1. Inbound calls are evaluated by `GuardianCallScreeningService` (`CallScreeningLogic`):
   - **Saved contacts:** Allowed to ring (`ALLOW` / `SAVED_CONTACT`).
   - **Emergency numbers (`112`, `1930`, `100`, `108`):** Allowed to ring (`ALLOW` / `EMERGENCY_WHITELIST`).
   - **Bolna gateway number (`BuildConfig.BOLNA_GATEWAY_NUMBER`):** Allowed to ring (`ALLOW` / `BOLNA_AGENT_PROXY`).
   - **Unknown numbers:** Rejected (`SCREEN` / `UNKNOWN_CALLER_SCREEN`, `disallowCall=true, rejectCall=true`).

---

## Undo forwarding

To clear all carrier call forwarding rules on any handset after testing, dial:
```text
##002#
```
