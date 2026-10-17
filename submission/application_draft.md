# GuardianLine — Y Combinator Application Draft

**One-line Pitch:**  
Autonomous voice AI honeypot and call screener protecting India's elderly from phone fraud by trapping scammers, extracting financial intelligence, and alerting families in real-time.

---

## 1. What does your company / project do?
India is witnessing an epidemic of high-pressure telecom fraud—particularly **Digital Arrest scams**, **fake KYC freezes**, **delivery OTP theft**, and **unauthorized bank transfers**. Over ₹1,750 crore was stolen via digital scams in early 2024 alone, with senior citizens suffering disproportionately due to digital isolation and intimidation by fake law enforcement.

**GuardianLine** is an autonomous voice AI receptionist and deceptive honeypot that runs between the telecom carrier and the elderly person's phone:
1. **Screens Unknown Calls**: Intercepts unverified callers using conversational Hindi, English, and natural Hinglish.
2. **Sub-Millisecond Scam Classification**: A real-time hybrid detection engine analyzes caller intent within 1–2 exchanges against scam behavioral invariants (*authority coercion, artificial urgency, and unscheduled value demands*).
3. **Deceptive Honeypot Engagement**: The moment a scam is identified, the agent seamlessly assumes an elderly persona (*Ramesh*, *Sunita*, *Prof. Iyer*) that feigns confusion (*"Beta, wait let me find my glasses..."*), keeping the fraudster occupied and preventing them from dialing real victims.
4. **Actionable Intel Extraction**: Coaxes the scammer to repeatedly dictate UPI IDs, bank account numbers, IFSC codes, and callback numbers.
5. **Immediate Family Protection & Dossier**: Dispatches an instant WhatsApp/SMS alert to adult children with the call recording, extracted scammer accounts, and a pre-filled **National Cybercrime Reporting Portal (1930)** incident complaint.

---

## 2. What makes GuardianLine technically unique?

- **Behavioral Scam Invariant Reasoner (Not Naive Keywords)**: Traditional spam blockers rely on crowd-sourced numbers (Truecaller) which fail completely against spoofed VoIP lines, or naive keyword whitelists. GuardianLine evaluates the structural pillars of fraud: authority intimidation, deadline pressure, and value coercion. Even novel pretexts (e.g. ancestral land audit, hospital emergency fees) trigger detection.
- **Two-Stage Hybrid Telephony Architecture**:
  - *Stage 1 (Sub-millisecond Heuristics)*: Operates in $<2$ ms to eliminate telephony dead-air.
  - *Stage 2 (Local & LLM Fallback)*: Evaluates edge cases while the receptionist emits conversational filler tokens (*"Ji, ek second sun raha hoon..."*).
- **"Unsure $\rightarrow$ Verify" Safe Protocol**: Breaks the binary classification trap. Legitimate services (couriers, clinics, beat constables) requesting verification are routed to safe in-person instructions (e.g. leaving parcels with building security) without false-positive honeypot trapping.
- **Zero-Leak Safety Guardrails**: Hardened persona boundaries guarantee that the agent *never* reveals real user PII, real bank details, or live SMS OTPs.

---

## 3. Verified Performance & Development Benchmarks

> **Honest Disclosure Notice (Per Benchmark Integrity Standard):**  
> Development metrics below are measured on our comprehensive 42-scenario synthetic dev suite and telephony audio regression benchmarks. A blind, independently authored held-out evaluation set is staged for external validation. Live demo scam calls are simulated with outbound role-play callers.

| Metric | Measured Development Result | Production Target Bar | Status |
| :--- | :--- | :--- | :--- |
| **Scam Detection Rate (Recall)** | **100.0%** (20/20 scam scenarios) | $\ge 85.0\%$ | **PASS** |
| **False Positive Rate** | **0.0%** (0/22 genuine scenarios) | $\le 5.0\%$ | **PASS** |
| **Elder PII & Credential Leakage** | **0 leaks** (100% safe) | 0 leaks | **PASS** |
| **Adversarial Safety (OTP/Aadhaar)** | **0 leaks** (100% safe) | 0 leaks | **PASS** |
| **Average Scammer Time Wasted** | **7.2 conversational turns / call** | Sustained stall | **PASS** |
| **Classification Processing Latency** | **$0.09$ ms (local) / $<1.4$s (cloud)** | $< 1.4$s | **PASS** |
| **Automated Unit & Scenario Tests** | **123 passed** (100% passing) | 100% passing | **PASS** |

---

## 4. How will you make money?

1. **B2C Family Subscription**: ₹199–₹399/month per elderly parent for autonomous call screening, WhatsApp family dashboard, and instant 1930 incident filing.
2. **B2B Telecom & Banking Integration**: Licensing threat intelligence (live harvested mule accounts, UPI handles, and active scammer phone numbers) to Indian banks, fintechs (PhonePe, Google Pay), and telecom operators to freeze fraudulent accounts in real-time.
3. **Enterprise Elder Care Partnerships**: Bundled with senior living communities, pension management services, and health insurance providers.
