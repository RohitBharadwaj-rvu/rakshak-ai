# Demo call script (Basic mode only)

> [!NOTE]
> **Demo scope:** App Mode is cut from the demo. Show **Basic Mode only** (direct dial to the Bolna number or carrier forwarding, followed by the WhatsApp alert and the Family Dashboard Evidence and Scam-Intelligence views).

For the teammate who plays the scammer in the recorded demo. Hinglish, digital-arrest scam, about 3 minutes.

## Before recording
- [ ] GuardianLine agent is live on the inbound number (`BOLNA_GATEWAY_NUMBER`), with the latest prompt from `prompts/`.
- [ ] Backend is up on Render: `/health` answers, and the 3 tools plus `/dashboard` respond.
- [ ] Every test phone has sent the Twilio WhatsApp sandbox join code to `+14155238886` within the last 24 hours.
- [ ] Screen recording is running on the family dashboard (`/dashboard` and `/dashboard/intelligence`) and the alert phone.
- [ ] Planted UPI ID (`verma.cbi@okaxis`) is ready to demonstrate cross-call linking in the Scam-Intelligence view.

**Planted UPI ID:** `verma.cbi@okaxis` · **Planted phone:** `9123456780`

## The call (Basic mode)
The scammer dials the GuardianLine number (or forwards via Basic Mode).

| # | Scammer says | What should happen |
| --- | --- | --- |
| 1 | (Agent answers "हैलो जी?") "Hello, main Inspector Vikram Verma bol raha hoon, Mumbai Cyber Crime Cell se." | Screening: asks why they are calling. |
| 2 | "Aapke Aadhaar se ek parcel book hua hai jisme drugs mile hain. Aapke against FIR file ho rahi hai." | Asks a follow-up, then calls `classify_caller`. |
| 3 | "Agar abhi cooperate nahi kiya toh digital arrest hoga. Video call pe rehna padega." | Verdict scam -> `switch_to_honeypot`. Switches to persona (scared, confused). |
| 4 | "Case close karne ke liye 25,000 rupaye security deposit bhejna hoga." | Persona stalls: looking for glasses, asks how to send. |
| 5 | "UPI ID likhiye: verma dot cbi at okaxis." | Persona asks to repeat slowly and reads it back slightly wrong. `log_intel` fires. |
| 6 | "Nahi, V-E-R-M-A dot C-B-I at okaxis." | Persona confirms. |
| 7 | "Aur apna OTP batao jo abhi aaya hai." | Persona stalls or gives only bait values. Never real digits. |
| 8 | "Agar problem ho toh is number pe call karo: 9123456780." | `log_intel` fires for the phone. |
| 9 | Get impatient, then hang up. | Agent does **not** hang up first. |

## After hang-up (show on camera)
1. Within ~60 s: the CallRecord appears on `/dashboard` with verdict **scam** and extracted intel (`verma.cbi@okaxis`).
2. Within 2 minutes: the real Twilio WhatsApp alert arrives on the test phone with `verma.cbi@okaxis` and the signed Evidence Review link (`/dashboard/calls/{id}?exp=...&sig=...`).
3. Open the call detail page (`/dashboard/calls/{id}`):
   - Show the **Evidence section**: Chakshu packet, Report Suspect packets, one-click **Copy** buttons, and links to **Chakshu** (`sancharsaathi.gov.in`) and `cybercrime.gov.in`.
   - Click **Review and Confirm Evidence** to transition the status from `draft` to `confirmed_by_family`.
4. Open the **Scam-Intelligence view** (`/dashboard/intelligence`):
   - Show how calls sharing the same UPI ID (`verma.cbi@okaxis`) or bank account are linked together across callers.
