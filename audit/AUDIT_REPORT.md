# GuardianLine Independent Repository Audit Report

**Date of Audit:** October 18, 2026 (00:15 IST)  
**Auditor Role:** Independent Auditor (Inspection & Verification Only)  
**Repository:** `RohitBharadwaj-rvu/rakshak-ai`  
**Working Copy Head:** Branch `lane-d` at commit `1109c3b`  
**Integration Head:** Branch `voice` at commit `8db909f`  

---

## 1. Summary Table

| ID | Item | Status | One-Line Finding |
|---|---|---|---|
| **A1** | Branch inventory | **VERIFIED** | 6 local branches tracked to origin (`main`, `voice`, `lane-b`, `lane-c`, `lane-d`, `SprintA`). |
| **A2** | lane-b vs voice divergency | **VERIFIED** | `voice` is 11 commits ahead, 14 commits behind `lane-b`; 14 `lane-b`-only commits exist. |
| **A3** | Temp worktree lane-b merge & test | **PARTIAL** | Merge hits 6 conflict files; once resolved, all 416 tests pass with 0 failures. |
| **A4** | Full test suite on voice as-is | **VERIFIED** | Exactly 416 passed, 0 failed, 1 warning (Pydantic model_copy deprecation); mock-only for Twilio/Bolna. |
| **B1** | Deployment configurations | **VERIFIED** | Free tier on Render (`render.yaml`), Dockerfile, and Procfile defined only on `lane-b`. |
| **B2** | Production database persistence | **FAILED** | Uses ephemeral `/tmp/guardianline_calls.db`; data is wiped on restart without external PostgreSQL `DATABASE_URL`. |
| **B3** | Keep-alive / cold-start mitigation | **NOT DONE** | No keep-alive pingers, cron jobs, or paid tier configured to prevent free-tier sleep. |
| **B4** | Deployed URL verification | **VERIFIED** | `https://rakshak-ai-3ckj.onrender.com/health` returns HTTP 200 OK (warm: 0.72s, cold start: 12.78s). |
| **C1** | Bolna agent tool & webhook hosts | **VERIFIED** | Points to `https://rakshak-ai-3ckj.onrender.com` (reachable, verified live). |
| **C2** | Voice stack components & gender | **VERIFIED** | STT: Sarvam `saaras:v3` (hi); LLM: OpenAI `gpt-4.1`; TTS: Sarvam `bulbul:v2` voice `Simran` (Female). |
| **C3** | Tamil language support | **NOT DONE** | Tamil is absent from config, prompts, and scenarios; intentionally cut in commit `36500b7`. |
| **C4** | Dynamic TTS voice switching mid-call | **CANNOT VERIFY** | Config has single static synthesizer (`Simran`); dynamic voice switching lacks Bolna doc proof. |
| **C5** | Hangup prompt behavior | **VERIFIED** | `prompts/rakshak-v1-hangup.md` explicitly blocks hangup while scammer is talking or giving intel. |
| **D1** | Receptionist to honeypot handoff | **PARTIAL** | Receptionist calls `switch_to_honeypot`; only `Ramesh` is wired by default; `Sunita`/`Prof. Iyer` are never selected. |
| **D2** | TTS voice vs persona consistency | **FAILED** | **MISMATCH**: Female voice (`Simran`) speaks as 72-year-old grandfather `Ramesh Kumar`. |
| **D3** | Dynamic household personalization | **FAILED** | Parent name is not dynamic; fallback persona is hardcoded in the Bolna system prompt. |
| **E1** | Android CallScreeningService logic | **VERIFIED** | `CallScreeningLogic.kt` correctly sets `setDisallowCall(true)`, `setRejectCall(true)`, `setSkipCallLog(false)`. |
| **E2** | Bolna gateway number whitelisting | **FAILED** | `BOLNA_GATEWAY_NUMBER` defaults to empty string in `build.gradle.kts`, causing a call loop on genuine transfer. |
| **E3** | Emergency helpline whitelisting | **VERIFIED** | Numbers `112`, `100`, `108`, `1930`, `1091` are hardcoded in `PhoneNumberNormalizer.kt`. |
| **E4** | Android Gradle build & unit tests | **CANNOT VERIFY** | Gradle 8.5 fails locally with missing Android SDK (`ANDROID_HOME` / `sdk.dir` not configured). |
| **E5** | Physical phone execution records | **NOT DONE** | Zero physical run logs exist; `docs/carrier_matrix.md` is an unpopulated template marked `NOT_RUN`. |
| **F1** | Family alert channels & provider | **VERIFIED** | Implemented for WhatsApp and SMS via Twilio in `app/notify/alerts.py`. |
| **F2** | Indian DLT registration for SMS | **NOT DONE** | No DLT Entity/Header/Template ID configured; TRAI firewalls will block domestic Indian SMS. |
| **F3** | WhatsApp sandbox & opt-in | **PARTIAL** | Configured for Twilio sandbox; documented in `docs/lane_c_integration.md`, but recipients must pre-join. |
| **F4** | Real message delivery proof | **CANNOT VERIFY** | No logs, screenshots, or message SIDs of live delivery to physical handsets exist. |
| **G1** | Classifier file freeze integrity | **PARTIAL** | Freeze broken; `app/voice/classifier.py` was modified in commits `7c5d5ee` and `ae215f8`. |
| **G2** | Whitelist loophole probe suite | **FAILED** | 4 out of 6 trojan scams bypass heuristics and are classified as `GENUINE` (`scripts/probe_whitelist_holes.py`). |
| **G3** | "Unsure/Verify" protocol wiring | **PARTIAL** | Verdict is strictly `"unsure"`, `"scam"`, or `"genuine"`; no `"verify"` verdict exists in code enum. |
| **G4** | Stage 2 live LLM latency & status | **FAILED** | Groq returns HTTP 404 (model not found); Gemini returns HTTP 429; all runs silently drop to local regex. |
| **G5** | Stage 2 latency profile authenticity | **VERIFIED** | `evaluation/stage2_latency_profile.json` confirms Groq and Gemini failed; only local regex measured. |
| **G6** | Handoff document latency claims | **FAILED** | `docs/handoff_lanes_a_b.md` quotes ~480ms Groq and ~680ms Gemini latencies that are not in the profile file. |
| **H1** | Held-out evaluation set existence | **NOT DONE** | `evaluation/held_out_scenarios.json` does not exist; only authoring brief exists. |
| **H2** | Held-out evaluation execution | **NOT DONE** | `scripts/run_held_out_eval.py` cannot execute because scenario file is missing. |
| **H3** | Performance claims backing & audit | **PARTIAL** | Accuracy claims are correctly labeled synthetic dev set, but cloud latency claims (<1.4s) are unbacked. |
| **H4** | Real Bolna phone call records | **NOT DONE** | Zero audio recordings, persistent DB exports, or live Bolna transcripts exist in the repository. |
| **I1** | Project naming hygiene in files | **PARTIAL** | "Rakshak" remains in `SprintA` bolna config, prompts, and `docs/handoff_lanes_a_b.md:131`. |
| **I2** | Git commit message naming hygiene | **PARTIAL** | Commits `09d1f60`, `67d0e12`, `6738acf`, `5a3a084` explicitly reference "Rakshak". |
| **J1** | Git environment secrets tracking | **VERIFIED** | `.env` and `.env.local` are gitignored; only `.env.example` is tracked. |
| **J2** | Git history secret scan | **VERIFIED** | Scanned full commit history (`git log -p`) for API key patterns; 0 live leaked keys found. |
| **K1** | Carrier forwarding matrix evidence | **NOT DONE** | `docs/carrier_matrix.md` contains 0 physical test runs; all table cells are `NOT_RUN (0/3)`. |
| **K2** | Elderly pilot trials & consent | **NOT DONE** | 0 completed consent records; `evaluation/pilot_results.json` has `participants: []`. |
| **L1** | README project definition | **VERIFIED** | Lines 1–16 of `README.md` provide a clear, accurate, and professional 3-line overview. |
| **L2** | Public pitch deck & demo video | **NOT DONE** | No demo video link, pitch deck link, or frontend app URL exists in repo or submission docs. |
| **L3** | GitHub repository visibility | **VERIFIED** | Repository `RohitBharadwaj-rvu/rakshak-ai` is currently **PUBLIC** on GitHub. |
| **L4** | Aggregated threat intel dashboard | **NOT DONE** | Dashboard only displays per-call logs; no cross-call aggregated scam intelligence view exists. |

