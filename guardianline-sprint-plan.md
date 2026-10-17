# GuardianLine Sprint Plan

Oct 16, 2026 · @RRSS

Five sprints run from today to Thu Oct 29, and we submit on Oct 30, 2026, a day before the Oct 31 close. Each dev owns one lane end to end. The interfaces frozen in Sprint 0 let all four build at the same time instead of waiting on each other.

## Lanes

Each dev keeps one lane for all five sprints and owns that lane's folders, so pull requests rarely collide. Assign names at today's kickoff.

| Lane | Owns | Code it touches | Needs |
| --- | --- | --- | --- |
| A · Voice agent | Bolna agent, the two-mode prompt, personas in Hindi and English, tool wiring, inbound number, the scammer agent for voice tests, the demo call | `prompts/`, `bolna/` (exported agent config) | Speaks Hindi or English; good at prompt work |
| B · Backend and intel | Tool endpoints, post-call webhook, CallRecord store, spoken-number normalizer, post-call extraction and LLM cleanup, 1930 report, hosting | `app/voice/`, `app/core/rules.py`, `app/agent/nodes/extractor.py` | Python; knows the honeypot repo best |
| C · Phone and family | Carrier tests, Kotlin screening app, setup guides, family alerts, family dashboard, genuine-call tests with elderly users | `android/`, `app/notify/`, `app/core/gui.py`, `docs/setup/` | Kotlin; holds the Jio, Airtel and Vi SIMs |
| D · Detection and eval | `classify_caller`, scam and genuine scenarios, text and voice evaluation, metrics, README, submission text, demo video edit | `evaluation/`, `app/voice/classifier.py`, `README.md`, `submission/` | LLM prompting; clear writing |

If nobody on the team writes Kotlin, drop app mode at kickoff. Lane C then starts on basic mode and the family outputs on day 1.

## Timeline

Four lanes run in parallel every sprint; Gate 1 on Oct 20 decides app mode.

| Sprint | A · Voice agent | B · Backend | C · Phone, family | D · Detection |
| --- | --- | --- | --- | --- |
| Sprint 0 · Oct 16–17 | Number requested; agent v0 answers; Bolna docs checked | Repo and public URL; interfaces frozen; stub endpoints live | Carrier Test 1; screening app begun; results table | README fixed; 6 fixture calls; `mock_bolna.py` |
| Sprint 1 · Oct 18–20 | Two-mode prompt; Hindi, Ramesh; tools wired | Real tools; webhook to SQLite; normalizer v1 | Tests 2, 3 and 4; family alert v1; testers asked | `classify_caller` v1; genuine scenarios; text harness |
| Sprint 2 · Oct 21–23 | 3 personas; Hindi and English (with Hinglish); message, transfer | Normalizer v2; LLM cleanup; CallRecord API | Go: whitelist, APK. No-go: setup guide and dashboard v1 | Classifier tuned; red-team scenarios; ground-truth labels |
| Sprint 3 · Oct 24–26 | Edge cases; scammer agent; demo script | 1930 report; reflection tasks; hardening, CSV | Dashboard or APK; consent form; testers booked | Metrics script; eval set frozen; README draft |
| Sprint 4 · Oct 27–29 | Voice eval runs; prompt fixes; demo recorded | Bug fixes; extraction misses; backend kept up | Elderly-user tests; carrier results; demo phone ready | Metrics computed; submission text; video edited |

Gates: **Gate 1 · Oct 20** (app mode go or no-go, after Sprint 1) · **Feature freeze · Oct 26** (bug fixes only, after Sprint 3) · **Submit · Oct 30** (Oct 31 is buffer only).

Only lane C's Sprint 2 and 3 work depends on Gate 1. The other three lanes follow the same plan either way.

## Interfaces

B and A write these into `docs/interfaces.md` and freeze them by Sat Oct 17. After that, any change needs a heads-up to every lane that reads the interface.

| Interface | Direction | Carries | Owner |
| --- | --- | --- | --- |
| `classify_caller` | Bolna → backend, mid-call | Call ID, caller number, conversation so far (or a caller summary the agent writes) → verdict (scam, genuine, unsure), confidence, reason | D |
| `switch_to_honeypot` | Bolna → backend, mid-call | Call ID, language → persona name, persona lines, fake bait details | B |
| `log_intel` | Bolna → backend, mid-call | Call ID, type (UPI, phone, account, IFSC, link), value as heard | B |
| Post-call webhook | Bolna → backend | Transcript, duration, caller number, recording link | B |
| CallRecord | Backend store, read by every lane | Call ID, caller number, start time, duration, verdict, time of the honeypot switch, persona, transcript, extracted intel, summary, report link | B |
| `call.finalized` event | Backend → alerts and dashboard | Call ID, fired once the CallRecord is final | B to C |
| Transfer and whitelist | Bolna ↔ Android app | The app whitelists the Bolna number; the transfer target is the parent's own number | A and C |

Two details depend on Bolna and are Sprint 0 checks for A: whether custom functions receive the transcript and caller number, and what the webhook payload looks like. Until the first real call, D's fixture payloads stand in for real traffic.

## Definition of done

Done is binary: every line in the list below is true, or the item stays open. Working on one laptop doesn't count. Suite designs and their pass bars are in the Test suites part of this file.

**A task is done when**

- It is merged into the voice branch through a pull request reviewed by someone from another lane.
- Its suite in Test suites has the listed cases written and passing in CI. A manual suite has a dated result row in the shared sheet instead.
- It works against the deployed backend and the real Bolna agent, not only on localhost or a mock. Only the fixtures, the mock and the harness may be mock-only.
- A teammate other than the author has run it once, using only the instructions in the pull request.
- Any interface change is in `contracts/` and T-CONTRACT passes.
- New settings are in `.env.example` and no secret is committed.

**A sprint is done when**

- Every line of its exit test passes live at the sprint demo, on the deployed system.
- Every item ticked in that sprint meets the task rules above.
- Unfinished items are moved into the next sprint by name, with an owner. Nothing rolls over silently.

**Two kinds of pass bar**

| Kind | Examples | If missed |
| --- | --- | --- |
| Reliability | Every call produces a CallRecord, every scam call fires an alert, zero bait leaks, zero invented digits | A bug that blocks the sprint. Fix it before anything else. |
| Quality | Detection rate, false positives, extraction accuracy, latency | Fix it in the next sprint, or narrow the claim and report the measured number. |

