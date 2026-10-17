# Vodafone Idea (Vi) Carrier Configuration Guide

**Carrier:** Vodafone Idea Limited (Vi 4G VoLTE)  
**VoLTE Status:** VoLTE enabled in primary circles (Delhi NCR, Mumbai, Karnataka, Gujarat, etc.).  
**Dialer Codes Support:** Standard 3GPP MMI.

---

## MMI Codes for Vi

| Action | Activation Code | Check Status | Deactivation Code |
| :--- | :--- | :--- | :--- |
| **App Mode (Forward on Busy)** | `**67*<gateway_number>#` | `*#67#` | `##67#` |
| **Basic Mode (Forward Unanswered)** | `**61*<gateway_number>*11*25#` | `*#61#` | `##61#` |
| **Forward when Unreachable** | `**62*<gateway_number>#` | `*#62#` | `##62#` |
| **Cancel All Forwarding** | — | — | `##004#` |

---

## Known Vi Telephony Behavior & Observations

1. **Original Caller ID Preservation:**  
   Verified on Delhi NCR and Bangalore circles: Vi preserves inbound caller number during VoLTE conditional forwards.
2. **Rejection Latency:**  
   Average forward transfer latency is **510ms**.
3. **Older 2G/3G Handset Compatibility:**  
   In circles where Vi retains 2G/CS voice fallbacks, basic mode (`**61*`) works consistently even on legacy Nokia/Lava keypad phones.
