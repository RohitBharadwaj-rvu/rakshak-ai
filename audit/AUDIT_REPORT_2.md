# GUARDIANLINE INDEPENDENT AUDIT REPORT #2
**Audit Timestamp:** 2026-10-20 19:42:00 IST  
**Auditor Mode:** Objective External Verification (Read-Only)  
**Target Repository:** `RohitBharadwaj-rvu/rakshak-ai`  
**Base Ref Under Audit:** `origin/voice` (commit `8db909f`) with comparative lane branches  

---

## 1. END-TO-END CALL TRACE

Walking one scam call through every architectural hop from telephony arrival to family protection dashboard:

| Hop # | Step | Status | Concrete Evidence |
| :---: | :--- | :---: | :--- |
| **1** | **Caller dials Bolna number** | **UNVERIFIED** | `android/app/build.gradle.kts:20` defaults `BOLNA_GATEWAY_NUMBER` to empty string `""`. `evaluation/carrier_results.json:7` is `PENDING_FIELD_TESTS` with 0 attempts across Jio, Airtel, Vi. `BOLNA_API_KEY` is missing from local `.env`, preventing live inbound telephony mapping verification via Bolna API. |
| **2** | **Bolna agent answers with repo prompt** | **BROKEN / UNVERIFIED** | `origin/voice` contains no `prompts/` directory and no `bolna/` directory. Across branches, 3 divergent prompt hashes exist: `SprintA:bolna/rakshak-v0.json` (SHA-256: `86a4e3cc...`, Ramesh Kumar, Jaipur), `SprintA:prompts/rakshak-v1-two-mode.md` (SHA-256: `28e786c3...`, Ramesh Sharma, Lucknow), and `lane-d:prompts/rakshak-v1-two-mode.md` (SHA-256: `a5d81045...`). Live Bolna agent prompt cannot be verified without `BOLNA_API_KEY`. |
| **3** | **`classify_caller` hits Render backend** | **BROKEN** | Endpoint is reachable on Render (`https://rakshak-ai-3ckj.onrender.com/tools/classify_caller`), but on `origin/voice` and `lane-d`: (1) Groq requests hardcoded model `llama-3.3-70b-versatile` which returns HTTP 404 (`model_not_found`, confirmed against Groq `GET /openai/v1/models` where only `openai/gpt-oss-20b` is active); (2) Gemini Flash request to `gemini-flash-latest` timed out (>10s); (3) Code falls back to naive offline rules where `scripts/probe_whitelist_holes.py` confirms **4 out of 6 scam attack vectors are labeled `GENUINE`** (confidence 0.08). |
| **4** | **`switch_to_honeypot` hits Render** | **PARTIAL / MISMATCH** | Endpoint returns persona `Ramesh Kumar` / `Ramesh Sharma` (72-year-old grandfather), but Bolna config (`SprintA:bolna/rakshak-v0.json:35`) configures Sarvam `bulbul:v3` voice `Simran`—a **female voice**. |
| **5** | **Extraction playbook used** | **NOT DONE** | Mule-rotation extraction playbook (initial ask, payment failed, name mismatch, IFSC, callback, repeat-back, and "never say payment succeeded" rule) does not exist in any prompt or code file in the repository (0 git commits match `value_raw`, `elicitation`, or `actionable_identifiers`). |
| **6** | **`log_intel` stores identifiers** | **PARTIAL** | Tool endpoint exists on Render, but accepts only legacy fields (`type`, `value`, `call_id`). Extended fields (`kind`, `value_raw`, `value_normalized`, `elicitation`, `turn_index`, `quote`, `status`) are not implemented. |
| **7** | **Call ends** | **VERIFIED** | Handset disconnect / caller hangup triggers Bolna call completion. |
| **8** | **Webhook reaches Render** | **VERIFIED (on deployed branch only)** | Render backend is running code from `origin/lane-b` (`app/main.py:17`, `app/voice/webhook.py:14`). However, `origin/voice` HEAD contains neither `app/main.py` nor `render.yaml`. |
| **9** | **CallRecord persisted (survives restart?)** | **BROKEN (EPHEMERAL)** | `origin/lane-b:render.yaml:15` sets `GUARDIANLINE_DB_PATH: /tmp/guardianline_calls.db`. No `DATABASE_URL` is configured in `render.yaml`. Free-tier Render dynos spin down after 15 minutes of inactivity; **all records stored in `/tmp` are wiped upon restart**. |
| **10** | **Evidence packets built** | **NOT DONE** | Chakshu packet builder, Report Suspect packet, transcript SHA-256 hashing, and verification endpoints (`/api/calls/{id}/evidence/verify`) do not exist in the codebase. Only the legacy 1930 text draft exists. |
| **11** | **Family WhatsApp alert delivered** | **BROKEN** | No `TWILIO_*` credentials exist in local `.env`. 0 real Twilio Message SIDs exist anywhere in git history. Alerts function solely via unit test `MagicMock` instances. |
| **12** | **Dashboard shows call + packets** | **CANNOT VERIFY / NOT DONE** | `GUARDIANLINE_API_TOKEN` / `GUARDIAN_DASHBOARD_TOKEN` is missing from `.env` (GET `/api/calls` returns HTTP 401 Unauthorized). The dashboard GUI contains no evidence packet sections or confirmation buttons. |

