# Voice-run credit budget (Lane A)

Rate seen on the dashboard (Oct 17): **$0.060 per minute** per agent leg.
Scammer-agent tests use **two legs** (scammer + Rakshak), so they cost double.

**Formula:** minutes = scenarios × average call length × legs. Cost = minutes × $0.06.

| Run | Scenarios | Avg length | Legs | Minutes | Cost |
| --- | --- | --- | --- | --- | --- |
| T-VOICE smoke set (per prompt merge, from Sprint 2) | 5 | 3 min | 2 | 30 | $1.80 |
| T-SCAM fidelity (each scam scenario × 3) | 6 × 3 = 18 | 3 min | 2 | 108 | $6.48 |
| T-LAT (Sprint 2) | 10 | 2 min | 1 | 20 | $1.20 |
| T-LAT (before freeze) | 20 | 2 min | 1 | 40 | $2.40 |
| T-VOICE full run (Sprint 4) | ~20 | 3 min | 2 | 120 | $7.20 |
| Demo rehearsal + recording | 5 | 3 min | 1 | 15 | $0.90 |
| **Total (one smoke set)** | | | | **333** | **≈ $20** |

Each extra smoke set adds $1.80. Scenario counts are estimates; update when D freezes the eval set.

**Current balance:** about $4.85 in the rakshak-v0 account (about 81 min). This does not cover Sprint 4.
- Needs Bolna hackathon credits (support emailed Oct 17) or a team top-up.
- Until then, iterate prompts in D's text harness, and save voice runs for Sprint 4 (plan fallback).
- Trial plan: outbound calls only to verified numbers, so the scammer agent cannot call Rakshak until the account is upgraded.
