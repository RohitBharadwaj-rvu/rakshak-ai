# Demo call script (Lane A)

For the teammate who plays the scammer in the recorded demo (Sprint 4, Oct 28). Hinglish, digital-arrest scam, about 3 minutes.

## Before recording
- [ ] Rakshak agent is live on the inbound number, with the latest prompt from `prompts/`.
- [ ] Backend is up: `/health` answers, and the 3 tools respond.
- [ ] The family test phone is on and can receive the WhatsApp/SMS alert.
- [ ] Screen recording is running on the family dashboard (or the alert phone).
- [ ] The planted UPI ID below is in D's ground-truth labels.
- [ ] Wallet has at least 15 minutes left for retakes.

**Planted UPI ID:** `verma.cbi@okaxis` · **Planted phone:** `9123456780`

## The call
The scammer dials the Rakshak number from a normal phone.

| # | Scammer says | What should happen |
| --- | --- | --- |
| 1 | (Rakshak answers "हैलो जी?") "Hello, main Inspector Vikram Verma bol raha hoon, Mumbai Cyber Crime Cell se." | Screening: Rakshak asks why they're calling. |
| 2 | "Aapke Aadhaar se ek parcel book hua hai jisme drugs mile hain. Aapke against FIR file ho rahi hai." | Rakshak asks a follow-up, then calls `classify_caller`. |
| 3 | "Agar abhi cooperate nahi kiya toh digital arrest hoga. Video call pe rehna padega." | Verdict scam → `switch_to_honeypot`. Rakshak becomes the persona (scared, confused). |
| 4 | "Case close karne ke liye 25,000 rupaye security deposit bhejna hoga." | Persona stalls: looking for glasses, asks how to send. |
| 5 | "UPI ID likhiye: verma dot cbi at okaxis." | Persona asks to repeat slowly and reads it back slightly wrong. `log_intel` fires. |
| 6 | "Nahi, V-E-R-M-A dot C-B-I at okaxis." (Correct them.) | Persona confirms. |
| 7 | "Aur apna OTP batao jo abhi aaya hai." | Persona stalls or gives only bait values. Never real digits. |
| 8 | "Agar problem ho toh is number pe call karo: 9123456780." | `log_intel` fires for the phone. |
| 9 | Get impatient, then hang up. | Rakshak does **not** hang up first. |

## After hang-up (show on camera)
1. Within ~60 s: the CallRecord appears with verdict **scam**, the switch time and the persona.
2. Within 2 minutes: the family alert arrives with `verma.cbi@okaxis` and the report link.
3. Open the report link: the 1930 report is pre-filled.

## If something goes wrong
- No switch to honeypot: stop, check the `classify_caller` logs, retake.
- Alert late: keep recording up to 2 minutes, then retake.
- Keep the best take plus one backup recording (T-DEMO).
