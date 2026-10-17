# GuardianLine Basic Mode Setup Guide (Zero-App Carrier Forwarding)

**Intended Users:** Elderly citizens using feature phones, non-Android smartphones (iPhones), or Android devices without the GuardianLine app.  
**Mechanism:** 3GPP Standard Conditional Call Forwarding (Unanswered Calls: `**61*`).  
**Time to Complete:** $< 5$ minutes.

---

## How Basic Mode Works

1. Any incoming call (contacts or unknown) rings the elder's handset normally for **20 to 25 seconds**.
2. If the elder answers, they speak as normal.
3. If the elder is unsure, occupied, or intentionally declines / lets it ring out, the carrier automatically redirects the call to the GuardianLine Voice Agent (`+919988776655`).
4. The GuardianLine receptionist greets the caller, assesses intent:
   - **Genuine Callers:** The agent takes a message (Caller Name, Callback Number, Reason) and immediately alerts family via WhatsApp/SMS.
   - **Scammers:** The agent detects fraudulent patterns and transitions to an elderly honeypot persona to extract evidence and file a 1930 cybercrime dossier.

---

## 3-Step Setup Instructions

### Step 1: Activate Unanswered Call Forwarding
Open the standard Phone / Dialer app on the elder's phone. Type the activation code for their carrier and press the **Call** button (green button):

* **General / All GSM Carriers:**
  ```text
  **61*+919988776655*11*25#
  ```
  *(The `*11*25#` parameter instructs the network to ring for 25 seconds before forwarding to voice speech).*

A carrier dialog will pop up stating:  
`"Call forwarding when unanswered: Registration was successful."`

---

### Step 2: Verify Configuration
Dial the interrogation code from the dialer:
```text
*#61#
```
Confirm the network displays:
- **Forwarding Status:** Active / Enabled
- **Forwarded Number:** `+919988776655` (GuardianLine Gateway)
- **Delay:** 20–25 seconds

---

### Step 3: Optional Busy Forwarding (Decline to Screen)
To allow the elder to immediately send suspected calls to the agent by pressing the **Red / Decline** button:
```text
**67*+919988776655#
```
Verify with `*#67#`.

---

## How to Undo / Deactivate (Factory Reset Calling)

If the elder ever wishes to cancel forwarding and return to standard carrier voicemail/missed call alerts, dial:

* To cancel unanswered forwarding: `##61#`
* To cancel busy forwarding: `##67#`
* To cancel all conditional forwarding at once: `##004#`