---

## 2. Detailed Checklist Findings

### A. Branches & Integration

#### A1. Branch Inventory
- **Command:** `git for-each-ref --format="%(refname:short) | %(objectname:short) | %(committerdate:iso8601) | %(subject)" refs/heads/ refs/remotes/`
- **Output:**
  ```text
  SprintA        | 631e9d6 | 2026-10-17 19:44:35 +0530 | Ask for missing UPI parts before logging intel
  lane-b         | 6386ebb | 2026-10-17 19:34:03 +0530 | fix(voice): prevent cross-turn glued repeated digits and extract split-turn Devanagari UPIs
  lane-c         | b490fcb | 2026-10-17 14:53:26 +0530 | Lane C: wire alerts and dashboard into lane B, fix audit v2 leftovers
  lane-d         | 1109c3b | 2026-10-17 14:51:02 +0530 | Merge origin/voice into lane-d: integrate Lane C Android screening, family alerts, and dashboard
  main           | f188520 | 2026-10-16 19:52:06 +0530 | Add sprint plan, definition of done and test suite designs
  voice          | 8db909f | 2026-10-17 14:54:10 +0530 | Merge lane-c into voice: lane C wired into lane B, audit v2 fixes
  origin/SprintA | 631e9d6 | 2026-10-17 19:44:35 +0530 | Ask for missing UPI parts before logging intel
  origin/lane-b  | 6386ebb | 2026-10-17 19:34:03 +0530 | fix(voice): prevent cross-turn glued repeated digits and extract split-turn Devanagari UPIs
  origin/lane-c  | b490fcb | 2026-10-17 14:53:26 +0530 | Lane C: wire alerts and dashboard into lane B, fix audit v2 leftovers
  origin/lane-d  | 1109c3b | 2026-10-17 14:51:02 +0530 | Merge origin/voice into lane-d: integrate Lane C Android screening, family alerts, and dashboard
  origin/main    | f188520 | 2026-10-16 19:52:06 +0530 | Add sprint plan, definition of done and test suite designs
  origin/voice   | 8db909f | 2026-10-17 14:54:10 +0530 | Merge lane-c into voice: lane C wired into lane B, audit v2 fixes
  ```
