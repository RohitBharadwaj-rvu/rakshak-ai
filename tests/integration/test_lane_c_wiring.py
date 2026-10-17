"""
Lane C wiring: Lane B's call.finalized bus and store, event route auth, signed family
links, cookie login, and SMS link preservation.
"""

import re
import time
import types
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import gui, lane_c
from app.notify import listener
from app.notify.alerts import (
    AlertChannel,
    AlertConfig,
    AlertStatus,
    FamilyAlertDispatcher,
    PersistentAlertStore,
    count_septets,
    format_alert_message,
    generate_report_signature,
    is_gsm7,
)

TOKEN = "dash_token_for_tests_0123456789"

B_RECORD = {
    "call_id": "call_b_001",
    "caller_number": "+919876543210",
    "start_time": "2026-10-17T02:00:00+00:00",
    "duration": 120.0,
    "verdict": "scam",
    "summary": "Caller claimed to be CBI and demanded a deposit.",
    "transcript": [{"role": "user", "content": "CBI se bol raha hoon"}],
    "extracted_intel": {
        "upi_ids": ["cbi.officer.verma@okaxis"],
        "phone_numbers": [],
        "bank_accounts": [],
        "ifsc_codes": [],
        "pan_numbers": [],
        "links": [],
        "entity_counts": {},
        "mid_call_logs": [],
    },
    "report_link": "/api/calls/call_b_001/report",
}

B_EVENT = {
    "event": "call.finalized",
    "call_id": "call_b_001",
    "verdict": "scam",
    "caller_number": "+919876543210",
    "timestamp": "2026-10-17T02:02:00+00:00",
    "report_link": "/api/calls/call_b_001/report",
    "extracted_intel": B_RECORD["extracted_intel"],
}


def fake_lane_b_store(tmp_path):
    """Stand-in for app.voice.store with the functions lane_c uses."""
    import sqlite3

    db = str(tmp_path / "calls.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE call_records (call_id TEXT PRIMARY KEY, verdict TEXT)")
    conn.execute("INSERT INTO call_records VALUES (?, ?)", (B_RECORD["call_id"], "scam"))
    conn.commit()
    conn.close()
    listeners = []
    return types.SimpleNamespace(
        init_db=lambda: None,
        get_db_path=lambda: db,
        get_call_record=lambda cid: dict(B_RECORD) if cid == B_RECORD["call_id"] else None,
        list_call_records=lambda limit=50, verdict=None, offset=0: [dict(B_RECORD)][offset:offset + limit],
        register_call_finalized_listener=listeners.append,
        listeners=listeners,
    )


@pytest.fixture(autouse=True)
def reset_lane_c_state():
    yield
    gui.set_dashboard_store(gui.InMemoryCallStore())
    gui.set_report_renderer(None)
    listener.set_record_loader(None)
    listener.set_default_dispatcher(None)


@pytest.fixture
def mock_dispatcher():
    client = MagicMock()
    client.messages.create.return_value.sid = "SM_test"
    config = AlertConfig(to_phone="+919876500001", channel=AlertChannel.WHATSAPP, signing_secret="s")
    return FamilyAlertDispatcher(config=config, twilio_client=client, store=PersistentAlertStore(":memory:"))


class TestLaneBEvents:
    def test_flat_lane_b_event_sends_alert(self, mock_dispatcher):
        result = listener.handle_call_finalized_event(dict(B_EVENT), dispatcher=mock_dispatcher)
        assert result.status == AlertStatus.SENT
        body = mock_dispatcher.twilio_client.messages.create.call_args.kwargs["body"]
        assert "cbi.officer.verma@okaxis" in body

    def test_full_record_is_loaded_from_store_for_summary(self, mock_dispatcher):
        listener.set_record_loader(lambda cid: dict(B_RECORD))
        listener.handle_call_finalized_event(dict(B_EVENT), dispatcher=mock_dispatcher)
        body = mock_dispatcher.twilio_client.messages.create.call_args.kwargs["body"]
        assert B_RECORD["summary"] in body

    def test_missing_recipient_disables_alerts_instead_of_using_a_default(self, monkeypatch):
        monkeypatch.delenv("FAMILY_ALERT_TO", raising=False)
        result = listener.handle_call_finalized_event(dict(B_EVENT))
        assert result.status == AlertStatus.FAILED
        assert result.reason == "ALERTS_NOT_CONFIGURED"

    def test_install_subscribes_to_lane_b_bus_and_reads_its_store(self, tmp_path, monkeypatch, mock_dispatcher):
        store = fake_lane_b_store(tmp_path)
        voice_pkg = types.ModuleType("app.voice")
        report_mod = types.ModuleType("app.voice.report")
        report_mod.generate_1930_report = lambda rec: f"LANE B REPORT {rec['call_id']}"
        voice_pkg.store = store
        voice_pkg.report = report_mod
        monkeypatch.setitem(__import__("sys").modules, "app.voice", voice_pkg)
        monkeypatch.setitem(__import__("sys").modules, "app.voice.store", store)
        monkeypatch.setitem(__import__("sys").modules, "app.voice.report", report_mod)
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TOKEN)

        app = FastAPI()
        assert lane_c.install(app) is True
        assert store.listeners == [listener.on_call_finalized]

        # Lane B fires the event; the alert is sent off the request thread
        listener.set_default_dispatcher(mock_dispatcher)
        store.listeners[0](dict(B_EVENT))
        from app.notify.alerts import _THREAD_POOL
        _THREAD_POOL.submit(lambda: None).result(timeout=5)
        for _ in range(50):
            if mock_dispatcher.twilio_client.messages.create.called:
                break
            time.sleep(0.05)
        assert mock_dispatcher.twilio_client.messages.create.called

        client = TestClient(app)
        headers = {"Authorization": f"Bearer {TOKEN}"}
        listing = client.get("/dashboard/api/calls", headers=headers)
        assert [c["call_id"] for c in listing.json()] == ["call_b_001"]
        report = client.get("/dashboard/report/call_b_001", headers=headers)
        assert report.text == "LANE B REPORT call_b_001"


