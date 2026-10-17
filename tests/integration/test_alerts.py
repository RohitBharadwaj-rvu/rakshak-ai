import json
import os
import pytest
from unittest.mock import MagicMock

from app.notify.alerts import (
    AlertConfig,
    AlertChannel,
    AlertStatus,
    FamilyAlertDispatcher,
    format_alert_message,
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
            "bank_accounts": [],
            "ifsc_codes": [],
        },
        "summary": "Scammer impersonated CBI officer alleging illegal drugs in Taiwan parcel and demanded deposit.",
        "report_url": f"https://guardianline.rvu.edu/report/{data['call_id']}",
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
        "summary": "Blue Dart delivery courier confirmed parcel drop at society security guard.",
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
        base_report_url="https://guardianline.rvu.edu/report",
    )


class TestAlertFormatting:
    def test_scam_whatsapp_alert_contains_all_details(self, scam_record, alert_config):
        msg = format_alert_message(scam_record, AlertChannel.WHATSAPP, alert_config.base_report_url)
        assert "SCAM ALERT" in msg
        assert scam_record["caller_number"] in msg
        assert "cbi.officer.verma@okaxis" in msg
        assert "9876543210" in msg
        assert scam_record["call_id"] in msg

    def test_scam_sms_alert_fits_within_two_segments(self, scam_record, alert_config):
        msg = format_alert_message(scam_record, AlertChannel.SMS, alert_config.base_report_url)
        assert "SCAM ALERT" in msg
        assert scam_record["caller_number"] in msg
        assert "cbi.officer.verma@okaxis" in msg
        # Standard SMS 2-segment ceiling: <= 306 chars (153 chars per segment) or <= 320 chars GSM
        assert len(msg) <= 320, f"SMS length {len(msg)} exceeded 2 segments (320 chars)"

    def test_genuine_note_formats_as_message_taken(self, genuine_record, alert_config):
        msg = format_alert_message(genuine_record, AlertChannel.WHATSAPP, alert_config.base_report_url)
        assert "MESSAGE TAKEN" in msg
        assert "SCAM ALERT" not in msg
        assert genuine_record["caller_number"] in msg
        assert "Blue Dart" in msg


class TestFamilyAlertDispatcher:
    def test_scam_fixture_sends_exactly_one_alert(self, scam_record, alert_config):
        mock_client = MagicMock()
        mock_client.messages.create.return_value.sid = "SM_mock_message_sid_001"

        dispatcher = FamilyAlertDispatcher(config=alert_config, twilio_client=mock_client)
        result = dispatcher.dispatch(scam_record)

        assert result.status == AlertStatus.SENT
        assert result.retry_count == 0
        assert mock_client.messages.create.call_count == 1

    def test_call_finalized_twice_sends_only_one_alert_idempotency(self, scam_record, alert_config):
        mock_client = MagicMock()
        mock_client.messages.create.return_value.sid = "SM_mock_message_sid_002"

        dispatcher = FamilyAlertDispatcher(config=alert_config, twilio_client=mock_client)
        result1 = dispatcher.dispatch(scam_record)
        assert result1.status == AlertStatus.SENT

        # Second delivery of same call_id
        result2 = dispatcher.dispatch(scam_record)
        assert result2.status == AlertStatus.SKIPPED
        assert result2.reason == "ALREADY_DISPATCHED"
        assert mock_client.messages.create.call_count == 1  # No duplicate send

    def test_genuine_fixture_sends_message_taken_note(self, genuine_record, alert_config):
        mock_client = MagicMock()
        mock_client.messages.create.return_value.sid = "SM_mock_message_sid_003"

        dispatcher = FamilyAlertDispatcher(config=alert_config, twilio_client=mock_client)
        result = dispatcher.dispatch(genuine_record)

        assert result.status == AlertStatus.SENT
        sent_body = mock_client.messages.create.call_args[1]["body"]
        assert "MESSAGE TAKEN" in sent_body
        assert "SCAM ALERT" not in sent_body

    def test_retries_three_times_with_backoff_on_twilio_error(self, scam_record, alert_config):
        mock_client = MagicMock()
        # Simulate Twilio network errors on all calls
        mock_client.messages.create.side_effect = Exception("Twilio 503 Service Unavailable")

        dispatcher = FamilyAlertDispatcher(config=alert_config, twilio_client=mock_client, backoff_base_s=0.01)
        result = dispatcher.dispatch(scam_record)

        assert result.status == AlertStatus.FAILED
        assert result.retry_count == 3
        assert mock_client.messages.create.call_count == 3
        # Ensure it does NOT throw an unhandled exception (resilient)