- **Status:** **VERIFIED**

#### A2. lane-b vs voice Divergence
- **Command:** `git rev-list --left-right --count voice...lane-b`
- **Output:** `11  14`
- **lane-b-only Commits:**
  - `6386ebb` fix(voice): prevent cross-turn glued repeated digits and extract split-turn Devanagari UPIs
  - `35d69f7` feat(voice): support execution_id on tools and 3-step mid-call to webhook join
  - `e585789` sec(webhook): enforce BOLNA_WEBHOOK_SECRET Bearer auth on /webhook and remove hardcoded token from render.yaml
  - `3e76110` feat(store): add optional DATABASE_URL Postgres mirror + JSON backup/restore across Render redeploys
  - `51ff88b` chore(lane-b): respond 200 OK on GET/HEAD / as well as /health for Render probes
  - `3ee9bf4` chore(lane-b): add requirements.txt for Render/Docker build
  - `bbd6b9f` chore(lane-b): add Dockerfile for Render deployment
  - `c4417cc` chore(lane-b): add Render/Railway cloud deployment configs (render.yaml, Procfile)
  - `73610db` fix(lane-b): support native Bolna webhook payload and blank BOLNA_WEBHOOK_SECRET in .env.example
  - `567450c` feat(lane-b): complete Sprint 4 (STT extraction-miss analyzer, online SQLite backup, T-HOST smoke suite)
  - `727a0a3` feat(lane-b): align Bolna v1 prompt parameter names with contracts/
  - `e1bbff2` feat(lane-b): complete Sprint 3 (T-RPT 1930 report generator, T-POST post-call reflection, CSV export)
  - `417d2a0` feat(lane-b): complete Sprint 2 (Normalizer v2, T-CLEAN grounded cleanup, T-API CallRecord endpoints)
  - `0a28aad` Lane B (Sprint 0 & 1): Add contracts, interfaces.md, normalizer, extractor, tools, and SQLite webhook store
- **Status:** **VERIFIED**

#### A3. Worktree Merge Test of lane-b into voice
- **Command:** `git worktree add $tempWorktree voice; git merge --no-commit --no-ff lane-b`
- **Conflict Files (6 files):**
  1. `.env.example` (add/add)
  2. `.github/workflows/ci.yml` (content)
  3. `.gitignore` (content)
  4. `app/api/classifier_router.py` (content)
  5. `pytest.ini` (add/add)
  6. `requirements.txt` (add/add)
- **Post-Merge Pytest Execution:** Resolving these 6 files yielded **416 passed, 1 warning, 0 failures** in 38.87s.
- **Status:** **PARTIAL** (Merge cleanly passes tests once conflict markers are resolved, but unmerged divergency currently blocks automatic integration).

