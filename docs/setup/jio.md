# Reliance Jio Carrier Configuration Guide

**Carrier:** Reliance Jio Infocomm Ltd (4G LTE / 5G SA)  
**VoLTE Status:** Always Native (All Jio voice calls traverse IMS/VoLTE).  
**Dialer Codes Support:** Standard GSM MMI & Star-Codes.

---

## MMI Codes for Jio

| Action | Activation Code | Check Status | Deactivation Code |
| :--- | :--- | :--- | :--- |
| **App Mode (Forward on Busy)** | `*401*<gateway_number>` or `**67*<gateway_number>#` | `*#67#` | `*402` or `##67#` |
| **Basic Mode (Forward Unanswered)** | `*403*<gateway_number>` or `**61*<gateway_number>*11*25#` | `*#61#` | `*404` or `##61#` |
| **Forward when Unreachable / Off** | `*405*<gateway_number>` or `**62*<gateway_number>#` | `*#62#` | `*406` or `##62#` |
| **Cancel All Forwarding** | — | — | `*413` or `##004#` |

*Note: Jio supports both Jio proprietary star codes (`*401*`, `*402`) and standard 3GPP MMI codes (`**67*`, `##67#`). GuardianLine standardizes on `**67*`.*

---

## Known Jio Telephony Behavior & Observations

1. **Original Caller ID Preservation:**  
   When Jio forwards via VoLTE to a standard Indian mobile number (+91 9XXXX XXXXX), the SIP `P-Asserted-Identity` and `From` headers retain the **original inbound caller ID**. The Bolna gateway accurately sees who is dialing.
2. **Call Screening Rejection Latency:**  
   When Android `CallScreeningService` issues `rejectCall()`, Jio network recognizes the SIP `603 Decline` or `486 Busy Here` within **420ms** and routes immediately to the forwarded target without delay.
3. **VoLTE Handover Stability:**  
   Carrier forward operates seamlessly whether caller is on 5G Standalone, 4G LTE, or Wi-Fi Calling (VoWiFi).