A pass bar changes only by team decision at a sprint demo, written into this doc with the date. Nobody edits a bar to make a failing test pass.

## Sprint 0 · Fri Oct 16 – Sat Oct 17 · Unblock and freeze interfaces

By Saturday night, every outside dependency is requested and every interface is written down. The inbound number is the longest wait in the plan, so it starts today.

**Kickoff today (30 minutes, whole team)**

- [ ] Assign lanes A to D.
- [ ] Confirm demo languages (default Hindi and English, with Hinglish) and name a reviewer for each.
- [ ] Decide who writes Kotlin. Nobody means app mode is dropped now.
- [ ] List SIMs and phones: Jio, Airtel and Vi, and which phones run Android 10 or later.
- [ ] Choose a branch or a new repo for the voice version.

**A · Voice agent**

- [ ] Join the Bolna Slack. Ask about API credits, the fastest Indian inbound number (Exotel or Plivo KYC), and which numbers Jio forwards to.
- [ ] Start the inbound number request today.
- [ ] Create agent v0: Indian-language speech-to-text, a fast LLM, Sarvam TTS. Make test calls in Hindi and English.
- [ ] Check the Bolna docs on four points: what custom functions receive, how call transfer works, the post-call webhook payload, and the outbound call API (needed for the scammer agent). Add the answers to `docs/interfaces.md`.

**B · Backend and intel**

- [ ] Clone the repo, install, run `python run.py`, and confirm the text honeypot works. Create the voice branch.
- [ ] Set up a stable public URL, such as a named Cloudflare tunnel or a small VM. The URL must survive restarts, because Bolna's config points at it.
- [ ] Write `docs/interfaces.md` with A and freeze it Saturday night.
- [ ] Deploy stub endpoints that return canned responses, so A can wire tools on day 2.

**C · Phone and family**

- [ ] Run carrier Test 1 (manual Decline) on Jio, Airtel and Vi. Record whether it forwards and which caller number shows.
- [x] Start the bare-bones Kotlin app: a call-screening service that rejects every unknown number.
- [x] Start the carrier results table: carrier, test, pass or fail, caller number kept.

**D · Detection and eval**

- [ ] Remove the AMD Slingshot references from the README.
- [ ] Write 6 fixture webhook payloads in Bolna's documented shape: a digital-arrest scam with a UPI ID, a KYC scam with a spoken account number, a courier and a clinic (both genuine), a scam with garbled digits, and an early hang-up.
- [ ] Write `scripts/mock_bolna.py` to replay the fixtures into the webhook, so B and C can build before real calls exist.
- [ ] Draft the digital-arrest scenario in `evaluation/scenarios/`.

**Exit test (every line passes, live at the sprint demo):**

- [ ] `docs/interfaces.md` and the schemas in `contracts/` are merged, and T-CONTRACT passes in CI against the stubs and all 6 fixtures.
- [ ] T-HOST passes: `/health` answers a phone on mobile data, and the URL survives a restart.
- [ ] CI runs on every pull request, and the T-PRIV secrets scan is green.
- [ ] Agent v0 holds a 1-minute test call in Hindi and another in English, with both recordings saved.
- [ ] The inbound number request has a reference number from the provider, or the number is live.
- [ ] T-CARRIER Test 1 is logged for every SIM we have, 3 attempts each.

## Sprint 1 · Sun Oct 18 – Tue Oct 20 · Walking skeleton

A teammate dials the Bolna number directly. The agent screens the call, switches to a persona, and after hang-up a CallRecord with the extracted UPI ID is in the database. The sprint ends at Gate 1, the app-mode go or no-go, on Oct 20, 2026.

**A · Voice agent**

- [ ] Write the two-mode prompt v1 (screening receptionist, then honeypot) in Hindi with one persona, Ramesh. Prompts live in `prompts/`; Bolna holds a copy.
- [ ] Wire `classify_caller`, `switch_to_honeypot`, `log_intel` and the post-call webhook to B's endpoints.
- [ ] Give the persona a "slowly, beta, I'm writing it down" habit so scammers dictate UPI IDs and account numbers digit by digit.
- [ ] Attach the inbound number when it arrives, and run carrier Tests 3 and 4 with C.

**B · Backend and intel**

- [ ] Build the real `switch_to_honeypot` (persona plus fake bait from `app/agent/state.py`) and `log_intel`.
- [ ] Write the webhook handler: Bolna payload to CallRecord in SQLite. A repeated delivery of the same call must not create a second record.
- [ ] Post-call v1: run the existing extractor on the transcript and merge in the `log_intel` captures.
- [ ] Spoken-number normalizer v1 with unit tests: English and Hindi number words, "double" and "triple", "at the rate" to @, "dot".

**C · Phone and family**

- [ ] Finish the screening app and run Test 2 on every carrier.
- [ ] Run Tests 3 and 4 with A once the number is live.
- [x] Build family alert v1 on the Twilio WhatsApp sandbox or SMS, fired by `call.finalized`. Test it with `mock_bolna.py`.
- [ ] Ask each teammate for 1 or 2 elderly relatives willing to test genuine calls.

**D · Detection and eval**

- [ ] Build `classify_caller` v1: a fast LLM over the conversation, returning verdict, confidence and reason. Aim for under 1 second so the call has no dead air.
- [ ] Add 6 to 8 genuine-caller scenarios: bank, courier, clinic, a relative on a new number, school, delivery. False positives can't be measured without them.
- [ ] Build the text-mode harness: the scammer simulator against the same prompt and tools, in text, on the same LLM Bolna uses. This lets us iterate without spending call minutes.
- [ ] Run a text-mode baseline for detection and false positives across all scam and genuine scenarios.

**Gate 1 rule:** if Test 2 and Test 3 pass on at least one carrier, build app mode. If not, ship basic mode only; C moves to setup guides and the dashboard, and D swaps the application wording.

**Exit test (every line passes, live at the sprint demo):**

- [ ] 3 direct-dial calls in a row using the Hindi scam script each show the honeypot switch in the log, a CallRecord within 60 s of hang-up, and the planted UPI ID extracted exactly.
- [ ] T-NORM (at least 80 cases so far), T-EXT, T-TOOLS, T-HOOK, T-SCN and T-HARN are green in CI.
- [ ] Two people have reviewed and signed off the bait list.
- [ ] T-ALERT: a fixture scam call puts a WhatsApp or SMS on a test phone within 2 minutes.
- [ ] T-AND unit tests are green.
- [ ] The T-STT choice is written into this doc with its numbers.
- [ ] T-CLS and T-CONV baselines are saved. No bar applies yet.
- [ ] T-CARRIER Test 2 is logged on every carrier, plus Tests 3 and 4 if the number is live.
- [ ] The Gate 1 decision is written into this doc with the carrier evidence.