class TestEventRouteAuth:
    @pytest.fixture
    def client(self):
        app = FastAPI()
        app.include_router(listener.router)
        return TestClient(app)

    def test_unset_token_refuses_events(self, client, monkeypatch):
        monkeypatch.delenv("GUARDIAN_EVENTS_TOKEN", raising=False)
        assert client.post("/events/call_finalized", json=B_EVENT).status_code == 503

    def test_wrong_or_missing_token_rejected(self, client, monkeypatch):
        monkeypatch.setenv("GUARDIAN_EVENTS_TOKEN", "events_secret")
        assert client.post("/events/call_finalized", json=B_EVENT).status_code == 401
        bad = client.post("/events/call_finalized", json=B_EVENT, headers={"Authorization": "Bearer nope"})
        assert bad.status_code == 401

    def test_valid_token_accepted(self, client, monkeypatch, mock_dispatcher):
        monkeypatch.setenv("GUARDIAN_EVENTS_TOKEN", "events_secret")
        listener.set_default_dispatcher(mock_dispatcher)
        resp = client.post("/events/call_finalized", json=B_EVENT, headers={"Authorization": "Bearer events_secret"})
        assert resp.status_code == 200
        assert mock_dispatcher.twilio_client.messages.create.called


class TestDashboardSessionsAndSignedLinks:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("GUARDIAN_DASHBOARD_TOKEN", TOKEN)
        monkeypatch.delenv("REPORT_SIGNING_SECRET", raising=False)
        store = gui.InMemoryCallStore()
        store.add_call(dict(B_RECORD))
        gui.set_dashboard_store(store)
        app = FastAPI()
        app.include_router(gui.router)
        return TestClient(app)

    def test_token_login_becomes_cookie_and_leaves_urls(self, client):
        first = client.get(f"/dashboard?token={TOKEN}", follow_redirects=False)
        assert first.status_code == 303
        assert "token=" not in first.headers["location"]
        assert "httponly" in first.headers["set-cookie"].lower()

        page = client.get("/dashboard")
        assert page.status_code == 200
        assert TOKEN not in page.text

    def test_signed_link_report_button_keeps_signature(self, client):
        exp = int(time.time()) + 3600
        sig = generate_report_signature("call_b_001", exp, TOKEN)
        detail = client.get(f"/dashboard/calls/call_b_001?exp={exp}&sig={sig}")
        assert detail.status_code == 200
        assert "Back to Overview" not in detail.text
        href = re.search(r'href="(/dashboard/report/[^"]+)"', detail.text).group(1).replace("&amp;", "&")
        assert f"sig={sig}" in href
        assert client.get(href).status_code == 200

    def test_dedicated_signing_secret_is_used(self, client, monkeypatch):
        monkeypatch.setenv("REPORT_SIGNING_SECRET", "separate_secret")
        exp = int(time.time()) + 3600
        old = generate_report_signature("call_b_001", exp, TOKEN)
        new = generate_report_signature("call_b_001", exp, "separate_secret")
        assert client.get(f"/dashboard/report/call_b_001?exp={exp}&sig={old}").status_code == 401
        assert client.get(f"/dashboard/report/call_b_001?exp={exp}&sig={new}").status_code == 200

    def test_unknown_verdict_filter_rejected(self, client):
        resp = client.get("/dashboard/api/calls?verdict=<script>", headers={"Authorization": f"Bearer {TOKEN}"})
        assert resp.status_code == 422


class TestSmsKeepsReportLink:
    def _link(self, msg):
        return re.search(r"Report: (\S+)$", msg).group(1)

    def test_hindi_intel_keeps_full_signed_link(self):
        rec = {"call_id": "call_scam_digital_arrest_001", "caller_number": "+919876543210", "verdict": "scam",
               "extracted_intel": {"upi_ids": ["रमेश@okaxis"]}}
        msg = format_alert_message(rec, AlertChannel.SMS, "https://guardianline-demo.example.org/dashboard/report",
                                   signing_secret="s")
        # Hindi intel forces UCS-2 (134 chars); if it can't fit beside the link it is dropped
        # (the report holds it) and the rest goes out as GSM-7. Either way: 2 segments, full link.
        assert (count_septets(msg) <= 306) if is_gsm7(msg) else (len(msg) <= 134)
        assert re.search(r"sig=[0-9a-f]{16}$", self._link(msg))

    def test_overlong_base_url_keeps_link_even_past_two_segments(self):
        rec = {"call_id": "c1", "caller_number": "+919999999999", "verdict": "scam",
               "extracted_intel": {"upi_ids": ["a@b"]}}
        base = "https://" + "x" * 300 + ".org/r"
        msg = format_alert_message(rec, AlertChannel.SMS, base, signing_secret="s")
        assert self._link(msg).startswith(base)
        assert re.search(r"sig=[0-9a-f]{16}$", msg)

    def test_gsm_message_within_two_segments(self):
        rec = {"call_id": "c1", "caller_number": "+919999999999", "verdict": "scam",
               "extracted_intel": {"upi_ids": [f"user{i}@okaxis" for i in range(40)]}}
        msg = format_alert_message(rec, AlertChannel.SMS, "https://demo.example.org/dashboard/report",
                                   signing_secret="s")
        assert count_septets(msg) <= 306
        assert "sig=" in self._link(msg)