#### A4. Full Test Suite on Current voice Branch
- **Command:** `python -m pytest tests -v` on clean `voice` worktree
- **Output:** `416 passed, 1 warning in 33.94s` (0 failed, 0 skipped, 0 xfailed).
- **Mock Evaluation:** Network calls to external APIs (Twilio SMS/WhatsApp, Bolna webhooks) are mocked via unit test fixtures (`mock_twilio_client`, `mock_bolna.py`).
- **Status:** **VERIFIED**

---

### B. Deployment (T-HOST)

#### B1. Configuration Files Inspection
- **Files:** `lane-b:render.yaml`, `lane-b:Dockerfile`, `lane-b:Procfile`
- **Evidence:**
  - `plan: free` in `render.yaml` line 5.
  - `startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT` in `render.yaml` line 7.
  - `healthCheckPath: /health` in `render.yaml` line 8.
  - Required Environment Variables: `BOLNA_WEBHOOK_SECRET`, `GUARDIANLINE_API_TOKEN`, `GUARDIANLINE_DB_PATH`.
- **Status:** **VERIFIED**

#### B2. Database Persistence
- **Evidence:**
  - In `render.yaml`: `GUARDIANLINE_DB_PATH: /tmp/guardianline_calls.db`.
  - In `app/voice/store.py` lines 42–46:
    ```python
    def _get_pg_conn():
        db_url = os.getenv("DATABASE_URL", "").strip()
        if not db_url or _CUSTOM_DB_PATH is not None:
            return None
    ```
- **Finding:** Render free instances do not attach persistent disks. Because `DATABASE_URL` is not provisioned or configured in `render.yaml`, all CallRecords written to `/tmp/guardianline_calls.db` are **permanently wiped on every container restart, redeploy, or idle sleep**.
- **Status:** **FAILED**

#### B3. Keep-Alive / Cold-Start Mitigation
- **Evidence:** Search for `keep-alive`, cron pings, or background pingers yielded 0 results.
- **Finding:** No keep-alive pinger or uptime monitor is configured. Free tier Render instances enter deep sleep after 15 minutes of inactivity.
- **Status:** **NOT DONE**

#### B4. Deployed URL Verification
- **Host:** `https://rakshak-ai-3ckj.onrender.com/health` (found in `bolna/rakshak-v0.json`)
- **Measured Response:**
  - Cold Start Response Time: **12.78 seconds**
  - Warm Response Time: **0.72 seconds**
  - Status Code: **HTTP 200 OK**
  - Body: `{"status":"ok","service":"guardianline-backend"}`
- **Status:** **VERIFIED**

---

### C. Bolna Agent Configuration

#### C1. Host Reachability
- **Tool URLs in `bolna/rakshak-v0.json`:**
  - Webhook: `https://rakshak-ai-3ckj.onrender.com/webhook`
  - `classify_caller`: `https://rakshak-ai-3ckj.onrender.com/tools/classify_caller`
  - `switch_to_honeypot`: `https://rakshak-ai-3ckj.onrender.com/tools/switch_to_honeypot`
  - `log_intel`: `https://rakshak-ai-3ckj.onrender.com/tools/log_intel`
- **Finding:** The URLs point to a live external domain on Render that responded with HTTP 200. Bolna can reach this host.
- **Status:** **VERIFIED**

#### C2. Voice Stack Configuration
- **Evidence from `SprintA:bolna/rakshak-v0.json`:**
  - STT: `"provider": "sarvam"`, `"model": "saaras:v3"`, `"language": "hi"`
  - LLM: `"provider": "openai"`, `"model": "gpt-4.1"`, `"temperature": 0.3`
  - TTS: `"provider": "sarvam"`, `"model": "bulbul:v2"`, `"voice": "Simran"` (Female Indian voice)
- **Status:** **VERIFIED**

#### C3. Tamil Language Support
- **Evidence:** `git grep -i "tamil"` returned 0 occurrences across all active prompts, scenarios, and agent configs.
- **Finding:** Tamil was removed in commits `36500b7` and `c9df95a` to focus on Hindi, English, and Hinglish. The original submission claim of "starting with Tamil and Hindi" is unfulfilled.
- **Status:** **NOT DONE**

#### C4. Mid-Call TTS Voice Switching
- **Evidence:** Bolna config contains a single static synthesizer task (`Simran`). `"multilingual_config"` and `"switch_handoff_messages"` are `null`.
- **Finding:** Without access to Bolna's internal API documentation regarding dynamic voice reconfiguration on live calls, mid-call voice switching cannot be verified.
- **Status:** **CANNOT VERIFY**