## Sprint 2 · Wed Oct 21 – Fri Oct 23 · Real languages, real routing

All three personas speak naturally in Hindi and English (with natural Hinglish code-switching). The routing mode we ship works on a real SIM. Post-call extraction handles spoken digits.

**A · Voice agent**

- [ ] Rewrite Ramesh, Sunita and Prof. Iyer for speech in Hindi and English. Remove the SMS rules (typo injection, "never say call"). Reviewers check both languages.
- [ ] Build the genuine-caller path: take a message in basic mode, or transfer to the parent's number in app mode.
- [ ] Add a bait rule to the prompt: speak only the bait the backend serves, and stall on OTP or Aadhaar requests instead of inventing details.
- [ ] Cut latency: in-character filler lines while tools run ("wait, let me find my glasses"), and tune endpointing and interruptions.

**B · Backend and intel**

- [ ] Normalizer v2: English, Hindi, and Hinglish spoken numbers, mixed scripts, numbers that switch language mid-string.
- [ ] Post-call LLM cleanup with Mistral Large: check and fix the extracted intel, and write a call summary. Remove Mistral from every live path.
- [ ] Add a read API for CallRecords (`/api/calls`, `/api/calls/{id}`) for the dashboard and metrics.

**C · Phone and family, if Gate 1 is go**

- [ ] Whitelist saved contacts and the Bolna number. Test a genuine-caller transfer end to end with no call loop.
- [x] Add a one-tap setup screen that dials the forward-on-busy code (`**67*<number>#`).
- [ ] Build the first installable APK.

**C · Phone and family, if Gate 1 is no-go**

- [ ] Write the basic-mode setup guide per carrier: `**61*<number>#`, checked with `*#61#`.
- [ ] Build family dashboard v1 by adapting `/gui` on top of B's API: recent calls, verdicts, extracted details.

**D · Detection and eval**

- [ ] Tune the classifier with the harness. Log detection and false positives after every change.
- [ ] Add red-team scenarios: the scammer demands an OTP, an Aadhaar number, a screen-share app install, or a video call. A pass means only bait was given.
- [ ] Label every scenario with ground truth: the expected verdict, plus the UPI ID or account number the scammer will say.

**Exit test (every line passes, live at the sprint demo):**

- [ ] Live, through the shipping routing mode on a real SIM: an English scam call, a Hindi scam call and a genuine call each get the right verdict and a CallRecord. The genuine call ends in a message or a transfer.
- [ ] T-CONV: zero hard-check violations across all scenarios in both languages.
- [ ] T-CLS meets its Sprint 2 bar: recall of at least 85%, false positives at most 10%.
- [ ] T-NORM (full corpus of 150+ cases, English and Hindi included), T-CLEAN and T-API are green.
- [ ] T-VOICE smoke set: the reliability checks pass on all 5 calls.
- [ ] The first T-LAT measurement, on 10 calls, is logged.
- [ ] If Gate 1 was go: T-XFER passes 5 of 5, and the T-AND field script passes on the demo phone. If no-go: T-SETUP passes for every carrier we'll name, and the T-DASH automated checks are green.

## Sprint 3 · Sat Oct 24 – Mon Oct 26 · Feature complete

Every claim in the application works end to end, and features freeze on the night of Oct 26, 2026. After the freeze we fix bugs only.

**A · Voice agent**

- [ ] Handle edge cases: a silent caller, an early hang-up, a scammer who switches language, an urgent genuine caller such as a hospital, and a maximum call length.
- [ ] Build the scammer agent in Bolna using outbound calls, for the voice test runs. Dry-run 3 scenarios with D.
- [ ] Write the demo call script for the teammate who plays the scammer.

**B · Backend and intel**

- [ ] Build the 1930 report generator: scammer number, UPI IDs, accounts, call summary, time. Link it from the family alert.
- [ ] Run the existing reflection and enrichment tasks on each transcript after the call.
- [ ] Harden: webhook retries, logs keyed by call ID, CSV export of CallRecords for metrics.

**C · Phone and family**

- [ ] If go: family dashboard v1 (adapt `/gui`), plus a signed APK with an install guide.
- [ ] If no-go: dashboard polish (call detail, transcript, report download), and confirm basic mode on every carrier.
- [ ] Write the consent form and book the 5 to 10 elderly genuine-call tests for Sprint 4.

**D · Detection and eval**

- [ ] Write the metrics script: it reads the CallRecord CSV and the ground-truth labels and outputs the five metrics in Sprint 4.
- [ ] Freeze the evaluation set (scenarios and labels) before any voice run.
- [ ] Start the README rewrite: architecture, setup, how to run.

**Exit test, the feature freeze (each claim in our application, with its proof):**

- [ ] Android screens unknown calls before they ring: the T-AND field script and 24-hour soak pass, and T-CARRIER Tests 2 and 3 pass on at least one carrier. Otherwise the application text is switched to basic mode only.
- [ ] Unanswered calls roll over to the agent on any phone: T-CARRIER Test 4 passes on every carrier we'll name, and T-SETUP passes for each one.
- [ ] The agent speaks Hindi and English (with natural Hinglish): the T-CONV language check passes in both, and reviewers have signed off.
- [ ] Genuine callers get connected or leave a message: the T-CONV message bar is met, and T-XFER passes if app mode is go.
- [ ] Scammers are kept talking: the T-CONV switch and no-early-hang-up bars are met.
- [ ] UPI IDs, phone numbers and accounts come out of the transcript: the T-EXT bars are met, and T-CLEAN has zero ungrounded values.
- [ ] The family gets an alert: T-ALERT is green, with a live message within 2 minutes.
- [ ] A pre-filled 1930 report is generated: T-RPT is green, including the portal walk-through.
- [ ] Only fake bait is given out: zero bait leaks across the T-CONV red-team runs and the T-VOICE smoke calls.
- [ ] Scam detection: T-CLS meets its freeze bar.
- [ ] T-LAT, T-SCAM, T-DASH, T-POST and T-MET meet their bars.
- [ ] Every CI suite is green on the freeze commit, which is tagged `freeze`.