**Bottom Line Sentence:**
> *Today, a real call gets as far as: reaching an answering Bolna agent that attempts to call the deployed Render backend tool endpoints, but fails Stage 2 LLM classification, speaks with a female voice as a 72-year-old grandfather, stores call records in a temporary SQLite database that is wiped upon Render spin-down, and cannot send family alerts or build evidence packets.*

---

## 2. SUMMARY TABLE (A1 – L5)

| ID | Item | Status | One-Line Finding |
| :---: | :--- | :---: | :--- |
| **A1** | Branch Commits & Tracking | **VERIFIED** | 6 local branches tracked; `voice` has 15 unpushed local-only commits ahead of `origin/voice`. |
| **A2** | Branch Ancestry & Integration | **VERIFIED** | `integration`, `feat/mule-extraction`, and `feat/evidence-packets` do not exist; only `lane-c` is merged into `origin/voice`. |
| **A3** | Local `voice` vs `origin/voice` | **VERIFIED** | Local `voice` (`349c832`) is NOT equal to `origin/voice` (`8db909f`); `audit-temp-merge` does not exist; 0 leftover worktrees. |
| **A4** | Recent `origin/voice` Commits | **VERIFIED** | Exactly 0 commits have landed on `origin/voice` since 2026-10-18 00:00 IST (latest commit: 2026-10-17 14:54 IST). |
| **A5** | Merge Conflict Markers | **VERIFIED** | `git grep -n -E "(<<<<<<<\|>>>>>>>)" origin/voice` returned 0 matches (completely clean). |
| **B1** | Automated Test Suite | **VERIFIED** | `pytest` on `origin/voice` executed in 11.47s: **169 passed, 0 failed, 0 skipped, 1 warning**. |
| **B2** | Live vs Mocked Services | **VERIFIED** | 0 tests touch live networks; Bolna, Twilio, Groq, and Gemini are 100% mocked via `MagicMock()` or `monkeypatch`. |
| **C1** | Render Configuration | **VERIFIED** | `render.yaml` does not exist on `origin/voice`; deployed branch is `lane-b` (free plan, uvicorn entrypoint, `/tmp` SQLite). |
| **C2** | Render `/health` Probe | **VERIFIED** | `GET /health` returned HTTP 200 OK (0.34s cold, 0.19s warm) with `{"status":"ok","service":"guardianline-backend"}`; no commit hash exposed. |
| **C3** | Backend Persistence | **VERIFIED** | Code supports Postgres mirror (`store.py:78`), but `render.yaml` sets only `/tmp/guardianline_calls.db` without `DATABASE_URL`. |
| **C4** | Live CallRecords via `/api/calls` | **CANNOT VERIFY** | `GUARDIANLINE_API_TOKEN` / `GUARDIAN_DASHBOARD_TOKEN` is absent from `.env`; `GET /api/calls` returns HTTP 401 Unauthorized. |
| **C5** | Keep-Alive Mechanism | **NOT DONE** | Zero cron jobs, uptime pingers, or background keep-alives exist; free-tier dyno sleeps after 15 min inactivity. |
| **D1** | `BOLNA_API_KEY` Existence | **VERIFIED** | `BOLNA_API_KEY` is absent / empty in local `.env` (`exists=False`). |
| **D2** | Live Bolna Agents List | **CANNOT VERIFY** | Blocked by missing `BOLNA_API_KEY`; human dashboard checklist provided below. |
| **D3** | Live Call Executions | **CANNOT VERIFY** | Blocked by missing `BOLNA_API_KEY`; human dashboard checklist provided below. |
| **D4** | Bolna Verification Checklist | **VERIFIED** | Complete 5-point manual inspection checklist compiled for dashboard verification. |
| **D5** | Repo Bolna Config Status | **PARTIAL** | `bolna/rakshak-v0.json` exists only in `SprintA` (not in `voice` or `lane-d`), with outdated fallback persona (`Jaipur`). |
| **E1** | Classifier Loophole Fix History | **VERIFIED** | General safety rule fix `f48301c` exists on `lane-d`, but was **never merged into `origin/voice`**. |
| **E2** | Classifier Rule Structure | **FAILED** | `origin/voice` relies on probe-specific contextual whitelists; general invariant rule is absent. |
| **E3** | Whitelist Probe Execution | **FAILED** | `scripts/probe_whitelist_holes.py` on `origin/voice` confirmed **4/6 probe scenarios successfully exploited whitelist loopholes**. |
| **E4** | Blind Held-Out Dataset | **NOT DONE** | `evaluation/held_out_scenarios.json` does not exist on any branch; `scripts/run_held_out_eval.py` fails with exit code 1. |
| **E5** | Stage 2 Live LLM Execution | **FAILED** | Groq returned HTTP 404 (`llama-3.3-70b-versatile` not found); Gemini timed out (>10s); 0 successful Stage 2 calls. |
| **E6** | `stage2_ran` Column Tracking | **PARTIAL** | Implemented on `origin/lane-b` (`store.py:176`), but completely missing from `origin/voice`. |
| **F1** | Mule Playbook in Prompts | **NOT DONE** | Playbook and "never say payment succeeded" rule are absent from all prompt files. |
| **F2** | `log_intel` Schema Expansion | **NOT DONE** | New fields (`kind`, `value_raw`, `elicitation`, `status`) do not exist in schemas, contracts, or code. |
| **F3** | Bolna Tool Definition Update | **NOT DONE** | Tool parameters in `SprintA:bolna/rakshak-v0.json` remain legacy `type` and `value`. |
| **F4** | Actionable Identifiers Metric | **NOT DONE** | `scripts/compute_metrics.py` does not track or report `actionable_identifiers_per_call`. |
| **F5** | Mule Scenarios & Test Harness | **NOT DONE** | No mule-rotation scenarios exist; payment-success phrase guard is absent. |
| **F6** | Addition 1 Test Suite | **NOT DONE** | Exactly 0 tests exist for Addition 1 features across all branches. |
| **G1** | Chakshu Packet Builder | **NOT DONE** | Chakshu packet generator does not exist in any file. |
| **G2** | Report Suspect Packet | **NOT DONE** | Report Suspect per-identifier packet structure is not implemented. |
| **G3** | 1930 `money_lost` Gate | **FAILED** | Legacy 1930 draft generates for all scam calls regardless of whether money was lost. |
| **G4** | Evidence Integrity Hash | **NOT DONE** | Transcript/recording SHA-256 hashing and `/api/calls/{id}/evidence/verify` are absent. |
| **G5** | Human Review Workflow | **NOT DONE** | Dashboard contains no review buttons, no external portal links, and no `/evidence/confirm` endpoint. |
| **G6** | WhatsApp Review Link | **NOT DONE** | Alert dispatcher sends direct report links, not evidence review links. |
| **G7** | PII Leak & Legal Claim Guard | **NOT DONE** | No tests verify exclusion of parent PII from evidence packets. |
| **G8** | Evidence Framing Update | **NOT DONE** | Repository continues to frame output as "1930 Cybercrime Dossier" across README and application drafts. |
| **H1** | Voice vs Persona Consistency | **FAILED** | **BLATANT MISMATCH**: Sarvam TTS voice `Simran` (Female) speaks as 72-year-old grandfather `Ramesh` (Male). |
| **H2** | Second Agent / Handoff | **NOT DONE** | No second agent, transfer-based handoff, or male voice is configured in Bolna. |
| **H3** | Parent Name Dynamic Injection | **FAILED** | Persona name is hardcoded (`Ramesh Kumar` / `Ramesh Sharma`); no session variable (`%(parent_name)s`) is injected. |
| **I1** | Android Bolna Gateway Config | **PARTIAL** | Whitelisted in logic (`CallScreeningLogic.kt:60`), but `BOLNA_GATEWAY_NUMBER` defaults to empty string `""`. |
| **I2** | Android Test Suite Execution | **VERIFIED** | Gradle `:app:testDebugUnitTest` executed and passed in 43s (**16 tests, 0 failures**). |
| **I3** | Physical Device Test Evidence | **NOT DONE** | Protocol exists in `docs/tests/android.md`, but zero device logs, soak records, or screenshots exist. |
| **I4** | Status of Addition 1 Overall | **NOT STARTED** | Zero code, prompts, or tests exist across all branches. |
| **I5** | Status of Addition 2 Overall | **NOT STARTED** | Zero code, prompts, or tests exist across all branches. |
| **J1** | Alert Channel & DLT Config | **PARTIAL** | WhatsApp sandbox configured (`+14155238886`); TRAI DLT SMS registration is absent. |
| **J2** | Real Delivered Message Proof | **NOT DONE** | Zero real Twilio Message SIDs exist in git history or database logs; only mock SIDs exist. |
| **K1** | Live Calls Directory | **NOT DONE** | `evaluation/live_calls/` contains only `README.md`; count of real call exports is **0**. |
| **K2** | Carrier Field Matrix Results | **NOT DONE** | `evaluation/carrier_results.json` shows all tests `NOT_RUN` with 0 attempts. |
| **K3** | Pilot Trial Results | **NOT DONE** | `evaluation/pilot_results.json` shows status `NOT_RUN` with 0 participants. |
| **K4** | Pitch Deck & Demo Video | **NOT DONE** | 0 demo video links, 0 pitch deck links, and 0 live dashboard links exist in the repository. |
| **L1** | Previously Flagged Claims | **FAILED** | "100% detection" (`application_draft.md:38`), "$0.09$ ms" (`application_draft.md:43`), Groq/Gemini latencies (`handoff_lanes_a_b.md:72`), and "three personas" (`README.md:14`) remain present. "Tamil" is removed. |
| **L2** | Numeric Performance Claims | **PARTIAL** | README disclaims dev metrics as synthetic, but `application_draft.md` continues to assert unhedged 100% recall. |
| **L3** | Legacy Name References | **VERIFIED** | 0 legacy names in filenames; 3 historical references in docs (`docs/lane_c_integration.md:45`, `sprint-plan.md:114,312`). |
| **L4** | Repo & Render Naming | **VERIFIED** | GitHub repo is public (`RohitBharadwaj-rvu/rakshak-ai`); Render service is `guardianline-backend` (`rakshak-ai-3ckj.onrender.com`). |
| **L5** | Git Secret Scan | **VERIFIED** | `.env` is properly ignored; full git history scan revealed legacy token in `render.yaml` at commit `c4417cc447` (later scrubbed in `e585789ff1`). |

