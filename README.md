# GuardianLine

**Autonomous Voice Honeypot & Call Screening to Protect India's Elderly from Telecom Scams**

---

## Overview

India faces an unprecedented wave of sophisticated phone fraud—notably **Digital Arrest scams**, **fake KYC verification**, **delivery/courier fraud**, and **unauthorized bank transfers**. Elderly citizens are disproportionately targeted and victimized.

**GuardianLine** serves as an intelligent shield:
1. **Screening & Reception**: Unrecognized callers are screened in natural languages (**Hindi**, **English**, and **Hinglish**; standardized strictly to Hindi, English, and Hinglish, replacing earlier Tamil draft targets) using an ultra-low-latency voice AI receptionist.
2. **Real-time Scam Classification**: A fast mid-call language model classifies the caller intent within the first few conversational exchanges.
3. **Deceptive Honeypot Engagement**: When a scam is identified, the agent transitions seamlessly to an elderly persona (*Ramesh*) that plays along, acts technologically hesitant (*"Beta, wait let me find my reading glasses..."*), and keeps scammers occupied.
4. **Actionable Intel Extraction**: The agent coaxes scammers to repeat payment addresses (UPI handles), bank account numbers, IFSC codes, and callback numbers.
5. **Immediate Family Protection & Reporting**: Family members receive immediate WhatsApp/SMS notifications with captured attacker intel and pre-formatted **Chakshu (DoT Sanchar Saathi)** and **Report Suspect** packets (with National Cybercrime 1930 escalation when money has been lost).

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
                                  └── Chakshu and Report Suspect Packets
```

---

## Operating Modes

1. **Basic Mode (Primary Demo Mode: Carrier Forwarding Only)**:
   - Works on any mobile phone (feature phone or smartphone) without an app.
   - Configured via standard carrier conditional forwarding (`**61*` / `**67*`; dial `##002#` to undo all conditional forwarding).
   - Agent screens unanswered calls, takes genuine messages, and traps scammers.
   - Live demos show Basic Mode only.

2. **App Mode (Android + Screening Role, Cut from Live Demo)**:
   - Tested in the Android emulator with `BOLNA_GATEWAY_NUMBER` configured: saved contacts ring, unknown numbers are rejected to trigger carrier busy forwarding (`**67*`), emergency numbers (`112`, `1930`) ring, and the Bolna gateway number rings.
   - Cut from the live demo to keep the setup focused on Basic Mode.

---

## Project Structure & Lanes

Development is organized into four decoupled parallel tracks:

- **Lane A (`prompts/`, `bolna/`)**: Voice Agent, Prompts, Hindi/English Personas, Scammer Simulation.
- **Lane B (`app/`, `contracts/`)**: Backend Server, Tool Endpoints, Normalizer, Intel Extraction, Chakshu and Report Suspect Packets.
- **Lane C (`android/`, `app/core/gui.py`, `app/notify/`, `docs/setup/`)**: Basic Mode USSD Guides, Family WhatsApp Alerts, Family Dashboard (Evidence section with copy buttons, links to Chakshu `sancharsaathi.gov.in` and `cybercrime.gov.in`, review-and-confirm workflow, and cross-call Scam-Intelligence view linking shared UPI IDs and bank accounts), and Android CallScreeningService.
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
- **Sprint 2 (Oct 21–23)**: Hindi & English personas (with Hinglish), normalizer v2, post-call cleanup.
- **Sprint 3 (Oct 24–26)**: Chakshu and Report Suspect packet generation, edge case hardening, **Feature Freeze**.
- **Sprint 4 (Oct 27–29)**: Measured benchmarks, elderly user pilot, and demo recording.
- **Submission (Oct 30)**: Final claims audit & release.

For full sprint details and test suite designs, see [guardianline-sprint-plan.md](guardianline-sprint-plan.md).

---

## Evaluation Benchmark & Integrity Status

> [!IMPORTANT]
> **Benchmarking & Field Evaluation Integrity Notice:**
> - Development metrics are measured strictly against an internal synthetic dev set.
> - An internal 20-scenario **agent-written evaluation set (not blind)** recorded 50.0% direct detection with 0.0% false negatives (remaining scams held in defensive verify/unsure). An external, independent human held-out benchmark is pending.
> - Whitelist loophole probe (`scripts/probe_whitelist_holes.py`) verifies 0/6 exploits bypass the classifier after enforcing the general invariant safety rule (`f48301c`).
> - Telephony audio checks (`scripts/run_audio_format_check.py`) verify 8kHz mono PCM telephony codec formatting and manifest turn logic; they do not benchmark acoustic speech-to-text (STT) accuracy.
> - **Carrier Test 1 (`evaluation/carrier_results.json`)**: Marked `NOT_VERIFIED` pending a physical Indian SIM card test (dial `##002#` afterwards to undo conditional call forwarding).
> - **3-Participant Consent Pilot (`evaluation/pilot_results.json`)**: Marked `NOT_DONE` (`0/3` completed sessions); no synthetic participant responses are fabricated.