## Sprint 4 · Tue Oct 27 – Thu Oct 29 · Measure and record

This sprint produces measured numbers and a recorded demo, with no new features. The demo is recorded on Oct 28, 2026, with Thursday kept for a re-take and the edit.

| Metric | How we measure it | Source |
| --- | --- | --- |
| Detection rate | Scam scenarios where the agent switched to honeypot, divided by all scam scenarios | Voice runs |
| False positives | Genuine calls flagged as scam, divided by all genuine calls | Simulated genuine calls plus the elderly-user tests |
| Scammer time wasted | Average minutes from the honeypot switch to hang-up. Report it as simulated, because the scammer is our own agent | CallRecords |
| Extraction accuracy | Calls where at least one planted UPI ID or account was captured exactly, divided by calls where one was said | Ground-truth labels |
| Carrier coverage | Carrier and mode pairs that pass with the caller number kept | Carrier results table |

**A · Voice agent**

- [ ] Before the voice runs, estimate minutes: scenarios × average call length × 2 (both legs use Bolna). Check that against the credits left.
- [ ] Run every scam and genuine scenario as a real call with D. Fix prompt bugs the runs expose.
- [ ] Rehearse and record the demo call: teammate scammer, agent plays along, family gets the alert with the UPI ID.

**B · Backend and intel**

- [ ] Fix the bugs the voice runs expose.
- [ ] Analyse extraction misses: which digits and phrases speech-to-text garbles.
- [ ] Keep the backend up and backed up through the runs and the recording.

**C · Phone and family**

- [ ] Run genuine-call tests with 5 to 10 elderly users, recording consent first. Log every false positive.
- [ ] Finalise the carrier results: carrier, mode, pass or fail, caller number kept.
- [ ] Set up the demo phone so the alert and the dashboard are on screen during the recording.

**D · Detection and eval**

- [ ] Run the metrics script on the voice runs. Report measured numbers only.
- [ ] Draft the submission text under our wording rules. Switch to basic-mode-only wording if Gate 1 was no-go. Say openly that demo scam calls are role-played or simulated.
- [ ] Add a short note on DPDP Act obligations beyond a pilot.
- [ ] Edit the demo video on Thursday.

**Exit test (every line passes before Friday):**

- [ ] T-VOICE full run: every scenario called once on the real number, with the reliability checks at 100%.
- [ ] Metrics come from the T-MET-tested script and are copied into the sheet from its output file.
- [ ] T-PILOT: at least 5 participants and 15 genuine calls, with consent recorded before any call for every participant.
- [ ] The T-CARRIER Sprint 4 re-check is done for every carrier we'll name.
- [ ] T-DEMO passes. The final video is exported, and the backup recording is saved.
- [ ] T-CLAIM has had a first pass on the draft submission.

## Submission · Fri Oct 30 – Sat Oct 31

We submit on the evening of Oct 30, 2026. Saturday is for emergencies only.

- [ ] Whole team: check the submission text, README and video against the Sprint 3 claims list. Every number must come from Sprint 4.
- [ ] D: confirm the README no longer names AMD Slingshot before the repo link is shared.
- [ ] D: submit Friday evening and post the confirmation in the team chat.

**Exit test (every line passes before we press submit):**

- [ ] T-CLAIM passes on the final text, signed off by two reviewers.
- [ ] T-PRIV passes, and only then is the repo made public.
- [ ] The submission confirmation is saved as a screenshot in the team chat.

## Risks and fallbacks

| Risk | Watched by | Fallback |
| --- | --- | --- |
| Inbound number delayed by KYC | A, checked daily from Oct 16 | Develop on Bolna test calls; ask the Slack for a pre-provisioned number; the demo can use a direct dial with no forwarding |
| App rejection doesn't trigger forwarding | C, Gate 1 on Oct 20 | Basic mode only; C moves to guides and the dashboard; D swaps the wording |
| Jio won't forward to our number | C, Tests 3 and 4 | Get a mobile-series number; claim only the carriers we verified |
| Caller number lost on VoLTE forwarding | C, Test 3 | Count it as a fail for that carrier |
| Credits run short | A | Iterate in the text harness; save voice runs for Sprint 4 |
| Tool calls leave dead air | A | In-character filler lines; a fast classifier; keep screening if a tool times out |
| Speech-to-text garbles digits | B | The "say it slowly" persona habit; post-call normalizer and LLM cleanup |
| Agent gives out real details | D | Bait comes only from the backend; red-team scenarios must pass before the freeze |
| Nobody writes Kotlin | Whole team, kickoff | Drop app mode on day 1; C starts on basic mode and family outputs |

## Working agreements

- Work on short branches per lane, merged into the voice branch by pull request, with one reviewer from another lane.
- Prompts live in `prompts/` as the single copy. Bolna and the text harness both use those files.
- Hold a 15-minute standup at the same time every day. Each lane says what it's blocked on first.
- On each sprint's last evening, run a 30-minute live demo of the whole call flow. That demo is the sprint's exit check.
- Keep the carrier results and metrics in one shared sheet that everyone can read.

---

# Test suites

Every component has a suite with written cases and a hard pass bar, and a component is done only when its suite passes. The sprint exit tests above cite these suite IDs.

## How the suites run

Cheap layers run on every pull request and block the merge. Expensive layers (real calls, real phones, real people) block the sprint exit instead.

| Layer | Tool | Runs when | Blocks |
| --- | --- | --- | --- |
| Unit | pytest for the backend, JUnit for Android | Every pull request, in GitHub Actions | The merge |
| Contract | pytest with jsonschema against `contracts/` | Every pull request | The merge |
| Integration | pytest with `mock_bolna.py` and a throwaway SQLite file | Every pull request | The merge |
| Conversation (text mode) | The harness, using the same prompt files and LLM as Bolna | Any pull request touching `prompts/` or the classifier, plus nightly | The merge, for hard checks; rates are logged |
| Voice end to end | The scammer agent calling the real number | A 5-scenario smoke set after each prompt merge from Sprint 2; the full set in Sprint 4 | The sprint exit |
| Field | Phones, SIMs, real people, the result sheet | When the sprint plan schedules it | The sprint exit |

**Rules for every suite**

- LLM output varies, so every LLM case runs 3 times. A hard check passes only if all 3 runs pass.
- Model names, versions and temperature are pinned in config and saved with every result.
- A bug found in a higher layer gets a regression case in the lowest layer that could have caught it.
- Results outside CI go in the shared sheet: date, commit, suite ID, pass or fail, the numbers, who ran it.

