# GuardianLine: DPDP Act (2023) Compliance & Privacy Architecture

**Document Version:** 1.0  
**Regulatory Framework:** Digital Personal Data Protection Act (DPDP Act), 2023 (Republic of India)  
**Applicability:** Telephony Call Screening, Voice Processing, and Family Alert Systems

---

## 1. Executive Summary & Purpose

GuardianLine is designed specifically to protect senior citizens from predatory telecom fraud without compromising the privacy of the elder, legitimate callers, or family members. 

Under the **DPDP Act, 2023**, processing voice communications and personal phone records requires strict adherence to **notice**, **consent**, **purpose limitation**, and **data minimization**. This document outlines how GuardianLine complies with statutory obligations beyond initial prototype pilots.

---

## 2. Core Privacy Principles in System Architecture

### A. Clear Notice and Informed Consent (Section 5 & 6)
- **Primary User & Family Consent**: During onboarding (via the GuardianLine Android screening app or carrier USSD enrollment), the elder and their designated family caregiver provide explicit, affirmative consent for call screening.
- **Audio Screening Disclaimer (Optional Carrier Tone)**: For non-whitelisted callers, an optional short carrier tone or localized introductory disclaimer can notify incoming callers that the line is protected by call screening.

### B. Strict Purpose Limitation (Section 7)
- Telephony audio and transcripts are processed **solely** for:
  1. Classifying scam vs. genuine caller intent.
  2. Operating the deceptive honeypot to protect the user from harm.
  3. Extracting fraudster financial identifiers (UPI IDs, bank accounts) for reporting to the **1930 Cybercrime Helpline**.
- Data is **never** sold, rented, or utilized for behavioral ad targeting or credit scoring.

### C. Zero Elder Credential Retention (Data Minimization - Section 8)
- **Zero-Bait-Leak Engine**: GuardianLine’s personas (*Ramesh*, *Sunita*) utilize strictly mock, synthetic credentials generated in memory (e.g. fake test bank accounts and arbitrary digits).
- The system **never stores or requests** the user's real bank details, debit card CVVs, or live Aadhaar numbers.
- Any live SMS OTP intercepted or mentioned by third parties is scrubbed immediately from conversational memory.

### D. Ephemeral Audio Storage & Automatic Scrubbing (Storage Limitation - Section 8(7))
- **Audio Lifespan**: Telephony audio streams are retained strictly during the active call session to generate transcripts.
- **Transcript Anonymization**: Post-call processing executes automated PII redaction:
  - Caller numbers matching the user's personal address book are whitelisted locally on device.
  - Non-scam legitimate audio is purged after 24 hours unless explicitly saved by the user.
  - Confirmed scam recordings are retained in encrypted cold storage solely for evidentiary handoff to law enforcement (**1930 / I4C National Cybercrime Reporting Portal**).

### E. End-to-End Encryption & Security Safeguards (Section 8(5))
- All webhook payloads, transcripts, and intelligence metadata are encrypted in transit via **TLS 1.3** and encrypted at rest using **AES-256**.
- The `classify_caller` engine executes locally or on dedicated inference infrastructure with zero persistent third-party logging.

---

## 3. Statutory Roles Under DPDP Act

| Stakeholder | DPDP Classification | Legal Responsibility |
| :--- | :--- | :--- |
| **Elder / Family User** | **Data Principal** | Holds rights to access, correction, erasure, and grievance redressal. |
| **GuardianLine Platform** | **Data Fiduciary** | Determines purpose and means of fraud prevention processing; enforces security safeguards. |
| **Telephony Gateway (Bolna / Plivo / Exotel)** | **Data Processor** | Transports audio streams under strict data processing agreements (DPA). |

---

## 4. Grievance Redressal Mechanism (Section 13)
A designated Data Protection Officer (DPO) and in-app one-click consent revocation mechanism allow users to:
1. Export all captured call logs associated with their phone number.
2. Request immediate deletion of all call transcripts and audio snippets.
3. Opt out of automated screening at any time by dialing standard carrier cancellation codes (`##67#` / `##61#`).
