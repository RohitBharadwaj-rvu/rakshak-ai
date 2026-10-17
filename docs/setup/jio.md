# Reliance Jio Carrier Configuration Guide

**Carrier:** Reliance Jio Infocomm Ltd (4G LTE / 5G SA)  
**Standard Telecom Forwarding:** 3GPP GSM MMI Codes (Recommended)

---

## 3GPP Standard MMI Codes (Recommended & Safe)

To avoid forwarding saved family contacts, **only conditional forwarding** should be configured:

| Action | Activation Code | Check Status | Deactivation Code |
| :--- | :--- | :--- | :--- |
| **App Mode (Forward on Busy)** | `**67*<gateway_number>#` | `*#67#` | `##67#` |
| **Basic Mode (Forward Unanswered after 25s)** | `**61*<gateway_number>*11*25#` | `*#61#` | `##61#` |
| **Forward when Unreachable / Switched Off** | `**62*<gateway_number>#` | `*#62#` | `##62#` |
| **Cancel All Conditional Forwarding** | — | — | `##004#` |

> [!CAUTION]
> **Warning on Jio Star-Codes (`*401*` vs `*405*`):**  
> On Jio, `*401*<number>` activates **Unconditional Call Forwarding** (all calls, including family, forward immediately without ringing). **Never use `*401*` for GuardianLine.**  
> If using Jio proprietary star codes instead of 3GPP MMI codes:  
> - Forward on Busy: `*405*<gateway_number>` (Cancel: `*406`)  
> - Forward when Unanswered: `*403*<gateway_number>` (Cancel: `*404`)  
> - Forward when Unreachable: `*409*<gateway_number>` (Cancel: `*410`)  
> - Cancel All: `*413`  
> Standardize on the 3GPP codes (`**67*` / `**61*`) whenever possible.

---

## To Verify in T-CARRIER (Physical SIM Field Checklist)

1. [ ] Confirm whether `**67*<gateway_number>#` registers cleanly via Jio VoLTE (or requires mobile data on for XCAP/Ut).
2. [ ] Measure seconds elapsed between device rejection and Bolna SIP leg answer.
3. [ ] Verify that inbound caller CLI (Calling Line Identification) is preserved in Bolna webhook headers across VoLTE forward.
4. [ ] Test behavior when handset is on Jio VoWiFi (Wi-Fi Calling).