## Suite index

29 suites cover every component in the plan. "First needed" is the sprint whose exit test first cites the suite.

| ID | What it tests | Owner | Layer | First needed |
| --- | --- | --- | --- | --- |
| T-CONTRACT | Every interface between lanes | B | Contract | Sprint 0 |
| T-STT | Speech-to-text choice for Hindi and English | A | Field (recorded audio) | Sprint 1 |
| T-CONV | Agent behaviour: screening, switch, persona, bait, language, speech fit | A | Conversation | Sprint 1 |
| T-LAT | Response time on real calls | A | Voice | Sprint 2 |
| T-SCAM | Scammer agent says its planted details and follows the scenario | A | Voice | Sprint 3 |
| T-VOICE | Whole call path on the real number | A with D | Voice | Sprint 2 (smoke), Sprint 4 (full) |
| T-NORM | Spoken-number normalizer | B | Unit | Sprint 1 |
| T-EXT | Rule-based extractor on transcripts | B | Unit | Sprint 1 |
| T-CLEAN | Post-call LLM cleanup and summary | B | Integration (LLM) | Sprint 2 |
| T-TOOLS | `switch_to_honeypot`, `log_intel` and the `classify_caller` route | B | Unit and contract | Sprint 1 |
| T-HOOK | Webhook, CallRecord store, `call.finalized` | B | Integration | Sprint 1 |
| T-API | CallRecord read API | B | Integration | Sprint 2 |
| T-RPT | 1930 report generator | B | Unit (golden files) | Sprint 3 |
| T-POST | Reflection and enrichment after the call | B | Integration | Sprint 3 |
| T-HOST | Deployed backend smoke test | B | Integration | Sprint 0 |
| T-AND | Android screening app | C | Unit and field | Sprint 1 |
| T-CARRIER | Carrier forwarding, Tests 1 to 4 | C | Field | Sprint 0 |
| T-XFER | Genuine-caller transfer in app mode | C with A | Field | Sprint 2 |
| T-SETUP | Setup guides | C | Field | Sprint 2 |
| T-ALERT | Family alerts | C | Integration | Sprint 1 |
| T-DASH | Family dashboard | C | Integration and manual | Sprint 2 |
| T-PILOT | Genuine calls with elderly users | C | Field | Sprint 4 |
| T-CLS | `classify_caller` accuracy, latency, stability | D | Conversation | Sprint 1 |
| T-SCN | Scenario file checks | D | Unit | Sprint 1 |
| T-HARN | Harness catches a broken agent | D | Unit | Sprint 1 |
| T-MET | Metrics script arithmetic | D | Unit | Sprint 3 |
| T-PRIV | Secrets, access control, recordings of real people | B with C | Unit and manual | Sprint 0 |
| T-CLAIM | Every claim backed by evidence | D | Manual | Sprint 4 |
| T-DEMO | Demo dry-runs | A | Field | Sprint 4 |

## Shared suite

### T-CONTRACT · Interfaces between lanes

Owner B · contract layer · `contracts/*.schema.json` and `tests/contract/` · every pull request

There is one JSON Schema per interface: each tool's request and response, the webhook payload, CallRecord, and `call.finalized`. Every producer and every consumer is tested against the same file.

- Backend responses for all three tools validate against their response schemas, from the Sprint 0 stubs onward.
- Every fixture in `tests/fixtures/` validates against the webhook schema.
- A script compares the tool definitions exported to `bolna/` with the request schemas. Parameter names and types must match exactly.
- The first real Bolna payload is saved as a fixture. If it fails the schema, the schema is fixed and every fixture is regenerated the same day.
- CallRecords returned by the read API validate against the CallRecord schema.
- A request missing a required field gets a 422 that names the field.
- Each schema carries a version number. CI fails if a schema changes without a version bump.

**Pass bar:** 100% green on every pull request. A breaking change merges only when every consumer's suite passes in the same pull request.

## Lane A · Voice agent

### T-STT · Speech-to-text bake-off

Owner A · field (recorded audio) · `evaluation/stt/` · once in Sprint 1, and again if the provider changes

- Record 20 clips per language from at least 3 speakers. Play each over a real phone call, so the audio has phone-line quality.
- Per language: 8 clips with phone numbers, 4 with UPI IDs, 4 with account numbers or IFSC codes, and 4 ordinary sentences. Record 5 of the 20 over background noise such as a TV or traffic.
- Hand-write a reference transcript for each clip.
- For every speech-to-text option Bolna offers for the language, compute word error rate and digit accuracy. Digit accuracy is the share of digit strings transcribed exactly after normalization.

**Pass bar:** the choice is written into the plan with both numbers for every option and language. Pick the highest digit accuracy, unless its word error rate is more than 10 points worse.

### T-CONV · Agent conversation suite (text mode)

Owner A · conversation · `evaluation/conversation/` · pull requests touching `prompts/`, plus nightly

Every scam, genuine and red-team scenario runs through the harness 3 times, in Hindi and in English.

| Hard check (zero violations) | How it is checked |
| --- | --- |
| Bait only | Every number, UPI ID, account, OTP or Aadhaar-like string the agent says is on the approved bait list (regex scan) |
| Speech fit | No markdown, emoji, bullet characters or links in agent turns, and no turn over 40 words |
| Language | A language detector on each agent turn matches the scenario language. Hindi-English mixing counts as valid |
| Tool order | `switch_to_honeypot` is never called before `classify_caller` returns scam |
| Persona consistency | Persona name, age, city and bait details never change within a call (string match against the persona file) |
| Screening opener | Within its first 2 turns, the agent asks who is calling and why |

| Rate check | Bar, per language |
| --- | --- |
| Switch to honeypot within 2 agent turns of a scam verdict | 95% of scam runs |
| Agent does not end a scam call before the scammer does | 95% of scam runs |
| Message from a genuine caller has name, callback number and reason | 95% of genuine runs |
| Agent asks the scammer to repeat a number slowly at least once | 80% of scam runs where a number was given |

**Pass bar:** every hard check at zero violations, and every rate check at its bar, in both languages.

### T-LAT · Response time

Owner A · voice · Bolna call logs and recordings · 10 calls in Sprint 2, 20 calls before the freeze

- On every turn, measure the time from the end of the caller's speech to the start of agent audio.
- On tool-call turns, measure the time to the first filler line instead.
- Use a half-scam, half-genuine mix across both languages.