#### C5. Hangup Prompt Rules
- **Evidence:** `SprintA:prompts/rakshak-v1-hangup.md` lines 15–21:
  > "The call is NOT complete if:  
  > - The assistant is in honeypot mode and the caller has not said goodbye. The assistant stalling, refusing, or saying 'ruk jao' never ends the call.  
  > - The caller is still explaining who they are or what they want.  
  > - The caller is giving or repeating a number, UPI ID, account or link."
- **Status:** **VERIFIED**

---

### D. Persona & Voice Consistency

#### D1. Receptionist to Honeypot Handoff
- **Evidence:**
  - `bolna/rakshak-v0.json` lines 155–165: Mode 1 calls `classify_caller`, switches on `scam` to `switch_to_honeypot`, then acts as persona.
  - Code implementation in `app/core/rules.py` defines `ramesh`, `sunita`, and `iyer`.
  - In `app/agent/state.py` line 34: `p_key = "ramesh"` is hardcoded as default. `sunita` and `iyer` are never dynamically assigned during runtime.
- **Status:** **PARTIAL**

#### D2. Persona Gender vs Voice Mismatch
- **Evidence:**
  - Synthesizer voice: `Simran` (Female Indian voice, Sarvam AI).
  - Assigned persona: `Ramesh Kumar` / `Ramesh Sharma` ("72, retired post office clerk... says 'beta' often").
- **Finding:** **MISMATCH**. A high-pitched female voice speaks as an elderly 72-year-old grandfather named Ramesh.
- **Status:** **FAILED**

#### D3. Household Name Personalization
- **Evidence:**
  - `bolna/rakshak-v0.json` system prompt uses a generic fallback persona with hardcoded name `Ramesh Kumar`.
  - No session variable (e.g. `%(parent_name)s`) is injected into the prompt.
- **Status:** **FAILED**

---

### E. Android Screening App (T-AND, T-XFER)

#### E1. CallScreeningService Decision Logic
- **Evidence:** `android/app/src/main/java/ai/guardianline/screening/GuardianCallScreeningService.kt` lines 47–64:
  - Allowed Calls:
    ```kotlin
    responseBuilder.setDisallowCall(false)
        .setRejectCall(false)
        .setSilenceCall(false)
        .setSkipCallLog(false)
        .setSkipNotification(false)
    ```
  - Screened Calls:
    ```kotlin
    responseBuilder.setDisallowCall(true)
        .setRejectCall(true)
        .setSilenceCall(true)
        .setSkipNotification(true)
        .setSkipCallLog(false)
    ```
- **Status:** **VERIFIED**

#### E2. Bolna Gateway Whitelisting & Transfer Loop
- **Evidence:** `android/app/build.gradle.kts` line 20:
  ```kotlin
  val gatewayNumber = project.findProperty("GUARDIAN_GATEWAY_NUMBER") as String? ?: ""
  buildConfigField("String", "BOLNA_GATEWAY_NUMBER", "\"$gatewayNumber\"")
  ```
- **Finding:** `BOLNA_GATEWAY_NUMBER` defaults to `""`. When an incoming transfer arrives from Bolna, `CallScreeningLogic.kt` normalizes `""` to `null` and treats the call as `UNKNOWN_CALLER_SCREEN`. The phone rejects the call, triggering carrier forward-on-busy (`**67*`) directly back to Bolna, causing an **infinite call loop**.
- **Status:** **FAILED**

#### E3. Emergency Number Whitelist
- **Evidence:** `PhoneNumberNormalizer.kt` line 5:
  ```kotlin
  val EMERGENCY_NUMBERS = setOf("112", "100", "108", "1930", "1091")
  ```
- **Status:** **VERIFIED**

#### E4. Android Gradle Build & Unit Tests
- **Command:** `cd android; .\gradlew.bat test`
- **Output:**
  ```text
  FAILURE: Build failed with an exception.
  * What went wrong:
  Could not determine the dependencies of task ':app:testDebugUnitTest'.
  > SDK location not found. Define a valid SDK location with an ANDROID_HOME environment variable or by setting the sdk.dir path in your project's local properties file at 'android\local.properties'.
  ```
- **Status:** **CANNOT VERIFY** (Requires Android SDK installed on auditor machine).

#### E5. Physical Handset Records
- **Evidence:** `docs/carrier_matrix.md` and `evaluation/carrier_results.json` contain 0 phone model entries or real test timestamps.
- **Status:** **NOT DONE**

---

### F. Family Alerts (T-ALERT)