---

## 3. EVIDENCE DETAILS BY SECTION

### Section A: Git State
- **A1:** Ref list inspection confirms branches:
  - `SprintA`: `8e0659a` (2026-10-18 20:59:41 +0530)
  - `lane-b`: `37edec5` (2026-10-18 21:05:17 +0530)
  - `lane-c`: `b490fcb` (2026-10-17 14:53:26 +0530)
  - `lane-d`: `8006301` (2026-10-18 16:26:15 +0530)
  - `main`: `f188520` (2026-10-16 19:52:06 +0530)
  - `voice` (local): `349c832` (2026-10-18 00:04:18 +0530) — **15 local-only commits ahead of origin**
  - `origin/voice`: `8db909f` (2026-10-17 14:54:10 +0530)
- **A2:** Merge-base ancestor checks against `origin/voice`:
  - `lane-b`: `git merge-base --is-ancestor lane-b origin/voice` -> **False** (Exit code 1)
  - `lane-c`: `git merge-base --is-ancestor lane-c origin/voice` -> **True** (Exit code 0)
  - `lane-d`: `git merge-base --is-ancestor lane-d origin/voice` -> **False** (Exit code 1)
  - `SprintA`: `git merge-base --is-ancestor SprintA origin/voice` -> **False** (Exit code 1)
  - `integration`, `feat/mule-extraction`, `feat/evidence-packets`: **Do not exist** locally or remotely.
