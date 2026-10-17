# GuardianLine Basic Mode Setup Guide (Zero-App Carrier Forwarding)

**Intended Users:** Elderly citizens using basic feature phones (e.g. Nokia, JioPhone), non-Android smartphones (iPhones), or handsets without the screening app.  
**Mechanism:** 3GPP Standard Conditional Call Forwarding (Unanswered Calls: `**61*`).  
**Time to Complete:** $< 5$ minutes.

---

## Important Telephony & Billing Notice

1. **All Unanswered Calls Forward:** In Basic Mode, because no app screens calls on the device, **all unanswered calls** (including saved family contacts if the elder does not pick up within 25 seconds) will roll over to the GuardianLine voice assistant. The assistant will politely greet the caller, take a message, and send an immediate WhatsApp/SMS note to the family.
2. **Carrier Call Billing:** In India, when a call is conditionally forwarded to another number, the carrier treats the forwarded leg as an outbound call from the elder's SIM. Most standard Indian telecom plans (Jio, Airtel, Vi) include unlimited voice calling, so there are typically zero extra charges. Ensure the SIM has an active calling plan.
3. **Data Connection Requirement for MMI (XCAP/Ut):** On modern VoLTE networks (especially Jio and Airtel), USSD/MMI codes like `**61*` configure supplementary services over the IMS Ut (XCAP) interface, which requires **Mobile Cellular Data** to be toggled ON during dialing. If mobile data is turned off, the network may return an error.

---

## 3-Step Setup Instructions

### Step 1: Ensure Mobile Data is ON
Turn on mobile data on the elder's phone before dialing.

### Step 2: Activate Unanswered Call Forwarding
Open the standard Phone dialer. Dial the activation code:
```text
**61*<gateway_number>*11*25#
```
*(Replace `<gateway_number>` with your assigned GuardianLine gateway number, e.g. `+919988776655`).*

Press **Call**. A carrier confirmation dialog will display:  
`"Call forwarding when unanswered: Registration was successful."`

---

### Step 3: Verify Configuration
Dial:
```text
*#61#
```
Confirm the network displays:
- **Status:** Active / Enabled
- **Forwarded Number:** GuardianLine gateway number
- **Delay:** 20–25 seconds

---

## Troubleshooting "Connection problem or invalid MMI code"

If dialing `**61*` produces an "Invalid MMI code" error:
1. **Enable Mobile Data:** Go to Settings $\rightarrow$ Network $\rightarrow$ Mobile Data $\rightarrow$ On. Dial again.
2. **VoLTE Toggle:** Ensure VoLTE is enabled in SIM card settings.
3. **Jio Alternative:** On Jio, if standard MMI codes fail, dial `*403*<gateway_number>` (Do NOT dial `*401*`).
4. **Phone App Settings:** Alternatively, configure forwarding via UI: Phone App $\rightarrow$ Three Dots $\rightarrow$ Settings $\rightarrow$ Calling Accounts / Supplementary Services $\rightarrow$ Call Forwarding $\rightarrow$ When Unanswered $\rightarrow$ Enter gateway number.

---

## How to Deactivate / Undo

To cancel unanswered forwarding and restore default behavior:
- Dial `##61#` (or `##004#` to cancel all forwarding).