#### F1. Channels & Provider
- **Evidence:** `app/notify/alerts.py` implements both SMS and WhatsApp dispatching using `twilio.rest.Client`.
- **Status:** **VERIFIED**

#### F2. Indian Telecom DLT Compliance
- **Evidence:** Search for `DLT`, `entity_id`, or `template_id` across `app/notify/` yielded 0 configuration fields.
- **Finding:** Under TRAI regulations, A2P SMS to Indian mobile numbers from Twilio numbers without registered Distributed Ledger Technology (DLT) Principal Entity IDs and approved templates are filtered or dropped by Indian telecom operators.
- **Status:** **NOT DONE**

#### F3. WhatsApp Sandbox & Opt-in
- **Evidence:** `docs/lane_c_integration.md` Section 3 documents the WhatsApp sandbox limitation:
  > "WhatsApp sandbox: It only delivers to numbers that have sent the sandbox join code. Join the demo phone in advance. Messages that GuardianLine starts outside a 24-hour session need an approved template."
- **Status:** **PARTIAL** (Works for pre-joined demo handsets; cannot send unsolicited alerts to real family members in production without an approved Meta Business WhatsApp template).

#### F4. Real Handset Message Delivery
- **Evidence:** No message delivery receipts, Twilio SIDs from live runs, or screenshots exist.
- **Status:** **CANNOT VERIFY** (Requires live Twilio credentials and recipient device).

---

### G. Detection Classifier (T-CLS)

#### G1. Classifier Freeze Integrity
- **Command:** `git log 119e6c6..HEAD --oneline -- app/voice/classifier.py`
- **Output:**
  - `ae215f8` Lane D: Add YC submission draft, DPDP Act compliance brief, and 2-min demo storyboard
  - `7c5d5ee` Lane D: Add caller_summary support to classify_caller and implement run_held_out_eval runner
- **Finding:** The freeze commit `119e6c6` was broken by subsequent commits that modified regex patterns and parameters.
- **Status:** **PARTIAL**

#### G2. Whitelist Loophole Probe Suite
- **Command:** `python scripts/probe_whitelist_holes.py`
- **Output:**
  ```text
  [1/6] probe_01_fake_courier_delivery_otp: Verdict=GENUINE -> [FALSE NEGATIVE (SCAM LABELED GENUINE)]
  [2/6] probe_02_fake_police_tenant_fine:    Verdict=GENUINE -> [FALSE NEGATIVE (SCAM LABELED GENUINE)]
  [3/6] probe_03_fake_hospital_icu_advance:  Verdict=SCAM    -> [BLOCKED AS SCAM]
  [4/6] probe_04_fake_relative_highway:      Verdict=GENUINE -> [FALSE NEGATIVE (SCAM LABELED GENUINE)]
  [5/6] probe_05_fake_bank_remote_access:    Verdict=GENUINE -> [FALSE NEGATIVE (SCAM LABELED GENUINE)]
  [6/6] probe_06_fake_challan_traffic:       Verdict=SCAM    -> [BLOCKED AS SCAM]
  AUDIT SUMMARY: 4/6 probe scenarios successfully exploited whitelist loopholes!
  ```
- **Finding:** **FAILED**. 4 out of 6 trojan scams bypass the heuristic rules because benign opening phrases match genuine whitelists before coercive asks are evaluated.
- **Status:** **FAILED**

#### G3. "Unsure/Verify" Protocol in Code
- **Evidence:** `app/voice/classifier.py` line 24:
  `verdict: str  # "scam" | "genuine" | "unsure"`
- **Finding:** The system prompt in `bolna/rakshak-v0.json` handles `unsure` by asking follow-up questions, but no distinct `"verify"` verdict exists in the code enum.
- **Status:** **PARTIAL**

#### G4. Stage 2 Live LLM Execution & Latency
- **Direct Test Commands:**
  - Groq Test (`llama-3.3-70b-versatile`): Failed with `HTTPError: 404 {"error":{"message":"The model llama-3.3-70b-versatile does not exist or you do not have access to it."}}`
  - Gemini Test (`gemini-flash-latest`): Failed with `HTTPError: 429 Too Many Requests`.
- **Finding:** Both live Stage 2 LLM callers fail. Every single classifier call in dev testing has silently executed via `_classify_offline_rules` (local regex fallback).
- **Status:** **FAILED**

#### G5. Stage 2 Latency Profile Authenticity
- **Evidence:** `evaluation/stage2_latency_profile.json` lines 13–18:
  ```json
  "groq": { "error": "All Groq calls failed or invalid API key" },
  "gemini": { "error": "All Gemini calls failed or invalid API key" }
  ```