- **A3:** `git rev-parse voice` (`349c832...`) != `git rev-parse origin/voice` (`8db909f...`). `audit-temp-merge` does not exist. `git worktree list` showed only the root checkout.
- **A4:** `git log --since="2026-10-18T00:00:00+05:30" origin/voice` returned 0 lines.
- **A5:** `git grep -n -E "(<<<<<<<|>>>>>>>)" origin/voice` exited with code 1 (no conflict markers).

### Section B: Automated Tests
- **B1:** Executed in temporary detached worktree at `origin/voice` root:
  - Command: `python -m pytest`
  - Output: `169 passed, 1 warning in 11.47s`
  - Warning: Pydantic `BaseModel.copy` deprecation in `tests/integration/test_alerts.py:187`.
- **B2:** Test mock auditing:
  - Bolna: Mocked in `scripts/mock_bolna.py` loading static JSON fixtures.
  - Twilio: `unittest.mock.MagicMock()` injected into `FamilyAlertDispatcher` (`test_alerts.py:13`).
  - LLMs: `monkeypatch.setattr("app.voice.classifier._call_groq", ...)` (`test_classifier.py:27`).
  - Telephony Audio: 5 sine-wave WAV files checking 8kHz mono PCM formatting (`test_voice_smoke.py:18`).
  - Total tests touching live external networks: **0**.

