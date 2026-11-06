# GUARDIANLINE: READ-ONLY AUDIT & STATUS MATRIX (E1–E10, N1–N9)

**Date:** November 6, 2026  
**Auditor Mode:** Read-Only Verification (No code modified, installed, or refactored)  
**Branch:** `voice` / `main`  
**Purpose:** Pre-interview technical gap analysis for Bolna x Y Combinator Voice AI Hackathon.

---

## 1. Status Matrix

| ID | Item | Verdict | Evidence | What is Missing | Effort (Mins) | Risk | Depends On | Worth Doing Before Interview? (Y/N + Reason) |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **E1** | **The 2 Failing Tests** | **Partial** | `tests/integration/test_alerts.py:423` (assert 1500 in (100..1200)) & `tests/integration/test_dashboard.py:54` (assert 401 == 503). 502/504 pass. | Fix assertions: add 1500 to allowed endpointing tuple in `test_alerts.py`; align `_master_token()` fallback in `test_dashboard.py`. | 15 | Very Low | None | **Y** — A failing test suite is an immediate disqualifier for technical judges; 15 mins gets 100% pass rate. |
| **E2** | **Demo Stability** | **Partial** | Backend runs locally on port 8000 via transient tunnel (`mart-louise-forbes-comfortable.trycloudflare.com`). Bolna agent (`bolna/rakshak-v0.json:6`) points to sleeping Render URL (`rakshak-ai-3ckj.onrender.com`). | Sync Bolna agent (`scripts/sync_bolna_agent.py`) with active tunnel URL; record 1 clean backup call video/audio. | 30 | Low | E1 | **Y** — If Bolna cloud calls Render instead of your local server, the live demo will hit 12s cold start and fail. |
| **E3** | **Real Carrier Forwarding** | **Implemented-unverified** | `evaluation/carrier_results.json:8` marks Gate 1 `status: "NO_GO"`, `all tests: NOT_VERIFIED`. Android dialer opens `**67*` via `MainActivity.kt:299`. | 1 single physical SIM call trial (dial `**67*+918064261985#`, decline call, verify Bolna answers). | 45 | Medium | Physical SIM | **Y** — Being able to say "I verified this on my physical Airtel/Jio phone today" destroys competitor demo-ware claims. |
| **E4** | **Overclaim Audit** | **Complete** | Audit documented below. Mocks exist for Auto-Freeze (`auto_freeze.py:53`), Family Heartbeat (`family.py:488`), and OTP cloaking dialog (`MainActivity.kt:1195`). | Add clear `[Simulation / Defense Specification]` labels to GUI cards so judges see engineering realism instead of deception. | 25 | Low | None | **Y** — Experienced YC judges punish fake claims instantly; labeled defense specs earn technical respect. |
| **E5** | **Syndicate Demo Data** | **Implemented-verified** | SQLite DB (`guardianline_calls.db`) contains 24 calls; `rahul.sbi@ybl` is shared across 7 real calls, verified via script. GUI renders linked calls at `gui.py:720`. | None. Live data already links in the dashboard. | 0 | None | None | **N** — Already working with real multi-call extraction data in the database. |
| **E6** | **Safety Net for Real Callers** | **Partial** | Contact whitelist (`CallScreeningLogic.kt:69`) & Emergency whitelist (`112, 1930`) verified. `approve_legitimate_caller` tool exists (`tools.py:270`), but does NOT bridge call to elder. | SIP call-bridging or outbound transfer back to parent phone. | 180 | High | Telephony carrier | **N** — Too risky to engineer SIP transfer 12 hours before interview; explain "instruction whisper to driver" as current design. |
| **E7** | **Honeypot Call Cap** | **Implemented-verified** | Bolna task config (`bolna/rakshak-graph.json:37`) enforces `call_terminate: 400` (6m 40s) & `hangup_after_silence: 20`. Prompt forces agent to hold line (`sync_bolna_agent.py:140`). | None. Hard cap is enforced in cloud engine. | 0 | None | None | **N** — Already implemented and verified in Bolna task definition. |
| **E8** | **Latency & Cost** | **Partial** | In-memory regex benchmarked at `0.42ms` (`held_out_report.md`). LLM profiled at `480-950ms` (`stage2_latency_profile.json`). Cost formula derived in `docs/lane-a/voice-run-budget.md:6` ($0.06/min). | Live end-to-end acoustic turn measurement script across cellular audio. | 45 | Low | None | **Y** — Having 1 measured roundtrip latency number (e.g. 1,280ms) gives hard data when asked. |
| **E9** | **Caretaker Visibility** | **Partial** | Per-call alerts with HMAC review links in `alerts.py:270`. Web dashboard live. But Twilio keys absent from `.env`; daily summary cron missing. | Twilio Sandbox credentials in `.env` or daily summary batch script. | 30 | Low | Twilio Sandbox | **Y (Twilio only)** — Showing a real WhatsApp alert landing on your phone during the demo is high theater. |
| **E10** | **Forwarding Health Check** | **Partial** | WorkManager checks Android CallScreening role every 15 mins (`ProtectionStatusWorker.kt:43`). Dialer launcher for `**67*` in `MainActivity.kt:299`. Zero carrier-level health check. | Automated outbound carrier probe. | 240 | High | Telco operator | **N** — Carrier USSD interrogation is notoriously blocked on consumer Android; explain role monitoring as current scope. |
| **N1** | **Bank-Ready Mule Report** | **Implemented-verified** | `evidence.py:123-160` generates `ChakshuPacket` and `ReportSuspectPacket`. `ifsc.py:resolve_ifsc` queries Razorpay API for bank/branch/city. Serialized on `/api/calls/{id}/report`. | None. Structured schemas with SHA-256 hashes exist and pass unit tests. | 0 | None | None | **N** — Already built, verified, and rendered on dashboard. |
| **N2** | **Simulated-Scammer Harness** | **Implemented-verified** | `scripts/text_harness.py` (667 lines) simulates multi-turn conversations against LLM. `bolna/scammer_agent.json` defines Bolna caller. `scripts/compute_metrics.py` generates scorecard. | Run script on 5 scenarios to output fresh benchmark markdown table. | 20 | Low | Text harness | **Y** — Running `compute_metrics.py` gives you an empirical table of 42 scenarios to flash on screen. |
| **N3** | **Language Mirroring** | **Partial** | Sarvam `saaras:v3` STT handles Hindi/Hinglish/English. But prompt (`sync_bolna_agent.py:19`) strictly forces Hindi Ramesh output. Kannada/Tamil explicitly unsupported. | Multi-language persona prompt router. | 120 | Medium | Prompts | **N** — Deep Hindi/Hinglish execution for North/Central India is defensible; don't break prompt hours before interview. |
| **N4** | **Scammer Knowledge Audit** | **Partial** | `location.py:182` extracts claimed location and flags mismatch against IFSC/SIM circle. But no schema for claimed elder PII (Aadhaar digits, address). | Dedicated PII claim extraction regex in `extractor.py`. | 60 | Low | Extractor | **N** — Nice-to-have forensic touch, but secondary to mule account extraction. |
| **N5** | **Script Classification** | **Implemented-verified** | `cleanup.py:219-243` (`_infer_scam_type`) tags 6 families: `digital_arrest`, `electricity_bill_scam`, `bank_kyc`, `customs_parcel`, `traffic_challan`, `job_scam`. Stored in DB summary. | Visual aggregate trend bar on dashboard. | 45 | Low | `gui.py` | **Y** — Adding a small horizontal breakdown bar of scam types on `/dashboard` makes it look like enterprise security software. |
| **N6** | **Cross-Customer Burn** | **Partial** | Cross-call grouping exists retrospectively in SQLite/GUI (`gui.py:720`). But runtime screening does NOT block known numbers upfront. | Pre-screening lookup against `mule_identifiers` in `CallScreeningLogic.kt`. | 60 | Medium | Android build | **N** — Current design relies on cloud screening; retrospective syndicate display is enough for demo. |
| **N7** | **Evidence Integrity** | **Implemented-verified** | `evidence.py:100-106` computes canonical JSON SHA-256 hash of transcript + audio URL. Displayed in GUI and validated in `tests/unit/test_evidence.py`. | None. Fully implemented and passing tests. | 0 | None | None | **N** — Already built and verified. |
| **N8** | **KPI Surface** | **Partial** | `seconds_from_start` tracked per entity in `SuspectIdentifier`. Total turns tracked in metrics. But no dashboard summary card for "Time-to-first-rail" or "Attacker Minutes Wasted". | Small summary metrics card at top of `/dashboard` (Minutes Wasted, Mule Rails Burned). | 30 | Low | `gui.py` | **Y** — Highly visible commercial metric for judges (*"42 Attacker Minutes Wasted, 8 Mule Accounts Captured"*). |
| **N9** | **Real Alert in Demo** | **Partial** | Twilio dispatch logic with retries and GSM-7 budgeting complete in `alerts.py`. Blocked solely by missing `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` in `.env`. | Add Twilio sandbox keys to `.env` + join sandbox on your phone. | 15 | Low | Twilio account | **Y** — Showing your phone buzz with a real WhatsApp alert when Bolna finishes a test call is 10x more persuasive than UI logs. |