- **Finding:** The profile JSON explicitly proves that cloud LLMs failed; only the local fallback recorded latency (`median_p50_ms: 0.1`).
- **Status:** **VERIFIED**

#### G6. Handoff Document Latency Claims
- **Evidence:** `docs/handoff_lanes_a_b.md` lines 71–73 claims:
  - Groq: `~480 ms (p50) / ~920 ms (p95)`
  - Gemini: `~680 ms (p50) / ~1350 ms (p95)`
- **Finding:** These numbers contradict `evaluation/stage2_latency_profile.json`, where both Groq and Gemini failed.
- **Status:** **FAILED**

---

### H. Evaluation & Performance Claims

#### H1. Held-Out Evaluation Set
- **Evidence:** `Test-Path evaluation/held_out_scenarios.json` returned `False`.
- **Status:** **NOT DONE**

#### H2. Held-Out Evaluation Execution
- **Finding:** Cannot run `scripts/run_held_out_eval.py` without the dataset file.
- **Status:** **NOT DONE**

#### H3. Performance Claims Audit
- **Evidence:**
  - [submission/application_draft.md](file:///c:/Users/Rohith%20P%20Hegde/Desktop/Y%20combinator/submission/application_draft.md) line 43 claims: `Classification Processing Latency: 0.09 ms (local) / <1.4s (cloud)`.
- **Finding:** The `<1.4s (cloud)` claim is **unbacked and false** in this environment because both Groq and Gemini cloud endpoints fail (404 and 429).
- **Status:** **PARTIAL**

#### H4. Live Telephony Recordings & Call Records
- **Evidence:** Search for physical `.wav`, `.mp3`, or database exports from live calls yielded 0 real files. Only 5 synthetic audio clips generated by `scripts/generate_voice_smoke_set.py` exist.
- **Status:** **NOT DONE**

---

### I. Naming & History Hygiene

#### I1. Tracked File Contents & Filenames
- **Evidence:**
  - `docs/handoff_lanes_a_b.md:131`: "The Android app, family dashboard, and alert notifications are branded **GuardianLine**, while the voice receptionist persona is **Rakshak**."
  - `SprintA:bolna/rakshak-v0.json`: Named `rakshak-v0` with URLs `https://rakshak-ai-3ckj.onrender.com`.
  - `SprintA:prompts/rakshak-v1-two-mode.md` and `rakshak-v1-hangup.md`: Filenames and titles use "Rakshak".
  - `guardianline-sprint-plan.md:114` & `312`: Contains references to "AMD Slingshot".
- **Status:** **PARTIAL**

#### I2. Git Commit Messages
- **Evidence:** Commits `09d1f60`, `67d0e12`, `6738acf`, and `5a3a084` explicitly contain "Rakshak".
- **Status:** **PARTIAL**

---

### J. Secrets (T-PRIV)

#### J1. Git Secrets Hygiene
- **Evidence:** `.gitignore` excludes `.env` and `.env.local`. Only `.env.example` is tracked.
- **Status:** **VERIFIED**

#### J2. Git History Secrets Scan
- **Command:** Scanned full `git log -p --all` for regex patterns (`sk-`, `AKIA`, `AIza`, `gsk_`).
- **Result:** **0 leaked API keys found in commit history.**
- **Status:** **VERIFIED**

---

### K. Carrier & Pilot Trials

#### K1. Carrier Forwarding Matrix
- **Evidence:** `docs/carrier_matrix.md` lines 24–28:
  All entries for Jio, Airtel, and Vi are `NOT_RUN (0/3)` and `PENDING`.
- **Status:** **NOT DONE**

#### K2. Elderly Pilot Trials
- **Evidence:** `evaluation/pilot_results.json` lines 11–12:
  `"participants": []`
- **Finding:** 0 elderly participants have been tested.
- **Status:** **NOT DONE**

---

### L. Submission Readiness

#### L1. README Pitch Clarity
- **Evidence:** `README.md` lines 1–16 provide a direct, professional explanation of GuardianLine's mission and technical architecture.
- **Status:** **VERIFIED**

#### L2. Video & Pitch Deck Links
- **Evidence:** No URL to a pitch deck (Google Slides), demo video (Luma / YouTube), or public frontend dashboard exists in the repository or submission draft.
- **Status:** **NOT DONE**

#### L3. Repository Visibility
- **Command:** GitHub API check on `https://api.github.com/repos/RohitBharadwaj-rvu/rakshak-ai`.
- **Result:** `Repository is: PUBLIC`.
- **Status:** **VERIFIED**

#### L4. Aggregated Threat Intelligence View
- **Evidence:** `app/core/gui.py` provides only single-call detail views and call logs. It does not provide an aggregated threat intel table across calls.
- **Status:** **NOT DONE**

---

## 3. Top 5 Critical Blockers

These are the 5 issues most likely to prevent a successful end-to-end demo by October 31, ranked in priority order:

1. **Female Voice vs Male Persona Mismatch (D2)**
   - *Problem:* Sarvam TTS voice `Simran` is female, but the persona is 72-year-old grandfather `Ramesh Kumar`.
   - *Action:* Change Bolna synthesizer voice to an elderly male voice, or update the persona name to a grandmother (`Sunita Verma`).

2. **Stage 2 LLM Failures Dropping to Fallback (G4)**
   - *Problem:* Groq returns 404 (wrong model ID `llama-3.3-70b-versatile`), and Gemini returns 429 quota errors.
   - *Action:* Update Groq model identifier to `llama-3.1-70b-versatile` or `llama-3.3-70b-specdec`, and configure an active Gemini API key.

3. **Android Genuine Call Transfer Infinite Loop (E2)**
   - *Problem:* `BOLNA_GATEWAY_NUMBER` is empty in `build.gradle.kts`. When Bolna transfers a genuine caller to the elder, the app rejects it, forwarding it straight back to Bolna.
   - *Action:* Hardcode or configure the actual Bolna DID number in `build.gradle.kts` and whitelist it in `CallScreeningLogic.kt`.

4. **Ephemeral Render Database Wiping Call Records (B2)**
   - *Problem:* Call records are stored in `/tmp/guardianline_calls.db` on Render free tier, which wipes data upon sleep or restart.
   - *Action:* Attach an external PostgreSQL database URL in `render.yaml` (`DATABASE_URL`) or switch to persistent disk storage.

5. **Untested Carrier Call Forwarding & Handset Delivery (K1, F2)**
   - *Problem:* Zero real phone calls or carrier forwarding tests have been executed; DLT registration is absent for Indian SMS.
   - *Action:* Use WhatsApp sandbox exclusively for the live demo, pre-join all test devices, and execute Test 1 (`**67*`) manually on a physical SIM.

---

## 4. Claims at Risk

The following claims in the submission draft, README, or handoff documents are unbacked or contradicted by audit findings:

1. **Cloud Latency Claim (`<1.4s cloud`)**:
   - *Claimed in:* `submission/application_draft.md` line 43.
   - *Reality:* Unbacked. Both Groq and Gemini cloud endpoints failed during live execution; all benchmark results came from local regex.

2. **Tamil Language Support**:
   - *Claimed in:* Initial YC proposal ("starting with Tamil and Hindi").
   - *Reality:* Not done. Tamil was deleted from the codebase in commit `36500b7`.

3. **Three Personas (`Ramesh`, `Sunita`, `Prof. Iyer`)**:
   - *Claimed in:* `README.md` line 14 and `submission/application_draft.md` line 14.
   - *Reality:* Only `Ramesh` is assigned in `app/agent/state.py`. `Sunita` and `Prof. Iyer` are never selected by the tool.

4. **100% Scam Detection Rate**:
   - *Claimed in:* `submission/application_draft.md` line 38.
   - *Reality:* Vulnerable to pretexts. 4 out of 6 trojan scam probes in `scripts/probe_whitelist_holes.py` bypass the classifier and are labeled `GENUINE`.

---

## 5. Unexpected Findings

1. **Repository is Already Public**:
   - The GitHub repository `RohitBharadwaj-rvu/rakshak-ai` is currently publicly visible on GitHub, despite sprint plan rules mandating a formal sign-off before making it public.
2. **Old Repository Branding in Production Domain**:
   - The production Render service is deployed under the old hackathon name: `https://rakshak-ai-3ckj.onrender.com`.

---

## 6. What Could Not Be Checked (CANNOT VERIFY)

1. **C4 (Dynamic Voice Switching):**
   - *Needs:* Official Bolna multi-synthesizer API documentation or live test agent validation.
2. **E4 (Android Unit Tests):**
   - *Needs:* Android SDK (`ANDROID_HOME` or `local.properties` path) configured on the local testing machine.
3. **F4 (Physical Message Delivery):**
   - *Needs:* Active Twilio account SID/token with funded balance and an approved recipient device.
