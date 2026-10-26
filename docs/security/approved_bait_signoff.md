# GuardianLine Approved Bait Sign-Off & Rotating Persona Specification

## 1. Human Sign-Off Requirement Policy
Under the GuardianLine sprint safety charter, the rotating fake bait values used by honeypot personas (*Ramesh Sharma*, *Sunita Verma*, *Prof. S. Iyer*, and 17 additional regional personas) require **two designated human reviewers**.

> [!IMPORTANT]
> **AI approvals do NOT count.** An automated model, agent, or LLM evaluation has zero authority to approve fake bait values. Formal approval requires dual human sign-off recorded in this registry.

---

## 2. Deterministic Rotating Bait Pool (`get_rotating_bait`)

`get_rotating_bait(call_id)` uses `hashlib.sha256(call_id).digest()` to deterministically select 1 persona from 20 regional Indian elderly personas:

| Persona | City & Bank | IFSC Code | Account Number (Luhn-valid) | UPI VPA | Phone Number |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Ramesh Sharma (72)** | Lucknow · SBI | `SBIN0000125` | `30984716255` | `rsharma72@oksbi` | `9415023481` |
| **Sunita Verma (68)** | Jaipur · PNB | `PUNB0021400` | `0214000109482713` | `sverma68@pnb` | `9829041726` |
| **Prof. S. Iyer (75)** | Chennai · Canara | `CNRB0001234` | `1234101048290` | `siyer75@cnrb` | `9444061829` |
| **Kantilal Patel (71)** | Vadodara · BoB | `BARB0VJBARO` | `01290100048293` | `kpatel71@barodampay` | `9824071638` |
| **Subhash Chatterjee (76)** | Kolkata · UCO | `UCBA0000002` | `00020110048293` | `schatterjee76@ybl` | `9830142869` |

All 20 persona bait values are automatically registered in `APPROVED_BAIT_VALUES` so that `extractor.py`, `cleanup.py`, and `store.py` never classify persona bait as scammer intelligence.

---

## 3. Human Review & Sign-Off Checklist

Dual sign-off is required prior to deploying honeypot personas in production or live telecom tests:

- **Reviewer 1 (Project Lead / User):** `[PENDING REVIEW]`
- **Reviewer 2 (Co-reviewer / Legal/Safety Lead):** `[PENDING APPOINTMENT & REVIEW]`

**Current Sign-Off Status:** ⏳ **AWAITING DUAL HUMAN SIGN-OFF**