**Pass bar:** p50 at or under 1.5 s and p95 at or under 2.5 s on normal turns. Filler audio starts within 1.0 s on tool turns. No silence anywhere lasts over 4 s. These are quality bars: if Sprint 2's first measurement shows the stack can't reach them, the team resets them at that demo.

### T-SCAM · Scammer agent

Owner A · voice · `bolna/scammer_agent.json` and `evaluation/scenarios/` · after every change to the scammer prompt

- Run each scam scenario twice against a dummy receiver that only keeps the scammer talking, and once against GuardianLine.
- From each transcript, check that the planted UPI ID or account was spoken in full.
- Check scenario fidelity with an LLM judge and a written rubric, 3 runs per call.

**Pass bar:** planted details spoken in 95% of calls, and scenario fidelity at 90%. Below this, the extraction metric means nothing.

### T-VOICE · Whole call path on the real number

Owner A with D · voice · `evaluation/voice/` · a 5-call smoke set after each prompt merge from Sprint 2 (2 Hindi scam, 1 English scam, 1 genuine, 1 red-team); the full set once in Sprint 4

After each hang-up, a script checks the CallRecord:

- It exists within 60 s of hang-up, with the caller number filled in.
- The verdict matches the scenario label.
- Every planted UPI ID or account appears exactly in the extracted intel.
- For a scam verdict, the family alert arrives within 2 minutes and its report link opens.
- For a genuine call, a message was taken (basic mode) or the call was transferred (app mode).
- The transcript passes the T-CONV bait-only check.

**Pass bar:** the reliability checks (record exists, alert for every scam verdict, no bait leak) hold on 100% of calls. Quality bars: detection at least 90%, false positives at most 10% on simulated genuine calls, extraction accuracy at least 70%.

## Lane B · Backend and intel

### T-NORM · Spoken-number normalizer

Owner B · unit · `tests/unit/test_normalizer.py` with cases in `tests/data/spoken_numbers.yaml` · every pull request

The corpus holds at least 150 cases: 60 or more each for English and Hindi (including Hinglish), plus 30 cases that must come out unchanged.

| Group | Example input | Expected |
| --- | --- | --- |
| English digit words | "nine eight four five zero" | `98450` |
| Repeats | "double five triple zero" | `55000` |
| "Oh" for zero | "nine oh one" | `901` |
| Hindi words, both scripts | "nau aath chaar", "नौ आठ चार" | `984` |
| Hinglish mixed digits | "nine आठ चार five zero", "double नौ five" | `98450`, `995` |
| Native digits | "९८४" | `984` |
| Digits mixed with words | "98 four 5" | `9845` |
| UPI handles | "ramesh at the rate okaxis", "ramesh at rate ok axis" | `ramesh@okaxis` |
| Separators | "ramesh dot kumar underscore one" | `ramesh.kumar_1` |
| Spelled IFSC | "S B I N zero zero zero one two three four" | `SBIN0001234` |
| Amount beside a number (unchanged) | "send five thousand to nine eight…" | The amount never merges into the phone number |
| Time (unchanged) | "call at ten thirty" | Not joined to any number |

**Pass bar:** 100% of corpus cases pass, because the normalizer is deterministic. A failing case is a bug, or it moves to a known-limits list reviewed at the sprint demo. It runs in under 50 ms on a 10-minute transcript.

### T-EXT · Rule-based extractor

Owner B · unit · `tests/unit/test_extractor.py` · every pull request

The labeled set holds at least 60 normalized transcripts with speaker turns: the fixtures plus harness outputs, labeled by hand with the expected entities.

- UPI handles in common forms, such as `name@okaxis`, `9876543210@ybl` and `name@paytm`.
- Phone numbers as `+91 98765 43210`, `098765 43210` and `9876543210`. A 10-digit string starting with 0 to 5 is rejected.
- Account numbers of 9 to 18 digits, IFSC (4 letters, a 0, 6 letters or digits), PAN (5 letters, 4 digits, 1 letter), and links.
- Negatives: a 4- to 6-digit OTP is not an account, an amount is not an account, a date is not a phone number.
- Speaker attribution: anything the agent said, including bait, is never extracted as scammer intel.
- Repeats merge: a UPI ID said 3 times becomes one entity with a count of 3.

**Pass bar:** for each entity type, precision of at least 0.95 and recall of at least 0.90 on the labeled set. Zero bait values extracted as scammer intel.

### T-CLEAN · Post-call LLM cleanup and summary

Owner B · integration (LLM) · `tests/llm/test_cleanup.py` · pull requests touching the cleanup step, plus nightly

The set holds 30 hard transcripts: digits split across turns, a number corrected mid-call ("no, the last digit is seven"), speech-to-text slips ("okay axis"), `log_intel` values that disagree with the transcript, and calls with no intel at all.

- The output validates against the CallRecord intel schema.
- Grounding: the LLM cites the turns it used for every value. A validator checks that those turns contain the value after normalization.
- Every value passes its format check (UPI, IFSC, phone, PAN).
- Where the transcript corrects a number, the corrected value wins.
- The summary is at most 80 words, states the verdict and the scam type, and contains no detail missing from the intel.
- A call with no intel produces empty intel.

**Pass bar:** zero ungrounded values across 90 runs (30 transcripts, 3 runs each); this is a reliability bar. Schema and format checks pass 100%. Corrections come out right in at least 90% of correction runs.

### T-TOOLS · Tool endpoints

Owner B · unit and contract · `tests/unit/test_tools.py` · every pull request

- `switch_to_honeypot` returns a persona and bait for the requested language. An unknown language falls back to Hindi. A second call with the same call ID returns the same persona.
- Every bait value served is on the approved bait list. Two people review that list before Sprint 1 ends, and no value on it may belong to a real person.
- `log_intel` stores both the value as heard and its normalized form. An unparseable value is stored with a flag, never rejected, so no evidence is lost mid-call.
- `log_intel` for a call ID with no record yet creates a pending record, which the webhook merges later.
- The `classify_caller` route returns "unsure" if the classifier takes over 1.5 s, so the agent keeps screening instead of hitting an error.
- On all three tools, a missing call ID returns a 422, and no response ever contains a stack trace.
- Load: send 100 sequential requests to the deployed URL.

**Pass bar:** every case green. p95 at or under 300 ms for `switch_to_honeypot` and `log_intel` under that load.

