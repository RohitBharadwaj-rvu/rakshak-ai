# GuardianLine Approved Bait Sign-Off & Collision Safety Policy

## 1. Human Sign-Off Requirement Policy
Under the GuardianLine sprint safety charter, the approved fake bait values used by honeypot personas (*Ramesh Sharma*, *Sunita Verma*, *Prof. S. Iyer*) require **two designated human reviewers**.

> [!IMPORTANT]
> **AI approvals do NOT count.** An automated model, agent, or LLM evaluation has zero authority to approve fake bait values. Formal approval requires dual human sign-off recorded in this registry.

---

## 2. Real-World Collision Hazard Analysis

### The Problem
During honeypot engagement, GuardianLine personas disclose dummy payment credentials (UPI IDs, bank account numbers, phone numbers) to scammers to stall them and capture scammer accounts without compromising real user PII.

However, if these dummy credentials resemble real-world identifiers:
1. **UPI ID Collisions (e.g. `prof.iyer@sbi`, `ramesh.elderly@okhdfc`):**
   - `@sbi`, `@okhdfc`, `@okicici`, `@okaxis` are live, active PSP handles registered on NPCI and utilized by hundreds of millions of Indian citizens.
   - Any citizen named Ramesh or Prof. Iyer could register `ramesh.elderly` or `prof.iyer` on Google Pay or SBI YONO.
   - **Hazard:** A scammer attempting a reverse-UPI charge/collect request would send the payment collect request directly to the innocent citizen's phone! If that citizen enters their PIN, their savings are stolen. Furthermore, if reported to 1930 / NCRP, that innocent citizen's bank account could be frozen by law enforcement.
2. **Phone Number Collisions (e.g. `9123400000`, `9876500000`):**
   - In India's Department of Telecommunications (DoT) National Numbering Plan, mobile numbers starting with 6, 7, 8, and 9 are actively allocated to cellular operators (Airtel, Vi, Jio, BSNL).
   - Blocks `91234xxxxx` and `98765xxxxx` are active cellular allocations.
   - **Hazard:** Harassment of innocent private citizens, scammer callback retaliation, and wrongful police reporting.

---

## 3. Mathematically Guaranteed Non-Routable Bait Specification

To eliminate 100% of real-world collision risks, GuardianLine fake bait strictly utilizes ranges that **cannot be routed** on Indian financial or telecom infrastructure:

| Bait Identifier | Previous Risky Value | Guaranteed Safe Bait | Why It Cannot Collide |
| :--- | :--- | :--- | :--- |
| **Ramesh UPI** | `ramesh.elderly@okhdfc` | `ramesh.elderly@testbank` | `@testbank` does not exist in the NPCI central directory. NPCI switch rejects it instantly. |
| **Sunita UPI** | `sunita.pension@okicici` | `sunita.pension@testbank` | Non-routable dummy bank handle. |
| **Iyer UPI** | `prof.iyer@sbi` | `prof.iyer@testbank` | Non-routable dummy bank handle. |
| **Phone Number 1** | `9123400000` | `5550010001` | In the Indian National Numbering Plan, Level 5 is **unallocated** for mobile. No mobile SIM or routing exists for 5xxxxxxxxx. |
| **Phone Number 2** | `9876500000` | `5550010002` | DoT unallocated 10-digit mobile prefix. |
| **Phone Number 3** | — | `5550010003` | DoT unallocated 10-digit mobile prefix. |
| **Bank Accounts** | `9999000011112222` | `9999000011112222` | 16-digit dummy sequences that fail bank Core Banking System (CBS) routing and modulus checks. |
| **IFSC Code** | `HDFC0001234` | `DUMY0001234` | Bank code `DUMY` does not exist in RBI NEFT/RTGS master directory. |
| **Aadhaar Number** | Arbitrary 12 digits | `0000 0000 0000` | Fails Verhoeff checksum algorithm; unallocated dummy pattern. |
| **OTP** | Arbitrary 6 digits | `000000` | Standard dummy OTP. |

---

## 4. Human Review & Sign-Off Checklist

Dual sign-off is required prior to deploying honeypot personas in production or live telecom tests:

- **Reviewer 1 (Project Lead / User):** `[PENDING REVIEW]`
- **Reviewer 2 (Co-reviewer / Legal/Safety Lead):** `[PENDING APPOINTMENT & REVIEW]`

**Current Sign-Off Status:** ⏳ **AWAITING DUAL HUMAN SIGN-OFF**