---

## 2. Full Overclaim Audit (from Item E4)

Every claim in the project where documentation, UI, or code comments claim live integration, contrasted against what the code actually does:

| Feature / Claim | File & Line | Claimed in Docs / UI / Comments | Reality in Code | Labeled Simulated? |
| :--- | :--- | :--- | :--- | :---: |
| **Interbank Freeze Pipeline** | [`app/voice/auto_freeze.py:53-157`](file:///app/voice/auto_freeze.py#L53-L157) | *"Autonomously dispatch freeze commands across national banking & payment rails... Early Warning Services (EWS), CIFAS, NPCI, Chainalysis."* | Generates local mock string IDs (`EWS-CASHAPP-*`, `NPCI-UPI-*`) via `hashlib.sha256` and updates local SQLite DB. Zero external HTTP requests made. | **NO** |
| **Dashboard Auto-Freeze Banner** | [`app/core/gui.py:688-695`](file:///app/core/gui.py#L688-L695) | *"🛡️ ZERO-BURDEN AUTONOMOUS FREEZE DISPATCHED: GuardianLine eliminated all manual paperwork for the family... instant freeze command was routed to national interbank fraud switches (EWS, CIFAS, NPCI). Mule accounts locked."* | Hardcoded HTML string displayed if `evidence_status == "auto_frozen"` or `cls == "scam"`. Displays local mock receipts. | **NO** |
| **Pre-Victim Burning Badge** | [`app/core/gui.py:805-808`](file:///app/core/gui.py#L805-L808) | *"Pre-Victim Burning Pipeline: Scammer mule drop extracted prior to victim transfer. Ready for automated network freeze. [READY TO BURN]"* | Static HTML markup rendered for any call with extracted identifiers. | **NO** |
| **Passive Family Heartbeat** | [`app/core/family.py:488-515`](file:///app/core/family.py#L488-L515) | *"Zero-Click Passive Heartbeat Verification (AI Voice Clone / Grandparent Defense). Queries device telemetry of family members (Wi-Fi, battery, geofence, call state)..."* | Returns static hardcoded Python dict: `Google_Corp_Secure`, battery `87%`, stationary, synthetic clone probability `99.4%`. | **NO** |
| **Heartbeat Dashboard Card** | [`app/core/gui.py:810-815`](file:///app/core/gui.py#L810-L815) | *"❤️ Zero-Click Passive Telemetry Heartbeat: Verified child (Amit) device online at Google_Corp_Secure Wi-Fi · Battery 87% · Stationary... AI Voice Clone probability 99.4%. [CHILD VERIFIED SAFE]"* | Static HTML card rendered beside call details. | **NO** |
| **Dynamic OTP Cloaking** | [`android/app/src/main/java/ai/guardianline/MainActivity.kt:1195-1215`](file:///android/app/src/main/java/ai/guardianline/MainActivity.kt#L1195-L1215) | Button `🔒 Test Dynamic OTP Cloak` claims *"DEFENSE ACTIONS APPLIED: Notification banner hidden from screen while caller is on the line. Device clipboard wiped..."* | Launches an Android `AlertDialog` with simulated text. No background `NotificationListenerService` exists to cloak real incoming SMS or WhatsApp notifications. | **PARTIAL** (Text contains `[SIMULATED SCENARIO]`, but row toggle implies active background engine) |
| **Financial Circuit Breaker** | [`android/app/src/main/java/ai/guardianline/MainActivity.kt:1175-1194`](file:///android/app/src/main/java/ai/guardianline/MainActivity.kt#L1175-L1194) | Switch `Scam Circuit Breaker` claims *"Remote desktop apps (AnyDesk, TeamViewer, QuickSupport) are BLOCKED. High-value banking apps in cooling-off lock."* | Launches an Android `AlertDialog`. Zero accessibility service, DevicePolicyManager, or process-killing logic exists. | **NO** |
| **Live Family Alerts Delivery** | [`evaluation/live_calls/alert_delivery_proof.json:4`](file:///evaluation/live_calls/alert_delivery_proof.json#L4) | Claims `status: "VERIFIED"`, `twilio_message_sid: "SM0123456789abcdef0123456789abcdef"`. | Static mock JSON fixture. `TWILIO_*` credentials are empty in `.env`. Real SMS/WhatsApp dispatch has never run to a physical handset. | **NO** |
| **Carrier Field Testing** | [`README.md:192`](file:///README.md#L192) vs. [`evaluation/carrier_results.json:8`](file:///evaluation/carrier_results.json#L8) | README notes carrier forwarding configured via `**61*` / `**67*`. | `carrier_results.json` explicitly states `gate_1_decision: "NO_GO"` and `attempts: []` across Jio, Airtel, and Vi. | **YES (in JSON, but obscured in README)** |
| **Multi-Country Telephony** | [`app/core/rules.py:24-28`](file:///app/core/rules.py#L24-L28) vs. [`scripts/sync_bolna_agent.py`](file:///scripts/sync_bolna_agent.py) | Claims US Cashtag, UK Sort code, and ABA routing defense. | Regex extractors exist, but Bolna agent runs strictly in Hindi on an Indian virtual mobile number (`+918064261985`). It cannot screen or converse in the US or UK. | **NO** |

---

## 3. Conflicts and Dependencies Between Items

1. **E2 (Demo Stability) relies on E1 (Failing Tests):** If you run test suites during your interview demo, you cannot pass without fixing the 2 assertions in `test_alerts.py` and `test_dashboard.py`.
2. **E2 (Demo Stability) conflicts with local Cloudflare Tunnel restarts:** Every time `cloudflared.exe` restarts, it generates a new random subdomain on `trycloudflare.com`. If you restart the tunnel, you **MUST** run `python scripts/sync_bolna_agent.py` so Bolna knows the new URL, or Bolna will continue calling the stale URL or sleeping Render dyno.
3. **N9 (Real WhatsApp Alert) depends on Twilio Sandbox Join:** You cannot send a WhatsApp alert from Twilio Sandbox without the target phone sending the sandbox keyword (e.g. `join <word>`) to `+1 415 523 8886` first.
4. **N5 (Script Classification) & N8 (KPI Surface) depend on `app/core/gui.py`:** Both are small UI enrichments to the web dashboard that pull from existing SQLite data. They can be done together in 45 minutes.

---

## 4. Recommended Build Order for a 6-Hour Window

Target: Maximize judge credibility, eliminate demo-fail risks, and turn simulation into verified reality.

```
[Hour 1: Clean Codebase & Fix Blockers]
  ├── Task 1 (15m): Fix the 2 failing tests (E1) -> 504/504 tests pass.
  ├── Task 2 (10m): Scrub BOLNA_API_KEY from android/app/build.gradle.kts (Security).
  └── Task 3 (20m): Label simulated cards in gui.py (E4) -> Reframe as "Defense Protocol Spec".

[Hour 2: Demo Bulletproofing & Bolna Sync]
  ├── Task 4 (25m): Sync Bolna agent to active Cloudflare tunnel (E2) -> Verify live tool response.
  └── Task 5 (35m): Pre-seed 1 verified direct-dial demo flow on phone -> Dial +918064261985 with script.

[Hour 3: Real WhatsApp Delivery Proof]
  ├── Task 6 (20m): Add Twilio credentials to .env and join Sandbox on demo phone (N9).
  └── Task 7 (25m): Trigger test call via mock_bolna.py -> Verify real WhatsApp arrives on your phone.

[Hour 4: Physical SIM Carrier Sanity Check]
  ├── Task 8 (45m): Dial **67*+918064261985# on a real Airtel/Jio phone (E3) -> Decline call, verify Bolna rings.
  └── Task 9 (15m): Update evaluation/carrier_results.json with real timestamp & carrier confirmation.

[Hour 5: Commercial Dashboard KPI Polish]
  ├── Task 10 (30m): Add KPI header to /dashboard (N8) -> "Attacker Minutes Wasted", "Mule Accounts Captured".
  └── Task 11 (30m): Add scam script family breakdown bar to /dashboard (N5).

[Hour 6: Rehearsal & Verification]
  ├── Task 12 (30m): Run full dry-run: Dial number -> Bolna talks -> Extraction -> Dashboard updates -> WhatsApp arrives.
  └── Task 13 (30m): Save a 45-second screen recording of the working loop as an emergency offline fallback asset.
```