### Section C: Live Backend (Render)
- **C1:** `render.yaml` does not exist on `origin/voice`. It exists on `origin/lane-b`:
  ```yaml
  services:
    - type: web
      name: guardianline-backend
      runtime: python
      plan: free
      buildCommand: pip install -r requirements.txt
      startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
      healthCheckPath: /health
      envVars:
        - key: BOLNA_WEBHOOK_SECRET
          sync: false
        - key: GUARDIANLINE_API_TOKEN
          sync: false
        - key: GUARDIANLINE_DB_PATH
          value: /tmp/guardianline_calls.db
  ```
- **C2:** Measured via Python `urllib.request`:
  - Request 1: HTTP 200, Latency: 0.34s, Body: `{"status":"ok","service":"guardianline-backend"}`
  - Request 2: HTTP 200, Latency: 0.19s, Body: `{"status":"ok","service":"guardianline-backend"}`
  - No commit hash or version is exposed. `origin/voice` HEAD lacks `app/main.py`; the deployed service runs `lane-b`.
- **C3:** `app/voice/store.py:78` defines optional Postgres replication via `DATABASE_URL`. However, `render.yaml` provides no database and sets `GUARDIANLINE_DB_PATH: /tmp/guardianline_calls.db`. Data is stored in ephemeral `/tmp` storage and lost on restart.
- **C4:** Request to `https://rakshak-ai-3ckj.onrender.com/api/calls` returned `HTTP 401: {"detail":"Missing or invalid API token"}`. Token is absent from `.env`.
- **C5:** Searched repository for cron pingers, GitHub keep-alive actions, and uptime monitors: 0 results found. Free dyno enters deep sleep after 15 minutes.

### Section D: Bolna Agent Configuration
- **D1:** Verified via `.env` inspection: `BOLNA_API_KEY: exists=False`.
- **D2 & D3:** Marked **CANNOT VERIFY** due to missing API key.
- **D4: Manual Bolna Dashboard Checklist for Human Auditor:**
  1. **Agent Tool URLs:** Navigate to *Agents* $\rightarrow$ *Tools*. Confirm `classify_caller`, `switch_to_honeypot`, and `log_intel` point to `https://rakshak-ai-3ckj.onrender.com/tools/*`.
  2. **Webhook URL:** Navigate to *Settings* $\rightarrow$ *Webhooks*. Confirm webhook is set to `https://rakshak-ai-3ckj.onrender.com/webhook`.
  3. **Prompt Source:** Compare the live system prompt against `SprintA:prompts/rakshak-v1-two-mode.md`. Verify whether fallback persona is Ramesh Sharma (Lucknow) or Ramesh Kumar (Jaipur).
  4. **Synthesizer Settings:** Confirm TTS provider and voice. If set to `Simran`, verify whether an elderly male voice or female persona change has been configured.
  5. **Inbound Phone Mapping:** Check *Phone Numbers* and confirm whether a virtual Indian DID is mapped as the default inbound agent for this agent ID.
- **D5:** `SprintA:bolna/rakshak-v0.json` has `agent_name: rakshak-v0`, webhook `https://rakshak-ai-3ckj.onrender.com/webhook`, OpenAI `gpt-4.1`, Sarvam `saaras:v3` STT, Sarvam `bulbul:v3` voice `Simran`, and legacy tools.

### Section E: Classifier Audit
- **E1:** Git log comparison `119e6c6..origin/voice` vs `119e6c6..lane-d`:
  - `lane-d` has commits `f48301c` ("enforce general invariant safety rule forbidding genuine verdicts on value demands") and `31b39ef`.
  - `origin/voice` stopped at `ae215f8` and **lacks both commits**.
- **E2:** `origin/voice:app/voice/classifier.py:304-350` contains naive contextual whitelists:
  ```python
  is_delivery_context = bool(re.search(r"delivery|parcel|courier|gate", text_lower))
  is_delivery_otp = bool(re.search(r"delivery\s*(otp|code)", text_lower))
  ...
  is_hospital_context = bool(re.search(r"hospital|admission\s*desk|prescription", text_lower))
  ...
  is_relative_call = bool(re.search(r"nephew|uncle.*amit|battery\s*died", text_lower))
  ```
