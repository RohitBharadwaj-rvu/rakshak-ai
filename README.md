# GuardianLine

**Autonomous Voice Honeypot & Call Screening to Protect India's Elderly from Telecom Scams**

---

## Overview

India faces an unprecedented wave of sophisticated phone fraud—notably **Digital Arrest scams**, **fake KYC verification**, **delivery/courier fraud**, and **unauthorized bank transfers**. Elderly citizens are disproportionately targeted and victimized.

**GuardianLine** serves as an intelligent shield:
1. **Screening & Reception**: Unrecognized callers are screened in natural regional languages (**Hindi**, **Tamil**, and Indian English) using an ultra-low-latency voice AI receptionist.
2. **Real-time Scam Classification**: A fast mid-call language model classifies the caller intent within the first few conversational exchanges.
3. **Deceptive Honeypot Engagement**: When a scam is identified, the agent transitions seamlessly to an elderly persona (e.g., *Ramesh*, *Sunita*, *Prof. Iyer*) that plays along, acts technologically hesitant (*"Beta, wait let me find my reading glasses..."*), and keeps scammers occupied.
4. **Actionable Intel Extraction**: The agent coaxes scammers to repeat payment addresses (UPI handles), bank account numbers, IFSC codes, and callback numbers.
5. **Immediate Family Protection & Reporting**: Family members receive immediate WhatsApp/SMS notifications with captured attacker intel and an auto-generated pre-filled **1930 Cybercrime Reporting Portal** dossier.

---

## Architecture

```
[ Incoming Unknown Call ]
         │
         ▼
[ Carrier / Call Screening Interception ]
         │ (Call Forwarding: **67* / **61*)
         ▼
[ Bolna Voice Agent Gateway ] (Sarvam TTS / Indian STT)
   │                  ▲
   │ (Audio Stream)   │ (Synthesized Audio)
   ▼                  │
[ GuardianLine Backend ]
   ├── `classify_caller`     --> Rapid verdict (Scam vs Genuine)
   ├── `switch_to_honeypot`  --> Persona selection & approved fake bait
   ├── `log_intel`           --> Mid-call tokenized intelligence logging
   └── Post-Call Webhook     --> Idempotent SQLite CallRecord pipeline
                                  ├── Spoken-Number Normalizer
                                  ├── Rule & LLM Extraction Cleanup
                                  ├── Family Alerts (WhatsApp / SMS)
                                  └── Pre-filled 1930 Cybercrime Dossier
```

---

## Operating Modes

1. **App Mode (Android + Screening Role)**:
   - Intercepts unknown incoming numbers before ringing.
   - Whitelists contacts and emergency services (112, 100, 1930).
   - Forwards unknown calls to GuardianLine via carrier busy forward (`**67*`).
   - Genuine callers can be transferred back to the user without call loops.

2. **Basic Mode (Carrier Forwarding Only)**:
   - Works on any mobile phone (feature phone or smartphone) without an app.
   - Configured via standard carrier conditional forwarding (`**61*` / `**67*`).
   - Agent screens unanswered calls, takes genuine messages, and traps scammers.

---

## Project Structure & Lanes

Development is organized into four decoupled parallel tracks:

- **Lane A (`prompts/`, `bolna/`)**: Voice Agent, Prompts, Hindi/Tamil Personas, Scammer Simulation.
- **Lane B (`app/`, `contracts/`)**: Backend Server, Tool Endpoints, Normalizer, Intel Extraction, 1930 Reports.
- **Lane C (`android/`, `docs/setup/`)**: Android Screening Service, USSD Guides, Family Alerts & Dashboard.
- **Lane D (`evaluation/`, `tests/`, `scripts/`)**: Detection Classifier, Scenarios, Harness, Metrics & Benchmarks.

---

## Quickstart (Development)

### Prerequisites
- Python 3.11+
- Virtual environment (`venv`)

### Installation
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### Running Tests
```bash
pytest tests/
```

### Simulating Bolna Calls (Lane D Replay Tool)
```bash
# Replay all test fixtures to local webhook
python scripts/mock_bolna.py --url http://localhost:8000/webhook

# Replay a specific scenario fixture
python scripts/mock_bolna.py --fixture tests/fixtures/01_scam_digital_arrest.json
```

---

## Sprint Roadmap & Status

- **Sprint 0 (Oct 16–17)**: Unblock, API contracts freeze, fixture creation & mock harness.
- **Sprint 1 (Oct 18–20)**: Walking skeleton end-to-end call test & **Gate 1** (App vs Basic mode).
- **Sprint 2 (Oct 21–23)**: Hindi & Tamil personas, normalizer v2, post-call cleanup.
- **Sprint 3 (Oct 24–26)**: 1930 complaint generation, edge case hardening, **Feature Freeze**.
- **Sprint 4 (Oct 27–29)**: Measured benchmarks, elderly user pilot, and demo recording.
- **Submission (Oct 30)**: Final claims audit & release.

For full sprint details and test suite designs, see [guardianline-sprint-plan.md](guardianline-sprint-plan.md).
