import json
import os
import pytest
from unittest.mock import MagicMock

from app.notify.alerts import (
    AlertConfig,
    AlertChannel,
    AlertStatus,
    FamilyAlertDispatcher,
    PersistentAlertStore,
    format_alert_message,
    is_gsm7,
)

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
        },
        "summary": "Scammer impersonated CBI officer alleging illegal drugs in Taiwan parcel.",
        "report_url": f"http://localhost:8000/dashboard/report/{data['call_id']}?token=sec123",
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
        to_phone="+919876500000",
        channel=AlertChannel.WHATSAPP,
        base_report_url="http://localhost:8000/dashboard/report",
        token="sec123",
    )


class TestAlertFormattingAndSegmentation:
    def test_scam_whatsapp_alert_contains_all_details(self, scam_record, alert_config):
        msg = format_alert_message(scam_record, AlertChannel.WHATSAPP, alert_config.base_report_url)
        assert "SCAM ALERT" in msg
        assert scam_record["caller_number"] in msg
        assert "cbi.officer.verma@okaxis" in msg
        assert "987654321098" in msg
        assert "SBIN0001234" in msg
        assert scam_record["call_id"] in msg

    def test_scam_sms_gsm7_strictly_within_two_segments(self, scam_record, alert_config):
        msg = format_alert_message(scam_record, AlertChannel.SMS, alert_config.base_report_url)
        assert "[SUSPECTED SCAM]" in msg
        assert scam_record["caller_number"] in msg
        assert "cbi.officer.verma@okaxis" in msg
        assert "987654321098" in msg
        # Report dossier URL must survive
        assert scam_record["call_id"] in msg
        # GSM-7 2-segment ceiling is 306 characters
        assert is_gsm7(msg)
        assert len(msg) <= 306, f"GSM-7 SMS length {len(msg)} exceeded 306 characters"

    def test_hindi_unicode_sms_within_ucs2_two_segments(self, alert_config):
        hindi_record = {
            "call_id": "call_hi_001",
            "caller_number": "+919876543210",
            "verdict": "genuine",
            "message": "शर्मा जी का पार्सल गार्ड रूम में जमा कर दिया है।",
        }
        msg = format_alert_message(hindi_record, AlertChannel.SMS, alert_config.base_report_url)
        assert not is_gsm7(msg), "Must be detected as Unicode"
        # UCS-2 2-segment ceiling is 134 characters
        assert len(msg) <= 134, f"UCS-2 SMS length {len(msg)} exceeded 134 characters"


class TestFamilyAlertDispatcher:
    def test_scam_fixture_sends_exactly_one_alert(self, scam_record, alert_config):
        mock_client = MagicMock()
        mock_client.messages.create.return_value.sid = "SM_mock_message_sid_001"

        store = PersistentAlertStore(":memory:")
        dispatcher = FamilyAlertDispatcher(config=alert_config, twilio_client=mock_client, store=store)
        result = dispatcher.dispatch(scam_record)

        assert result.status == AlertStatus.SENT
        assert result.retry_count == 0
        assert mock_client.messages.create.call_count == 1

    def test_cross_instance_persistent_idempotency(self, scam_record, alert_config, tmp_path):
        db_file = str(tmp_path / "alerts_idempotency.db")
        store1 = PersistentAlertStore(db_file)
        store2 = PersistentAlertStore(db_file)

        mock_client = MagicMock()
        mock_client.messages.create.return_value.sid = "SM_mock_id_001"

        dispatcher1 = FamilyAlertDispatcher(config=alert_config, twilio_client=mock_client, store=store1)
        res1 = dispatcher1.dispatch(scam_record)
        assert res1.status == AlertStatus.SENT

        # Second delivery on different dispatcher / process pointing to same database
        dispatcher2 = FamilyAlertDispatcher(config=alert_config, twilio_client=mock_client, store=store2)
        res2 = dispatcher2.dispatch(scam_record)
        assert res2.status == AlertStatus.SKIPPED
        assert res2.reason == "ALREADY_DISPATCHED"
        assert mock_client.messages.create.call_count == 1

    def test_non_retryable_client_error_fails_immediately(self, scam_record, alert_config):
        mock_client = MagicMock()
        # Mock 400 Bad Request
        err = Exception("Twilio 400 Invalid phone number")
        err.status = 400
        mock_client.messages.create.side_effect = err

        store = PersistentAlertStore(":memory:")
        dispatcher = FamilyAlertDispatcher(config=alert_config, twilio_client=mock_client, store=store)
        result = dispatcher.dispatch(scam_record)

        assert result.status == AlertStatus.FAILED
        assert result.retry_count == 0
        assert mock_client.messages.create.call_count == 1  # No repeated retries for 400

    def test_retryable_error_retries_three_times(self, scam_record, alert_config):
        mock_client = MagicMock()
        err = Exception("Twilio 503 Service Unavailable")
        err.status = 503
        mock_client.messages.create.side_effect = err

        store = PersistentAlertStore(":memory:")
        dispatcher = FamilyAlertDispatcher(
            config=alert_config,
            twilio_client=mock_client,
            store=store,
            backoff_base_s=0.001,
        )
        result = dispatcher.dispatch(scam_record)

        assert result.status == AlertStatus.FAILED
        assert result.retry_count == 3
        # 1 initial attempt + 3 retries = 4 total attempts
        assert mock_client.messages.create.call_count == 4