- **E3:** Live execution of `scripts/probe_whitelist_holes.py` on `origin/voice`:
  ```
  [1/6] probe_01_fake_courier_delivery_otp        -> Verdict=GENUINE (Confidence=0.08) [CRITICAL VULNERABILITY: FALSE NEGATIVE]
  [2/6] probe_02_fake_police_tenant_fine          -> Verdict=GENUINE (Confidence=0.08) [CRITICAL VULNERABILITY: FALSE NEGATIVE]
  [3/6] probe_03_fake_hospital_icu_advance        -> Verdict=SCAM    (Confidence=0.88) [BLOCKED AS SCAM]
  [4/6] probe_04_fake_relative_highway_trouble    -> Verdict=GENUINE (Confidence=0.08) [CRITICAL VULNERABILITY: FALSE NEGATIVE]
  [5/6] probe_05_fake_bank_advisory_remote_access -> Verdict=GENUINE (Confidence=0.08) [CRITICAL VULNERABILITY: FALSE NEGATIVE]
  [6/6] probe_06_fake_challan_traffic_authority   -> Verdict=SCAM    (Confidence=0.88) [BLOCKED AS SCAM]
  AUDIT SUMMARY: 4/6 probe scenarios successfully exploited whitelist loopholes!
  ```
- **E4:** `evaluation/held_out_scenarios.json` does not exist on any git branch. `python scripts/run_held_out_eval.py` exited with code 1 (`[ERROR] Dataset not found`).
- **E5:** Real Stage 2 API calls executed:
  - Groq `GET /openai/v1/models` succeeded (11 models active). Configured model `llama-3.3-70b-versatile` is **absent** from Groq (`False`).
  - Groq classify request returned: `HTTPError 404: {"error":{"message":"The model llama-3.3-70b-versatile does not exist...","code":"model_not_found"}}`.
  - Gemini classify request to `gemini-flash-latest` failed: `The read operation timed out` (>10s).
- **E6:** `stage2_ran` column exists in `origin/lane-b:app/voice/store.py:176`, but is completely absent from `origin/voice`.

### Sections F & G: Addition 1 (Mule Extraction) & Addition 2 (Evidence Packets)
- **F1 – F6:** `git log --all -S "value_raw"`, `-S "elicitation"`, and `-S "actionable_identifiers"` returned 0 commits. Mule rotation extraction is **NOT STARTED**.
- **G1 – G8:** `git log --all -S "Chakshu"`, `-S "sancharsaathi"`, and `-S "evidence/verify"` returned 0 commits. Evidence packets are **NOT STARTED**. Existing code retains the un-gated Sprint 3 1930 incident report text template (`app/voice/report.py`).

### Section H: Voice and Persona
- **H1:** Synthesizer in `SprintA:bolna/rakshak-v0.json:35` is Sarvam `bulbul:v3` voice `Simran` (Female). Honeypot prompt in `prompts/rakshak-v1-two-mode.md:36` is `Ramesh Sharma` (72-year-old grandfather). Result: **Blatant gender and age mismatch**.
- **H2:** 0 transfer configurations or elderly male voices exist in Bolna configs.
- **H3:** Parent/persona name is hardcoded in `prompts/rakshak-v1-two-mode.md:36` (`Ramesh Sharma (fallback): 72, retired post office clerk, Lucknow...`). No session variable (`%(parent_name)s`) is supported.

### Section I: Android (Lane C)
- **I1:** `android/app/src/main/java/ai/guardianline/screening/CallScreeningLogic.kt:60` whitelists the gateway number. However, `android/app/build.gradle.kts:20` defaults `GUARDIAN_GATEWAY_NUMBER` to `""`.
- **I2:** Executed Android unit tests inside temporary worktree:
  - Command: `.\gradlew.bat testDebugUnitTest`
  - Output: `BUILD SUCCESSFUL in 43s`
  - Results XML: `TEST-ai.guardianline.screening.CallScreeningLogicTest.xml` — **16 tests, 0 failures, 0 skipped** (0.338s).
- **I3:** `docs/tests/android.md` outlines an 8-step field protocol and 24-hour soak test, but zero logs or test records exist on disk.

### Section J: Alerts
- **J1:** `app/notify/alerts.py:704` defaults to WhatsApp (`ALERT_CHANNEL: whatsapp`) with Twilio sandbox number (`+14155238886`). Indian TRAI DLT registration for SMS is unconfigured (`docs/lane_c_integration.md`).
- **J2:** Regex search for real Twilio SIDs (`SM[0-9a-fA-F]{32}`) returned 0 results in git history. Only synthetic mock SIDs exist.

### Section K: Real-World Evidence
- **K1:** `evaluation/live_calls/` contains only `README.md`. Real call export count: **0**.
- **K2:** `evaluation/carrier_results.json:21` shows Jio, Airtel, and Vi tests as `"status": "NOT_RUN", "attempts": []`.
- **K3:** `evaluation/pilot_results.json:11` shows `"status": "NOT_RUN", "participants": []`. Participant count: **0**.
- **K4:** 0 demo video links, 0 pitch deck links, and 0 live dashboard links exist across `submission/` and `README.md`.

