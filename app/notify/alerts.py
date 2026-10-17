"""
Family Alert Dispatcher for GuardianLine (Lane C / T-ALERT).

Dispatches immediate alerts to family members via WhatsApp or SMS upon call finalization.
Ensures:
- Idempotency: multiple finalized events for the same call_id send only one alert.
- Reliability: 3 retries with exponential backoff on Twilio errors.
- Length constraint: SMS format fits comfortably within 2 SMS segments (<= 320 chars).
- Safe fail: Twilio errors are logged and never crash the main webhook loop.
"""

import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

logger = logging.getLogger("guardianline.notify")


class AlertChannel(str, Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"


class AlertStatus(str, Enum):
    SENT = "sent"
    SKIPPED = "skipped"
    FAILED = "failed"


class AlertConfig(BaseModel):
    account_sid: Optional[str] = None
    auth_token: Optional[str] = None
    from_phone: Optional[str] = None
    to_phone: str
    channel: AlertChannel = AlertChannel.WHATSAPP
    base_report_url: str = "https://guardianline.rvu.edu/report"


class AlertResult(BaseModel):
    status: AlertStatus
    call_id: str
    reason: Optional[str] = None
    recipient: str
    channel: AlertChannel
    message_sid: Optional[str] = None
    retry_count: int = 0


def format_alert_message(
    call_record: Dict[str, Any],
    channel: AlertChannel,
    base_report_url: str = "https://guardianline.rvu.edu/report",
) -> str:
    """
    Formats the notification string according to verdict and delivery channel.
    SMS is strictly constrained to <= 320 characters (2 segments).
    """
    call_id = call_record.get("call_id", "unknown_call")
    caller_num = call_record.get("caller_number", "Unknown Caller")
    verdict = str(call_record.get("verdict", "unsure")).lower()
    intel = call_record.get("extracted_intel", {}) or {}
    report_link = call_record.get("report_url") or f"{base_report_url.rstrip('/')}/{call_id}"

    upi_list: List[str] = intel.get("upi_ids", [])
    phone_list: List[str] = intel.get("phone_numbers", [])
    acc_list: List[str] = intel.get("bank_accounts", [])

    if verdict == "scam":
        if channel == AlertChannel.SMS:
            # 2 SMS segments max (<= 320 characters)
            intel_parts = []
            if upi_list:
                intel_parts.append(f"UPI:{upi_list[0]}")
            if acc_list:
                intel_parts.append(f"A/C:{acc_list[0]}")
            if phone_list:
                intel_parts.append(f"Ph:{phone_list[0]}")
            intel_str = " | ".join(intel_parts) if intel_parts else "Intel logged"

            msg = (
                f"[SCAM ALERT] Blocked call from {caller_num}. "
                f"{intel_str}. Dossier: {report_link}"
            )
            # Hard clip if somehow exceeds 320
            return msg[:320]
        else:
            # WhatsApp rich formatting
            bullet_lines = []
            if upi_list:
                bullet_lines.append(f"• *UPI ID:* {', '.join(upi_list)}")
            if acc_list:
                bullet_lines.append(f"• *Bank A/C:* {', '.join(acc_list)}")
            if phone_list:
                bullet_lines.append(f"• *Phone:* {', '.join(phone_list)}")
            intel_block = "\n".join(bullet_lines) if bullet_lines else "• Intel logged to dossier"

            summary = call_record.get("summary", "Fraud attempt intercepted.")
            return (
                f"🚨 *GUARDIANLINE SCAM ALERT*\n\n"
                f"An unrecognized scam call targeting the elder was intercepted and safely neutralized.\n\n"
                f"*Caller:* {caller_num}\n"
                f"*Summary:* {summary}\n\n"
                f"*Extracted Attacker Intel:*\n"
                f"{intel_block}\n\n"
                f"📄 *1930 Cybercrime Dossier:* {report_link}\n"
                f"Call ID: `{call_id}`"
            )

    elif verdict == "genuine":
        message_body = call_record.get("message") or call_record.get("summary") or "Caller left a message."
        if channel == AlertChannel.SMS:
            return (
                f"[MESSAGE TAKEN] Call from {caller_num}: {message_body}"
            )[:320]
        else:
            return (
                f"📞 *GUARDIANLINE MESSAGE TAKEN*\n\n"
                f"A genuine caller reached the assistant:\n"
                f"*Caller:* {caller_num}\n"
                f"*Note:* {message_body}\n"
                f"Call ID: `{call_id}`"
            )

    else:
        # Unsure / Screening
        return f"[SCREENING NOTE] Call from {caller_num} completed. Call ID: {call_id}"[:320]


class FamilyAlertDispatcher:
    """
    Manages dispatching alerts to family members with idempotency and retry handling.
    """

    def __init__(
        self,
        config: AlertConfig,
        twilio_client: Any = None,
        backoff_base_s: float = 0.5,
    ):
        self.config = config
        self.twilio_client = twilio_client
        self.backoff_base_s = backoff_base_s
        self._sent_call_ids: Set[str] = set()

    def dispatch(self, call_record: Dict[str, Any]) -> AlertResult:
        call_id = call_record.get("call_id")
        if not call_id:
            logger.error("Cannot dispatch alert: call_id missing in record")
            return AlertResult(
                status=AlertStatus.FAILED,
                call_id="unknown",
                reason="MISSING_CALL_ID",
                recipient=self.config.to_phone,
                channel=self.config.channel,
            )

        # 1. Idempotency Check
        if call_id in self._sent_call_ids:
            logger.info("Call %s already dispatched, skipping duplicate alert", call_id)
            return AlertResult(
                status=AlertStatus.SKIPPED,
                call_id=call_id,
                reason="ALREADY_DISPATCHED",
                recipient=self.config.to_phone,
                channel=self.config.channel,
            )

        message_body = format_alert_message(
            call_record=call_record,
            channel=self.config.channel,
            base_report_url=self.config.base_report_url,
        )

        recipient = self.config.to_phone
        from_phone = self.config.from_phone or "+14155238886"

        if self.config.channel == AlertChannel.WHATSAPP:
            if not recipient.startswith("whatsapp:"):
                recipient = f"whatsapp:{recipient}"
            if not from_phone.startswith("whatsapp:"):
                from_phone = f"whatsapp:{from_phone}"

        # If no twilio client provided (e.g. testing or mock fallback)
        if self.twilio_client is None:
            logger.info(
                "[MOCK ALERT SENT] To: %s | Channel: %s | Body: %s",
                recipient,
                self.config.channel,
                message_body,
            )
            self._sent_call_ids.add(call_id)
            return AlertResult(
                status=AlertStatus.SENT,
                call_id=call_id,
                recipient=recipient,
                channel=self.config.channel,
                message_sid="SM_local_mock_simulated",
            )

        # 2. Resilient Send with 3 Retries & Exponential Backoff
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                resp = self.twilio_client.messages.create(
                    to=recipient,
                    from_=from_phone,
                    body=message_body,
                )
                self._sent_call_ids.add(call_id)
                logger.info("Alert dispatched for %s (SID: %s)", call_id, getattr(resp, "sid", "OK"))
                return AlertResult(
                    status=AlertStatus.SENT,
                    call_id=call_id,
                    recipient=recipient,
                    channel=self.config.channel,
                    message_sid=getattr(resp, "sid", "OK"),
                    retry_count=attempt,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "Twilio dispatch attempt %d/%d failed for call %s: %s",
                    attempt + 1,
                    max_retries,
                    call_id,
                    str(e),
                )
                if attempt < max_retries - 1:
                    sleep_time = self.backoff_base_s * (2 ** attempt)
                    time.sleep(sleep_time)

        # If all retries failed, fail gracefully without blowing up the caller
        logger.error(
            "Failed all %d attempts to send alert for call %s: %s",
            max_retries,
            call_id,
            str(last_error),
        )
        return AlertResult(
            status=AlertStatus.FAILED,
            call_id=call_id,
            reason=f"Twilio delivery failed after {max_retries} retries: {last_error}",
            recipient=recipient,
            channel=self.config.channel,
            retry_count=max_retries,
        )
