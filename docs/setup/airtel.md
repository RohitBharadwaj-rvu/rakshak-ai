# Bharti Airtel Carrier Configuration Guide

**Carrier:** Bharti Airtel Limited (4G VoLTE / 5G NSA)  
**Standard Telecom Forwarding:** 3GPP GSM MMI Codes

---

## 3GPP Standard MMI Codes

| Action | Activation Code | Check Status | Deactivation Code |
| :--- | :--- | :--- | :--- |
| **App Mode (Forward on Busy)** | `**67*<gateway_number>#` | `*#67#` | `##67#` |
| **Basic Mode (Forward Unanswered after 25s)** | `**61*<gateway_number>*11*25#` | `*#61#` | `##61#` |
| **Forward when Unreachable** | `**62*<gateway_number>#` | `*#62#` | `##62#` |
| **Cancel All Conditional Forwarding** | — | — | `##004#` |

---

## To Verify in T-CARRIER (Physical SIM Field Checklist)

1. [ ] Confirm whether `**67*<gateway_number>#` registers via Airtel VoLTE without "Connection problem or invalid MMI code" error.
2. [ ] Verify whether mobile data needs to be toggled on to allow supplementary service registration (XCAP/Ut).
3. [ ] Verify that inbound caller CLI is preserved when forwarded from Airtel to the Bolna gateway number.
4. [ ] Measure carrier redirection latency on call rejection.
