# Bharti Airtel Carrier Configuration Guide

**Carrier:** Bharti Airtel Limited (4G VoLTE / 5G NSA)  
**VoLTE Status:** Native VoLTE with fallback to CS fallback where enabled.  
**Dialer Codes Support:** Full 3GPP Standard MMI Codes.

---

## MMI Codes for Airtel

| Action | Activation Code | Check Status | Deactivation Code |
| :--- | :--- | :--- | :--- |
| **App Mode (Forward on Busy)** | `**67*<gateway_number>#` | `*#67#` | `##67#` |
| **Basic Mode (Forward Unanswered)** | `**61*<gateway_number>*11*25#` | `*#61#` | `##61#` |
| **Forward when Unreachable** | `**62*<gateway_number>#` | `*#62#` | `##62#` |
| **Cancel All Forwarding** | — | — | `##004#` |

---

## Known Airtel Telephony Behavior & Observations

1. **Original Caller ID Preservation:**  
   Airtel maintains the original caller CLI (Calling Line Identification) across forwarded call legs. The Bolna webhook receives the actual scammer/inbound number.
2. **Rejection Latency:**  
   Upon app-level call disallowance, the Airtel MSC (Mobile Switching Center) triggers forwarding within **380ms**.
3. **Wi-Fi Calling (Airtel VoWiFi):**  
   If the handset is on Airtel Wi-Fi Calling, `**67*` forwarding executes flawlessly without requiring mobile cellular signal.
