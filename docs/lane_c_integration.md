# Lane C integration notes (for lanes A and B)

## 1. Wiring into lane B's backend

Lane B owns `app/main.py`, the CallRecord store (`app/voice/store.py`), the contracts and the 1930 report (`app/voice/report.py`). Lane C doesn't keep copies of any of them. After lane C is merged, B's `app/main.py` needs these two lines:

```python
from app.core.lane_c import install
install(app)
```

`install()` does four things:

- **Mounts the family dashboard and event route.** These are `/dashboard`, `/dashboard/calls/{id}`, `/dashboard/report/{id}` and `POST /events/call_finalized`.
- **Points the dashboard at B's SQLite store** through a read-only adapter.
- **Renders `/dashboard/report/{id}` with B's `generate_1930_report`.** It's the same report that B's golden files test.
- **Subscribes family alerts to `register_call_finalized_listener`.** The listener queues the send on a thread pool, so B's webhook never waits on Twilio.

The event Lane C consumes is B's flat `contracts/call_finalized.schema.json`. The listener loads the full CallRecord with `get_call_record` so the WhatsApp alert can include the summary.

## 2. Settings Lane C reads

| Variable | Purpose |
| --- | --- |
| `FAMILY_ALERT_TO` | Required. Comma-separated family numbers. Alerts are disabled if unset. |
| `ALERT_CHANNEL` | `whatsapp` (default) or `sms` |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` / `TWILIO_WHATSAPP_FROM` | Twilio sender |
| `ALERT_DB_PATH` | SQLite file for alert idempotency (default `data/alerts.db`) |
| `REPORT_BASE_URL` | Public base for report links in alerts, e.g. `https://<host>/dashboard/report` |
| `REPORT_SIGNING_SECRET` | Signs the per-call report links in alerts (falls back to `GUARDIAN_DASHBOARD_TOKEN`) |
| `GUARDIAN_DASHBOARD_TOKEN` | Family dashboard login. Exchanged for an HttpOnly cookie on first use. |
| `GUARDIAN_EVENTS_TOKEN` | Bearer token for `POST /events/call_finalized`. The route returns 503 if unset. |

## 3. Delivery in India (read before the demo)

- **SMS:** A2P SMS to Indian numbers from a Twilio US number needs TRAI DLT registration (entity, header and template). Without it, messages are filtered or arrive as international. For the demo, use WhatsApp, or an Indian SMS provider with DLT.
- **WhatsApp sandbox:**
  - It only delivers to numbers that have sent the sandbox join code. Join the demo phone in advance.
  - Messages that GuardianLine starts outside a 24-hour session need an approved template. A family member who hasn't messaged the sandbox in 24 hours won't get the alert.

## 4. Open questions for lane A (must be settled before T-XFER)

1. **Transfer caller ID.** When Bolna transfers a genuine caller to the parent's phone, which number does the handset see: the Bolna gateway number (whitelisted by the app) or the original caller's number (screened as unknown)?
2. **Transfer loop.** If the parent declines or is busy, the carrier's `**67*` busy-forward sends that leg straight back to Bolna. The agent needs a rule for an inbound call that is its own transfer coming back: take a message, never transfer again.
3. **Naming.** The Android app, dashboard and alerts say **GuardianLine**. Lane A's agent config and prompt say **Rakshak**. Pick one before the demo.