### T-HOOK · Webhook, CallRecord store and `call.finalized`

Owner B · integration · `tests/integration/test_webhook.py` with `mock_bolna.py` · every pull request

- Each of the 6 fixtures produces exactly one CallRecord with every required field.
- The same payload delivered twice still makes one record, and `call.finalized` fires once.
- `log_intel` captures that arrived before the webhook are merged into the record.
- A malformed payload gets a 400, is logged with its call ID, and the server keeps running.
- A missing caller number keeps the record, with the number left empty and a flag for the carrier results.
- A 60-minute transcript: the webhook still answers in under 1 s (post-call work runs in the background), and the record is final within 60 s.
- If the LLM cleanup is down, the record is saved with the rule-based intel, marked "cleanup pending", and retried.

**Pass bar:** every case green on every pull request.

### T-API · CallRecord read API

Owner B · integration · `tests/integration/test_api.py` · every pull request

- `/api/calls` lists newest first, 50 per page, and filters by verdict.
- `/api/calls/{id}` returns the full record, and an unknown ID returns a 404.
- A missing or wrong token gets a 401 on every route.
- Every response validates against the CallRecord schema.

**Pass bar:** every case green.

### T-RPT · 1930 report generator

Owner B · unit (golden files) · `tests/unit/test_report.py` with files in `tests/golden/` · every pull request

- Reports for 5 fixture CallRecords match their golden files exactly, with the generation time masked.
- Each report has: scammer number, every UPI ID, account and IFSC, call date and time in IST, duration, summary, and a line asking the family to check it before reporting.
- A field the call didn't capture prints "Not captured", never a blank or a guess.
- Once in Sprint 3, someone outside lane B walks through the National Cybercrime Reporting Portal form using only the report, stops before submitting, and lists any field the report couldn't supply. Never submit a test report.

**Pass bar:** golden tests green. The portal walk-through finds no missing field that the call actually captured.

### T-POST · Reflection and enrichment

Owner B · integration · `tests/integration/test_post.py` · every pull request

- Both tasks run on all 6 fixtures without errors.
- They start after the record is saved, and never delay the webhook response or the family alert.
- Each finishes within 60 s. A failure is logged and leaves the CallRecord intact.

**Pass bar:** every case green.

### T-HOST · Deployed backend smoke test

Owner B · integration · `scripts/smoke.sh` · after every deploy, and daily during voice runs

- `/health` returns 200 when called from a phone on mobile data, outside our network.
- Each tool endpoint answers a canned request with a schema-valid response.
- After a server restart, the public URL is unchanged and answers within 30 s.
- A Bolna test call shows up in the backend log with its call ID.

**Pass bar:** every check passes after every deploy. A failed smoke test means rolling back the deploy.

## Lane C · Phone and family

### T-AND · Android screening app

Owner C · unit and field · `android/app/src/test/` and `docs/tests/android.md` · unit tests on every pull request, field script on every new APK

Unit tests (JUnit) cover the decision function that takes a number, the contacts and the whitelist:

- A saved contact rings. The Bolna number rings. An unknown number is rejected.
- One number in different formats still matches its contact: `+91 98765 43210`, `09876543210`, `9876543210`, with spaces or dashes.
- A withheld number is rejected and goes to the agent.
- Emergency and helpline numbers (112, 100, 108, 1930) always ring.
- With an empty contact list, the app still runs and rejects every number.

Field script, on every demo phone:

1. Install the APK and grant the call-screening role. The app shows it is active.
2. A saved contact calls: the phone rings normally.
3. An unknown number calls: the phone doesn't ring, and the call reaches the agent.
4. The Bolna number calls: the phone rings.
5. Reboot, then repeat steps 2 and 3.
6. Force-stop the app, then repeat steps 2 and 3.
7. Turn on battery saver, then repeat steps 2 and 3.
8. Revoke the role: the app shows a warning and every call rings normally. When broken, the app must fail open.

Soak test: 24 hours on a teammate's own phone, with every incoming call logged.

**Pass bar:** unit tests 100%. The field script passes on every demo phone. The soak test shows zero blocked calls from saved contacts, which is a reliability bar.

### T-CARRIER · Carrier forwarding matrix

Owner C · field · carrier results sheet · Test 1 in Sprint 0, Tests 2 to 4 in Sprint 1, a full re-check in Sprint 4

For each carrier (Jio, Airtel, Vi), run each of the 4 tests 3 times. Log every attempt: date, phone model, Android version, VoLTE on or off, forwarding code, whether it forwarded, the caller number the receiver saw, and seconds to forward.

**Pass bar:** a cell passes when all 3 attempts forward and the original caller number arrives. A carrier is claimed for a mode only when that mode's deciding tests pass (Tests 2 and 3 for app mode, Test 4 for basic mode). The claim names the phone it was verified on, and the Sprint 4 re-check must pass again.

### T-XFER · Genuine-caller transfer (app mode only)

Owner C with A · field · results sheet · Sprint 2, and again before the freeze

- A teammate calls the parent's phone from an unknown number as a genuine caller. The agent asks the purpose and transfers.
- The parent's phone rings showing the Bolna number, the app lets it through, and the call connects with audio both ways.
- The parent declines the transferred call: the caller is offered a message, and the call doesn't bounce back to the agent.
- Log what happens when the parent is already on another call.

**Pass bar:** 5 of 5 transfers connect with two-way audio, and zero loops in 5 declined transfers.

### T-SETUP · Setup guides

Owner C · field · `docs/setup/` · whenever a guide changes, and before the freeze

- A teammate who didn't write the guide follows it, timed and without help, on a phone they haven't set up before.
- Afterwards, `*#61#` (basic mode) or `*#67#` (app mode) shows the Bolna number.
- A test call (unanswered in basic mode, unknown in app mode) reaches the agent.
- The guide's undo steps bring normal calling back.

**Pass bar:** finished in 10 minutes or less with no help, forwarding confirmed, undo works. Each carrier's guide passes separately.

### T-ALERT · Family alerts

Owner C · integration · `tests/integration/test_alerts.py`, plus one live send · every pull request; the live send at every sprint demo

- A scam fixture sends exactly one WhatsApp or SMS message, with caller number, verdict, every captured UPI ID and account, and the report link.
- A genuine fixture in basic mode sends a "message taken" note, not a scam alert.
- A call finalized twice sends one alert.
- If Twilio errors, the send is retried 3 times with backoff and then logged. The webhook and the record are unaffected.
- The SMS version fits in 2 segments.
- Live: the message reaches a test phone within 2 minutes of hang-up.

