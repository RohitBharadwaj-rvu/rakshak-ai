import json
import logging
import os
import pytest
from unittest.mock import MagicMock

from app.notify.alerts import (
    AlertConfig,
    AlertChannel,
    AlertStatus,
    FamilyAlertDispatcher,
    PersistentAlertStore,
    TwilioRestException,
    count_septets,
    format_alert_message,
    is_gsm7,
    is_retryable_twilio_error,
    generate_report_signature,
    verify_report_signature,
    build_dispatcher_from_env,
)
from app.notify.listener import handle_call_finalized_event

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")


@pytest.fixture
def scam_record():
    with open(os.path.join(FIXTURES_DIR, "01_scam_digital_arrest.json"), "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "call_id": data["call_id"],
        "caller_number": data["caller_number"],
        "verdict": "scam",
        "duration": data["call_duration"],
        "extracted_intel": {
            "upi_ids": [data["metadata"]["planted_intel"]["upi_id"]],
            "phone_numbers": [data["metadata"]["planted_intel"]["phone_number"]],
            "bank_accounts": ["987654321098"],
            "ifsc_codes": ["SBIN0001234"],
            "links": ["https://mumbai-cyber-clearance.in/verify"],
        },
        "summary": "Scammer impersonated CBI officer alleging illegal drugs in Taiwan parcel.",
    }


@pytest.fixture
def genuine_record():
    with open(os.path.join(FIXTURES_DIR, "03_genuine_courier.json"), "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "call_id": data["call_id"],
        "caller_number": data["caller_number"],
        "verdict": "genuine",
        "duration": data["call_duration"],
        "extracted_intel": {},
        "summary": "Blue Dart delivery courier confirmed parcel drop.",
        "message": "Blue Dart courier dropped Amazon parcel with society guard.",
    }


@pytest.fixture
def alert_config():
    return AlertConfig(
        account_sid="AC_test_account_sid_123",
        auth_token="test_auth_token_secret",
        from_phone="+14155238886",
        to_phone="+919876500001, +919876500002",
        channel=AlertChannel.WHATSAPP,
        base_report_url="http://localhost:8000/dashboard/report",
        token="master_sec123",
        signing_secret="master_sec123",
    )


class TestAlertFormattingAndSegmentation:
    def test_septet_counting_and_gsm7_extension_chars(self):
        # Basic GSM-7 characters: 1 septet each
        basic = "Hello World 123"
        assert count_septets(basic) == len(basic)

        # Extended characters: 2 septets each
        # {}[]~|^€
        ext = "Test {braces} and [brackets] | ^ ~ €"
        # Each extension char costs 2
        ext_chars_count = sum(1 for c in ext if c in "{}[]~|^€")
        expected_septets = (len(ext) - ext_chars_count) + (ext_chars_count * 2)
        assert count_septets(ext) == expected_septets
        assert is_gsm7(ext)

    def test_scam_whatsapp_alert_contains_all_details_and_links(self, scam_record, alert_config):
        msg = format_alert_message(
            scam_record,
            AlertChannel.WHATSAPP,
            alert_config.base_report_url,
            signing_secret=alert_config.signing_secret,
        )
        assert "SCAM ALERT" in msg
        assert scam_record["caller_number"] in msg
        assert "cbi.officer.verma@okaxis" in msg
        assert "987654321098" in msg
        assert "SBIN0001234" in msg
        assert "https://mumbai-cyber-clearance.in/verify" in msg
        assert scam_record["call_id"] in msg
        # Master token MUST NOT appear in the URL
        assert "token=master_sec123" not in msg
        # Expiring signature params MUST appear instead
        assert "exp=" in msg and "sig=" in msg
        # Must include the signed Evidence Review link (/dashboard/calls/{call_id})
        assert f"/dashboard/calls/{scam_record['call_id']}?exp=" in msg


    def test_scam_sms_gsm7_strictly_within_two_segments_budget(self, scam_record, alert_config):
        msg = format_alert_message(
            scam_record,
            AlertChannel.SMS,
            alert_config.base_report_url,
            signing_secret=alert_config.signing_secret,
        )
        assert "[SUSPECTED SCAM]" in msg
        assert scam_record["caller_number"] in msg
        assert is_gsm7(msg)
        # Strict 2-segment ceiling is 306 septets
        septets = count_septets(msg)
        assert septets <= 306, f"GSM-7 SMS septets {septets} exceeded 306 limit"
        # Master token not leaked
        assert "token=" not in msg

    def test_scam_sms_with_worst_case_payload_and_long_url_stays_within_budget(self, alert_config):
        worst_case_record = {
            "call_id": "call_extremely_long_id_0123456789abcdef",
            "caller_number": "+919988776655",
            "verdict": "scam",
            "extracted_intel": {
                "upi_ids": ["verylongfraudulentid@icicibank", "anotherattackerid@axisbank"],
                "bank_accounts": ["1234567890123456", "9876543210987654"],
                "ifsc_codes": ["ICIC0001234", "UTIB0005678"],
                "phone_numbers": ["+919876543210", "+919123456789"],
                "links": ["https://phishing-portal.com/urgent-payment-gateway-resolve"],
            },
            "summary": "Attacker aggressively attempted to extract Aadhaar and immediate funds." * 3,
        }
        long_base_url = "https://prod-gateway-service.guardianline.ai/reports/v1/dossier"

        msg = format_alert_message(
            worst_case_record,
            AlertChannel.SMS,
            base_report_url=long_base_url,
            signing_secret="super_secret_signing_key_12345",
        )
        assert is_gsm7(msg)
        septets = count_septets(msg)
        assert septets <= 306, f"Worst-case SMS septets {septets} exceeded 306 limit"

    def test_hindi_unicode_sms_within_ucs2_two_segments(self, alert_config):
        hindi_record = {
            "call_id": "call_hi_001",
            "caller_number": "+919876543210",
            "verdict": "genuine",
            "message": "शर्मा जी का पार्सल गार्ड रूम में जमा कर दिया है। कृपया वापस कॉल करके पुष्टि कर लें धन्यवाद।",
        }
        msg = format_alert_message(hindi_record, AlertChannel.SMS, alert_config.base_report_url)
        assert not is_gsm7(msg), "Must be detected as Unicode"
        # UCS-2 2-segment ceiling is 134 characters
        assert len(msg) <= 134, f"UCS-2 SMS length {len(msg)} exceeded 134 characters"


