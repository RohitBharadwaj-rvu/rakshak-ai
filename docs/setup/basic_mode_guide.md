# GuardianLine basic mode setup guide (zero-app carrier forwarding)

**Demo status:** Active demo mode (App Mode is cut from the demo; show Basic Mode only).  
**Intended users:** Elderly citizens on any feature phone or smartphone without installing an app.  
**Mechanism:** 3GPP standard carrier call forwarding (`**21*` unconditional for Carrier Test 1, or `**61*` unanswered rollover) and `##002#` to undo all forwarding.

---

## 1. Carrier test 1 (only if borrowing a physical SIM)

If you have a physical SIM card to test forwarding to the Bolna gateway number (`+919988776655`):

1. Turn on **Mobile Data** and **VoLTE** on the test phone.
2. Dial the unconditional forwarding code (Test 1):
   ```text
   **21*<gateway_number>#
   ```
   Or for unanswered rollover after 25 seconds:
   ```text
   **61*<gateway_number>*11*25#
   ```
3. Place a test call to the SIM and verify that the Bolna voice receptionist answers.
4. **Undo forwarding immediately after testing:**
   ```text
   ##002#
   ```
   Dialing `##002#` cancels all conditional and unconditional call forwarding rules on the SIM. If no physical SIM is available, record Carrier Test 1 as `NOT_VERIFIED` in `evaluation/carrier_results.json`.

---

## 2. Important telephony and billing notes

1. **All forwarded calls reach the voice assistant:** In Basic Mode, forwarded calls are answered by the GuardianLine receptionist, which screens the caller, switches to the elderly honeypot persona on scams, and sends a WhatsApp alert to the family.
2. **Carrier call billing:** Indian telecom operators treat a forwarded leg as an outbound call from the SIM. Standard unlimited voice plans on Jio, Airtel, and Vi cover forwarded domestic calls.
3. **Mobile data required for MMI setup:** On VoLTE networks, dialing `**21*`, `**61*`, or `##002#` communicates over the IMS Ut interface and requires mobile data to be enabled while dialing.

---

## 3. Troubleshooting "Connection problem or invalid MMI code"

1. Enable Mobile Data in Settings -> Network -> Mobile Data.
2. Ensure VoLTE is enabled in SIM settings.
3. Alternatively, open Phone App -> Settings -> Supplementary Services / Call Forwarding -> configure or disable forwarding from the UI.
4. Always dial `##002#` when finished to verify all forwarding is cleared.