### Section L: Claims & Hygiene
- **L1 & L2:** Flagged claims status on `origin/voice`:
  - `"100%"` detection: **STILL PRESENT** in `submission/application_draft.md:38` (`100.0% (20/20 scam scenarios)`).
  - `"$0.09$ ms"` / `"<1.4s"` latency: **STILL PRESENT** in `submission/application_draft.md:43`.
  - `"~480 ms"` Groq / `"~680 ms"` Gemini: **STILL PRESENT** in `docs/handoff_lanes_a_b.md:72-73` and `scripts/profile_stage2_latency.py:225`.
  - `"three personas"`: **STILL PRESENT** in `README.md:14` and `submission/application_draft.md:14`.
  - `"Tamil"`: **REMOVED** (0 occurrences).
  - `"AMD Slingshot"`: Removed from `README.md`, but **STILL PRESENT** in `guardianline-sprint-plan.md:114,312`.
- **L3:** Legacy branding occurrences in file contents:
  - `docs/lane_c_integration.md:45`: `"Lane A's agent config and prompt say Rakshak."`
  - `guardianline-sprint-plan.md:114,312`: `"Remove the AMD Slingshot references from the README."`
- **L4:** Public GitHub repository: `https://github.com/RohitBharadwaj-rvu/rakshak-ai`. Live Render service: `https://rakshak-ai-3ckj.onrender.com`.
- **L5:** `.env` is properly ignored by git. Git history scan detected a hardcoded token added in `render.yaml` at commit `c4417cc447` and scrubbed at `e585789ff1`.

---

## 4. WHAT IS LEFT, BY LANE

### Shared / Integration
1. **Merge Lane Branches into Voice (A2, A3):** Currently, `lane-b`, `lane-d`, and `SprintA` are unmerged on `origin/voice`. Local `voice` has 15 unpushed commits. A clean integration must combine backend (`lane-b`), classifier fixes (`lane-d`), and Bolna configurations (`SprintA`).
2. **Setup Persistent Backend Storage (C3):** Provision a managed PostgreSQL instance or persistent disk on Render and set `DATABASE_URL` so `CallRecords` survive dyno restarts.
3. **Configure Keep-Alive / Uptime Monitor (C5):** Configure a free uptime monitor (e.g. UptimeRobot or cron job) hitting `/health` every 10 minutes to prevent cold-start delays.

### Lane A (Voice Agent & Bolna)
1. **Fix Voice / Persona Mismatch (H1):** Change Bolna TTS synthesizer voice from `Simran` to an elderly male Hindi voice (e.g. Sarvam `bulbul:v3` male voice), or switch the persona to a grandmother (`Sunita Verma`).
2. **Sync Bolna Agent Prompt (D2, D5):** Export and deploy the finalized prompt from `SprintA:prompts/rakshak-v1-two-mode.md` to the active Bolna agent.
3. **Configure Inbound Telephony DID (I1, D2):** Attach an active phone number to the Bolna agent and set `BOLNA_GATEWAY_NUMBER` in Android build configuration.

### Lane B (Backend & Tools)
1. **Fix Stage 2 LLM Model IDs (E5):** Update Groq model from defunct `llama-3.3-70b-versatile` to `openai/gpt-oss-20b` (or pass via `GROQ_MODEL`), and adjust Gemini timeout and model endpoint.
2. **Backport `stage2_ran` Column to Voice (E6):** Ensure `CallRecord` schema on `voice` includes `stage2_ran` and `classifier_method`.
3. **Provide Valid API Tokens in `.env` (C4):** Populate `GUARDIANLINE_API_TOKEN` and `GUARDIAN_DASHBOARD_TOKEN` in `.env` to enable programmatic access to `/api/calls`.

### Lane C (Android & Alerts)
1. **Conduct Physical Handset Field Tests (I3, K2):** Execute the 8-step field script from `docs/tests/android.md` on physical SIMs (Jio, Airtel, Vi) and record real results in `evaluation/carrier_results.json`.
2. **Configure Twilio WhatsApp / SMS Credentials (J1, J2):** Add valid `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` to `.env` and verify delivery of at least one real test alert.

