# Vodafone Idea (Vi) Carrier Configuration Guide

**Carrier:** Vodafone Idea Limited (Vi 4G VoLTE / CS)  
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

1. [ ] Test `**67*<gateway_number>#` and `**61*` on Vi SIMs across targeted circles (Delhi, Karnataka, Maharashtra).
2. [ ] Check compatibility with legacy 2G/CS keypad phones.
3. [ ] Verify that inbound caller CLI is preserved across Vi forwarded calls.
4. [ ] Measure forwarding transfer latency.