class TestFamilyAlertDispatcher:
    def test_multi_recipient_dispatch(self, scam_record, alert_config):
        mock_client = MagicMock()
        mock_client.messages.create.return_value.sid = "SM_mock_sid_multi"

        store = PersistentAlertStore(":memory:")
        dispatcher = FamilyAlertDispatcher(config=alert_config, twilio_client=mock_client, store=store)
        result = dispatcher.dispatch(scam_record)

        assert result.status == AlertStatus.SENT
        # Alert was dispatched to both configured recipients
        assert mock_client.messages.create.call_count == 2
        recipients_called = [call.kwargs["to"] for call in mock_client.messages.create.call_args_list]
        assert "whatsapp:+919876500001" in recipients_called
        assert "whatsapp:+919876500002" in recipients_called

    @pytest.mark.parametrize("twilio_code", [63015, 21211, 21614, 63007])
    def test_whatsapp_sandbox_error_triggers_sms_fallback_with_status_sent(
        self, scam_record, alert_config, caplog, twilio_code
    ):
        caplog.set_level(logging.WARNING)
        single_config = (
            alert_config.model_copy(update={"to_phone": "+919876500001"})
            if hasattr(alert_config, "model_copy")
            else alert_config.copy(update={"to_phone": "+919876500001"})
        )

        sms_response = MagicMock()
        sms_response.sid = f"SM_fallback_{twilio_code}"

        def create_side_effect(**kwargs):
            if kwargs["to"].startswith("whatsapp:"):
                raise TwilioRestException(
                    status=400,
                    uri="/Messages",
                    msg=f"Twilio WhatsApp error {twilio_code}",
                    code=twilio_code,
                )
            return sms_response

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = create_side_effect

        store = PersistentAlertStore(":memory:")
        dispatcher = FamilyAlertDispatcher(config=single_config, twilio_client=mock_client, store=store)
        result = dispatcher.dispatch(scam_record)

        assert result.status == AlertStatus.SENT
        assert result.channel == AlertChannel.SMS
        assert result.message_sid == f"SM_fallback_{twilio_code}"
        assert mock_client.messages.create.call_count == 2
        sms_call = mock_client.messages.create.call_args_list[1]
        assert sms_call.kwargs["to"] == "+919876500001"
        assert not sms_call.kwargs["from_"].startswith("whatsapp:")
        assert "[SUSPECTED SCAM]" in sms_call.kwargs["body"]
        assert count_septets(sms_call.kwargs["body"]) <= 306
        assert any(r.levelname == "WARNING" and str(twilio_code) in r.message for r in caplog.records)

    def test_cross_instance_persistent_idempotency_with_two_phase_states(self, scam_record, alert_config, tmp_path):
        db_file = str(tmp_path / "alerts_idempotency.db")
        store1 = PersistentAlertStore(db_file)
        store2 = PersistentAlertStore(db_file)

        mock_client = MagicMock()
        mock_client.messages.create.return_value.sid = "SM_mock_id_001"

        single_config = (
            alert_config.model_copy(update={"to_phone": "+919876500001"})
            if hasattr(alert_config, "model_copy")
            else alert_config.copy(update={"to_phone": "+919876500001"})
        )
        dispatcher1 = FamilyAlertDispatcher(config=single_config, twilio_client=mock_client, store=store1)
        res1 = dispatcher1.dispatch(scam_record)
        assert res1.status == AlertStatus.SENT

        # Second delivery attempt on different dispatcher / process pointing to same DB
        dispatcher2 = FamilyAlertDispatcher(config=single_config, twilio_client=mock_client, store=store2)
        res2 = dispatcher2.dispatch(scam_record)
        assert res2.status == AlertStatus.SKIPPED
        assert res2.reason == "ALREADY_DISPATCHED"
        assert mock_client.messages.create.call_count == 1

    def test_stale_pending_alert_sweep(self, tmp_path):
        db_file = str(tmp_path / "stale_alerts.db")
        store = PersistentAlertStore(db_file)

        # Claim a call (status='pending')
        claimed = store.claim_call("call_stale_test", "+919876500001", "sms")
        assert claimed is True

        # Second immediate claim is blocked
        assert store.claim_call("call_stale_test", "+919876500001", "sms") is False

        # Sweep with 0 second timeout triggers sweep
        swept = store.sweep_stale_pending(stale_timeout_s=-1.0)
        assert swept == 1

        # Now can be claimed again after crash recovery
        reclaimed = store.claim_call("call_stale_test", "+919876500001", "sms")
        assert reclaimed is True

    def test_retry_classification_handles_connection_errors_and_transients(self):
        import socket
        import requests

        conn_err = requests.exceptions.ConnectionError("Failed to establish a new connection: [Errno 111] Connection refused")
        assert is_retryable_twilio_error(conn_err) is True

        timeout_err = requests.exceptions.Timeout("HTTPSConnectionPool: Read timed out.")
        assert is_retryable_twilio_error(timeout_err) is True

        sock_err = socket.error("Connection reset by peer")
        assert is_retryable_twilio_error(sock_err) is True

        # Twilio 429 rate limit is retryable
        tw_429 = Exception("Rate limit exceeded")
        tw_429.status = 429
        assert is_retryable_twilio_error(tw_429) is True

        # Twilio 400 is not retryable
        tw_400 = Exception("Invalid phone number")
        tw_400.status = 400
        assert is_retryable_twilio_error(tw_400) is False

    def test_env_factory_requires_recipient(self, monkeypatch):
        monkeypatch.delenv("FAMILY_ALERT_TO", raising=False)
        with pytest.raises(ValueError, match="FAMILY_ALERT_TO environment variable is required"):
            build_dispatcher_from_env()