**Pass bar:** every automated case green, and the live message arrives within 2 minutes at every sprint demo.

### T-DASH · Family dashboard

Owner C · integration and manual · `tests/integration/test_dashboard.py` and a manual checklist · automated on every pull request, manual at each sprint demo

- Automated: the page returns 200 with a valid token and 401 without one, and it lists a fixture call by caller number and verdict.
- Manual, on a phone browser: the last 50 calls load in under 2 s.
- The call detail shows verdict, transcript, extracted intel and a report download.
- With no calls, the empty state makes sense.
- At 360 px wide, everything is readable with no sideways scrolling.

**Pass bar:** automated checks green, and the manual checklist passes on two different phone browsers.

### T-PILOT · Genuine calls with elderly users

Owner C · field · consent forms and the results sheet · Sprint 4

- 5 to 10 elderly participants. Each gives consent in their own language (recording, how data is used, withdrawing at any time) before their phone is set up.
- Each participant gets at least 3 genuine calls from teammates playing a clinic, a delivery and a relative on a new number.
- Log for every call: verdict, whether the caller got through or left a message, and anything that confused the participant.
- Afterwards, ask each participant two questions: was anything confusing, and would you keep it on?
- Recordings are deleted after analysis unless the participant agreed otherwise.

**Pass bar:** consent recorded for 100% of participants before any call. At least 5 participants and 15 genuine calls. False positives reported exactly as measured.

## Lane D · Detection and eval

### T-CLS · `classify_caller`

Owner D · conversation · `evaluation/classifier/` with `classifier_set.jsonl` · pull requests touching the classifier, plus nightly

The set cuts every scam and genuine scenario at caller turns 2, 4 and 6, in Hindi, English and Hinglish mixed speech. It adds hard cases:

- Paired openings that differ only in the ask: a relative on a new number, and a bank calling about a transaction. The genuine version never asks for money, an OTP or a PIN; the scam version does.
- A courier confirming a delivery address.
- Words that fooled the old keyword detector in genuine calls: "namaste", "PIN code", "job interview".

Each case runs 3 times. The suite records the verdict at each cut, the latency measured from the backend host to the production model, and whether the JSON is valid.

**Pass bar at the freeze:** scam recall of at least 90% by turn 6. False positives at most 5%, counting a genuine conversation flagged scam at any cut. p95 latency at or under 1.0 s. JSON valid 100%. Verdicts flip between runs in at most 5% of cases.

**Pass bar at the end of Sprint 2:** recall of at least 85% and false positives at most 10%. From then on, no pull request may lower recall or raise false positives against the baseline saved in `evaluation/classifier/baseline.json`.

### T-SCN · Scenario file checks

Owner D · unit · `tests/unit/test_scenarios.py` · every pull request

- Every scenario validates against the scenario schema: ID, language, type (scam, genuine or red-team), caller script, planted details, expected verdict, maximum turns.
- Every scam scenario plants at least one UPI ID or account, and no genuine scenario plants any.
- No planted value matches a bait value, so extraction scoring is never ambiguous.
- IDs are unique, and every scam type has a Hindi and an English version.
- The digital-arrest scenario exists.

**Pass bar:** 100% green.

### T-HARN · Harness catches a broken agent

Owner D · unit · `tests/unit/test_harness.py` · every pull request touching the harness

- Three deliberately broken agent prompts must fail: one that never switches to honeypot must score 0% detection, one that flags every caller must score 100% false positives, and one that reads out an invented account number must trip the bait-only check.
- Output rows match the CallRecord CSV format the metrics script reads.
- Every run saves its prompt version, model and settings beside its results.

**Pass bar:** all three broken prompts caught, and the format check green. If the harness misses one, none of its numbers can be trusted.

### T-MET · Metrics script

Owner D · unit · `tests/unit/test_metrics.py` · every pull request

- A hand-built CSV of 6 calls has hand-computed answers for all five metrics. The script must match them exactly.
- With zero genuine calls, the false-positive rate prints "not measured", not 0% and not a crash.
- Calls with no planted details are left out of the extraction-accuracy denominator.
- Scammer time counts from the honeypot switch, not from the start of the call.
- Carrier coverage reads the carrier sheet export and counts only passing cells.

**Pass bar:** 100% green. Numbers in the submission are copied only from this script's output file.

## Release suites

### T-PRIV · Secrets, access control and real people's data

Owner B with C · unit and manual · secrets scan in CI plus a checklist · the scan on every pull request, the checklist before the repo goes public

- A secrets scanner such as gitleaks runs in CI over the full git history. Any API key, token or `.env` file fails the build.
- Every backend route except `/health` requires the token. The routes Bolna calls check a shared secret that Bolna sends, as a header or a parameter, whichever Bolna supports.
- No real person's phone number, transcript or recording appears in the repo, fixtures or screenshots. Fixtures use invented numbers.
- Pilot recordings stay in the team's private storage and are deleted on the date the consent form states.
- Logs mask all but the last 4 digits of caller numbers. CallRecords keep full numbers, because the report needs them.

**Pass bar:** the scan is green on the full history, and two people sign off the checklist before the repo is made public.

### T-CLAIM · Claims audit

Owner D · manual · `submission/claims.md` · Sprint 4, and again on submission day

- List every sentence in the submission text and README that states a fact about what GuardianLine does or has achieved.
- Map each one to evidence: a suite result row (ID and date), a recording, or a line in the metrics output file.
- Check the wording rules: no earlier hackathon named, no unmeasured metric, mule-account action only as long-term vision, demo scam calls described as role-played or simulated, and basic-mode-only wording if Gate 1 was no-go.

**Pass bar:** 100% of factual sentences mapped. A sentence without evidence is cut or rewritten. Two reviewers from outside lane D sign off.

### T-DEMO · Demo dry-runs

Owner A · field · `submission/demo.md` · 3 dry-runs before Oct 28, then the recording

- Run the full script live: the teammate scammer calls, the agent screens and switches, the scammer gives a UPI ID, the family phone gets the alert with that UPI ID, then the dashboard and report are shown.
- Time each run and note every stumble.
- Keep the best dry-run recording as a backup.

**Pass bar:** 3 dry-runs in a row with no failure that would force a retake, and the alert visible on camera within 2 minutes. The backup recording is saved before the final take.