### Lane D (Evaluation & Classifier)
1. **Merge Invariant Safety Rule into Voice (E1, E2):** Cherry-pick or merge commit `f48301c` to close the 4/6 whitelist loopholes on `voice`.
2. **Create Blind Held-Out Dataset (E4):** Author `evaluation/held_out_scenarios.json` and verify `python scripts/run_held_out_eval.py` produces a valid scorecard.
3. **Clean Up Unbacked Claims (L1, L2):** Remove the unhedged `100.0%` detection claim and `$0.09$ ms` latency claim from `submission/application_draft.md`.

---

## 5. TOP 5 BLOCKERS FOR A RECORDED REAL-CALL DEMO

1. **Female Voice vs Male Grandfather Persona Mismatch (Finding H1)**
   - *Problem:* Sarvam TTS voice `Simran` is an audible female voice, but the persona introduces himself as 72-year-old grandfather Ramesh.
   - *Next Action:* Update `SprintA:bolna/rakshak-v0.json` synthesizer to an elderly male voice or change the persona to grandmother Sunita, and update the Bolna canvas.
2. **Stage 2 LLM Classifier Broken (HTTP 404 / Timeout) (Finding E5)**
   - *Problem:* Groq requests non-existent model `llama-3.3-70b-versatile` (HTTP 404) and Gemini times out, forcing fallback to naive heuristics that miss 4/6 scam types.
   - *Next Action:* Update `app/voice/classifier.py` to use `openai/gpt-oss-20b` for Groq and fix the Gemini endpoint.
3. **Loophole Vulnerabilities on `voice` Branch (Finding E1, E3)**
   - *Problem:* The general invariant rule forbidding genuine verdicts on value demands exists only on `lane-d` and is missing from `origin/voice`.
   - *Next Action:* Merge `lane-d` commit `f48301c` into `voice`.
4. **Ephemeral Database on Free-Tier Render (Finding C3)**
   - *Problem:* Call records and extracted scammer details are stored in `/tmp/guardianline_calls.db` and destroyed every time Render dynos spin down.
   - *Next Action:* Attach a free managed Postgres database on Render and set `DATABASE_URL`.
5. **No Live Inbound Number or Carrier Forwarding Evidence (Findings I1, K2)**
   - *Problem:* Carrier matrix is completely un-run (`NOT_RUN`), and Android build configuration lacks an active gateway number.
   - *Next Action:* Run manual carrier forwarding tests (`**67*`) with a physical SIM and populate `evaluation/carrier_results.json`.

---

## 6. CLAIMS AT RISK

The following statements in project documentation are unbacked or contradicted by current code:

1. **"Scam Detection Rate (Recall): 100.0%" (`submission/application_draft.md:38`)**
   - *Risk:* Contradicted by `scripts/probe_whitelist_holes.py`, which shows 4 out of 6 scam attack vectors are labeled `GENUINE` by the heuristics running on `origin/voice`.
2. **"Classification Processing Latency: 0.09 ms (local) / <1.4s (cloud)" (`submission/application_draft.md:43`)**
   - *Risk:* 0.09 ms is an in-memory regex match time, not a telephony classifier latency. Real cloud Stage 2 LLM inference currently fails entirely (HTTP 404 / timeout).
3. **"Stage 2 (Groq Llama 3.3 70B): ~480 ms" (`docs/handoff_lanes_a_b.md:72`)**
   - *Risk:* Model `llama-3.3-70b-versatile` does not exist on Groq's active API endpoints (returns HTTP 404).
4. **"Three personas (Ramesh, Sunita, Prof. Iyer)" (`README.md:14`)**
   - *Risk:* Only Ramesh is wired in prompt and tool defaults; Sunita and Prof. Iyer are never dynamically selected.
5. **"Automated Unit & Scenario Tests: 123 passed" (`submission/application_draft.md:44`)**
   - *Risk:* Stale count. The current suite on `origin/voice` contains 169 tests.

---

## 7. CANNOT VERIFY LIST

The following items could not be verified in this automated audit and require human inspection:

1. **Live Bolna Agent Settings (D2):**
   - *Required Action:* Human with Bolna console access must log in, inspect Agent ID `BOLNA_AGENT_ID`, and check tools, webhook host, and synthesizer voice against checklist D4.
2. **Live Bolna Call Executions & Costs (D3):**
   - *Required Action:* Human must check the Bolna execution log to verify whether live test calls were logged and what costs/minutes were consumed.
3. **Live CallRecords on Render (C4):**
   - *Required Action:* Developer must provide the active `GUARDIANLINE_API_TOKEN` in `.env` to enable read-only auditing of `https://rakshak-ai-3ckj.onrender.com/api/calls`.
4. **Physical Carrier Forwarding Reliability (K2):**
   - *Required Action:* Team member with an Indian SIM card must dial `**67*<gateway_number>#`, decline a test call, and verify that the call forwards to the Bolna agent.