class TestCallFinalizedEventListener:
    def test_call_finalized_triggers_dispatcher(self, scam_record):
        mock_dispatcher = MagicMock()
        mock_dispatcher.config.channel = AlertChannel.WHATSAPP
        mock_dispatcher.dispatch.return_value.status = AlertStatus.SENT

        event = {
            "event": "call.finalized",
            "call_id": scam_record["call_id"],
            "timestamp": "2026-10-17T02:00:00Z",
            "record": scam_record,
        }

        result = handle_call_finalized_event(event, dispatcher=mock_dispatcher)
        assert result.status == AlertStatus.SENT
        mock_dispatcher.dispatch.assert_called_once_with(scam_record)

    def test_dispatcher_failure_does_not_raise_exception(self, scam_record):
        broken_dispatcher = MagicMock()
        broken_dispatcher.config.to_phone = "+919876543210"
        broken_dispatcher.config.channel = AlertChannel.WHATSAPP
        broken_dispatcher.dispatch.side_effect = RuntimeError("Twilio network bridge crashed")

        event = {
            "event": "call.finalized",
            "call_id": scam_record["call_id"],
            "timestamp": "2026-10-17T02:00:00Z",
            "record": scam_record,
        }

        # Must not raise exception to the caller
        result = handle_call_finalized_event(event, dispatcher=broken_dispatcher)
        assert result.status == AlertStatus.FAILED
        assert "DISPATCHER_EXCEPTION" in result.reason

    def test_mock_bolna_scam_fixture_triggers_family_alert_end_to_end(self, alert_config):
        from scripts.mock_bolna import load_fixture

        fixture_path = os.path.join(FIXTURES_DIR, "01_scam_digital_arrest.json")
        payload = load_fixture(fixture_path)

        mock_client = MagicMock()
        mock_client.messages.create.return_value.sid = "SM_mock_bolna_replay_123"

        store = PersistentAlertStore(":memory:")
        dispatcher = FamilyAlertDispatcher(config=alert_config, twilio_client=mock_client, store=store)

        # Synthesize call.finalized event from mock_bolna fixture
        event = {
            "event": "call.finalized",
            "call_id": payload["call_id"],
            "timestamp": "2026-10-17T02:00:00Z",
            "record": {
                "call_id": payload["call_id"],
                "caller_number": payload["caller_number"],
                "verdict": "scam",
                "duration": payload["call_duration"],
                "summary": "Mock Bolna replay of digital arrest scam.",
                "extracted_intel": {
                    "upi_ids": [payload["metadata"]["planted_intel"]["upi_id"]],
                    "phone_numbers": [payload["metadata"]["planted_intel"]["phone_number"]],
                    "links": ["https://fake-cbi-clearance.org/pay"],
                },
            },
        }

        result = handle_call_finalized_event(event, dispatcher=dispatcher)
        assert result.status == AlertStatus.SENT
        assert mock_client.messages.create.call_count >= 1
        sent_body = mock_client.messages.create.call_args_list[0].kwargs["body"]
        assert payload["metadata"]["planted_intel"]["upi_id"] in sent_body
        assert "token=master_sec123" not in sent_body

    def test_render_yaml_includes_whatsapp_sandbox_and_alert_env_vars(self):
        render_yaml_path = os.path.join(FIXTURES_DIR, "..", "..", "render.yaml")
        with open(render_yaml_path, "r", encoding="utf-8") as f:
            content = f.read()
        for required_key in (
            "TWILIO_ACCOUNT_SID",
            "TWILIO_AUTH_TOKEN",
            "TWILIO_WHATSAPP_FROM",
            "ALERT_CHANNEL",
            "FAMILY_ALERT_TO",
            "REPORT_BASE_URL",
            "REPORT_SIGNING_SECRET",
            "GUARDIAN_EVENTS_TOKEN",
            "ALERT_DB_PATH",
        ):
            assert f"key: {required_key}" in content, f"Missing {required_key} in render.yaml"

    def test_alert_delivery_proof_contract_and_script(self, alert_config, tmp_path):
        from scripts.send_test_alert import deliver_and_record_proof

        repo_proof_path = os.path.join(FIXTURES_DIR, "..", "..", "evaluation", "live_calls", "alert_delivery_proof.json")
        assert os.path.exists(repo_proof_path), "evaluation/live_calls/alert_delivery_proof.json must exist"
        with open(repo_proof_path, "r", encoding="utf-8") as f:
            repo_proof = json.load(f)
        assert repo_proof["status"] in ("NOT_VERIFIED", "VERIFIED")
        if repo_proof["status"] == "NOT_VERIFIED":
            assert repo_proof["twilio_message_sid"] is None

        # Test recording a verified proof when Twilio returns a real SM... SID
        mock_client = MagicMock()
        mock_client.messages.create.return_value.sid = "SM0123456789abcdef0123456789abcdef"
        store = PersistentAlertStore(str(tmp_path / "proof_alerts.db"))
        dispatcher = FamilyAlertDispatcher(config=alert_config, twilio_client=mock_client, store=store)

        out_proof = tmp_path / "alert_delivery_proof.json"
        proof = deliver_and_record_proof(
            dispatcher=dispatcher,
            proof_path=str(out_proof),
            screenshot_path="evaluation/live_calls/whatsapp_alert_screenshot.png",
        )
        assert proof["status"] == "VERIFIED"
        assert proof["twilio_message_sid"] == "SM0123456789abcdef0123456789abcdef"
        assert proof["screenshot_path"] == "evaluation/live_calls/whatsapp_alert_screenshot.png"
        assert out_proof.exists()

    def test_bolna_latency_tuning_and_stage2_latency_profile(self):
        root_dir = os.path.join(FIXTURES_DIR, "..", "..")
        bolna_path = os.path.join(root_dir, "bolna", "rakshak-v0.json")
        with open(bolna_path, "r", encoding="utf-8") as f:
            bolna_cfg = json.load(f)
        task = bolna_cfg["agent_config"]["tasks"][0]
        assert task["task_config"]["incremental_delay"] in (180, 350)
        assert task["tools_config"]["transcriber"]["endpointing"] in (350, 100)
        assert task["tools_config"]["synthesizer"]["buffer_size"] in (80, 180)
        expected_pronunciation = {
            "HDFC": "H D F C",
            "ICICI": "I C I C I",
            "UPI": "U P I",
            "IFSC": "I F S C",
            "CBI": "C B I",
            "Aadhaar": "Aadhaar",
        }
        assert task["tools_config"]["synthesizer"]["pronunciation_dict"] == expected_pronunciation

        profile_path = os.path.join(root_dir, "evaluation", "stage2_latency_profile.json")
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)
        assert profile["p95_ms"] < 1000.0
        assert profile["total_latency"]["p95_ms"] < 1000.0
