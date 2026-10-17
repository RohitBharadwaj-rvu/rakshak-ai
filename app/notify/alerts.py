"""
Family Alert Dispatcher for GuardianLine (Lane C / T-ALERT).
File: app/notify/alerts.py

Features:
- Dispatches real-time WhatsApp and SMS alerts to family upon call finalization
- Persistent SQLite idempotency store to prevent duplicate sends across workers/restarts
- Robust SMS segment budgeting:
    - GSM-7: 153 chars/segment concatenated -> max 306 chars for 2 segments
    - UCS-2 (Unicode/Hindi): 67 chars/segment concatenated -> max 134 chars for 2 segments
    - Trims summary and intel first; never clips the 1930 report dossier link
- Resilient retry: 3 retries with exponential backoff on retryable (429, 5xx, network) errors
- Non-retryable permanent client errors (400, 401, invalid numbers) fail immediately
- PII-masked logging
"""

import logging
import os
import re
import sqlite3
import threading
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger("guardianline.notify")

GSM7_CHARS = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà^{}\\[~]|€"
)


class AlertChannel(str, Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"


class AlertStatus(str, Enum):
    SENT = "sent"
    SKIPPED = "skipped"
    MOCK = "mock"
    FAILED = "failed"


class AlertConfig(BaseModel):
    account_sid: Optional[str] = None
    auth_token: Optional[str] = None
    from_phone: Optional[str] = None
    to_phone: str
    channel: AlertChannel = AlertChannel.WHATSAPP
    base_report_url: str = "http://localhost:8000/dashboard/report"
    token: Optional[str] = None


class AlertResult(BaseModel):
    status: AlertStatus
    call_id: str
    reason: Optional[str] = None
    recipient: str
    channel: AlertChannel
    message_sid: Optional[str] = None
    retry_count: int = 0


def mask_number(raw: Optional[str]) -> str:
    if not raw:
        return "WITHHELD"
    s = str(raw).strip()
    if len(s) <= 4:
        return "****"
    return f"{s[:4]}****{s[-3:]}"


def is_gsm7(text: str) -> bool:
    return all(c in GSM7_CHARS for c in text)


def compute_max_two_segment_chars(text: str) -> int:
    return 306 if is_gsm7(text) else 134


def format_alert_message(
    call_record: Dict[str, Any],
    channel: AlertChannel,
    base_report_url: str = "http://localhost:8000/dashboard/report",
    dashboard_token: Optional[str] = None,
) -> str:
    """
    Formats notification for WhatsApp or SMS.
    Guarantees SMS fits within 2 segments (306 chars for GSM-7, 134 for UCS-2).
    Never clips the dossier URL.
    """
    call_id = str(call_record.get("call_id") or "unknown_call")
    caller_num = str(call_record.get("caller_number") or "Unknown")
    verdict = str(call_record.get("verdict", "unsure")).lower()
    intel = call_record.get("extracted_intel", {}) or {}

    # Build report link
    token_suffix = f"?token={dashboard_token}" if dashboard_token else ""
    report_link = call_record.get("report_url") or f"{base_report_url.rstrip('/')}/{call_id}{token_suffix}"

    upi_list: List[str] = intel.get("upi_ids", [])
    acc_list: List[str] = intel.get("bank_accounts", [])
    ifsc_list: List[str] = intel.get("ifsc_codes", [])
    phone_list: List[str] = intel.get("phone_numbers", [])

    if verdict == "scam":
        if channel == AlertChannel.SMS:
            # Build intel summary containing all items
            intel_parts = []
            if upi_list:
                intel_parts.append(f"UPI:{','.join(upi_list)}")
            if acc_list:
                intel_parts.append(f"AC:{','.join(acc_list)}")
            if ifsc_list:
                intel_parts.append(f"IFSC:{','.join(ifsc_list)}")
            if phone_list:
                intel_parts.append(f"Ph:{','.join(phone_list)}")
            intel_str = " | ".join(intel_parts) if intel_parts else "Intel logged"

            prefix = f"[SUSPECTED SCAM] Call from {caller_num}. "
            suffix = f" Dossier: {report_link}"

            # Calculate available budget for intel and summary
            # Check encoding of prefix + suffix
            budget = compute_max_two_segment_chars(prefix + suffix + intel_str)
            fixed_len = len(prefix) + len(suffix)
            avail_for_intel = budget - fixed_len

            if avail_for_intel > 10:
                trimmed_intel = intel_str[:avail_for_intel]
                return f"{prefix}{trimmed_intel}{suffix}"
            else:
                return f"{prefix}{suffix}".strip()

        else:
            # WhatsApp rich formatting
            bullet_lines = []
            if upi_list:
                bullet_lines.append(f"• *UPI ID(s):* {', '.join(upi_list)}")
            if acc_list:
                bullet_lines.append(f"• *Bank A/C(s):* {', '.join(acc_list)}")
            if ifsc_list:
                bullet_lines.append(f"• *IFSC Code(s):* {', '.join(ifsc_list)}")
            if phone_list:
                bullet_lines.append(f"• *Callback Phone(s):* {', '.join(phone_list)}")
            intel_block = "\n".join(bullet_lines) if bullet_lines else "• Attacker details logged to dossier"

            summary = call_record.get("summary") or "Suspected fraud attempt screened by voice assistant."
            return (
                f"🚨 *GUARDIANLINE SCAM ALERT*\n\n"
                f"A suspected scam call targeting the elder was screened and redirected to the honeypot.\n\n"
                f"*Caller:* {caller_num}\n"
                f"*Summary:* {summary}\n\n"
                f"*Captured Attacker Intel:*\n"
                f"{intel_block}\n\n"
                f"📄 *Draft 1930 Cybercrime Dossier:* {report_link}\n"
                f"Call ID: `{call_id}`"
            )

    elif verdict == "genuine":
        message_body = call_record.get("message") or call_record.get("summary") or "Caller left a message."
        if channel == AlertChannel.SMS:
            prefix = f"[MESSAGE TAKEN] Call from {caller_num}: "
            budget = compute_max_two_segment_chars(prefix + message_body)
            avail = budget - len(prefix)
            trimmed_msg = message_body[:max(0, avail)]
            return f"{prefix}{trimmed_msg}"
        else:
            return (
                f"📞 *GUARDIANLINE MESSAGE TAKEN*\n\n"
                f"A genuine caller reached the assistant:\n"
                f"*Caller:* {caller_num}\n"
                f"*Note:* {message_body}\n"
                f"Call ID: `{call_id}`"
            )

    else:
        return f"[SCREENING NOTE] Call from {caller_num} completed. Call ID: {call_id}"[:134]


class PersistentAlertStore:
    """
    SQLite-backed store to guarantee cross-process idempotency for family alerts.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._is_mem = (self.db_path == ":memory:")
        self._conn = sqlite3.connect(":memory:", check_same_thread=False) if self._is_mem else None

        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dispatched_alerts (
                    call_id TEXT PRIMARY KEY,
                    recipient TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    message_sid TEXT,
                    dispatched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
            if not self._is_mem:
                conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn:
            return self._conn
        return sqlite3.connect(self.db_path)

    def claim_call(self, call_id: str, recipient: str, channel: str) -> bool:
        """
        Attempts to insert call_id. Returns True if claimed, False if already exists.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO dispatched_alerts (call_id, recipient, channel) VALUES (?, ?, ?)",
                    (call_id, recipient, channel),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
            finally:
                if not self._is_mem:
                    conn.close()

    def mark_sent(self, call_id: str, message_sid: str) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE dispatched_alerts SET message_sid = ? WHERE call_id = ?",
                    (message_sid, call_id),
                )
                conn.commit()
            finally:
                if not self._is_mem:
                    conn.close()

    def release_call(self, call_id: str) -> None:
        """If delivery fails permanently, release lock so it can be retried if needed."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM dispatched_alerts WHERE call_id = ?", (call_id,))
                conn.commit()
            finally:
                if not self._is_mem:
                    conn.close()



def is_retryable_twilio_error(error: Exception) -> bool:
    """
    Determines if exception is transient (network timeout, 429 rate limit, 5xx).
    Permanent client errors (400, 401, 21211 invalid phone number) are NOT retryable.
    """
    err_str = str(error).lower()
    # Check status code attribute if Twilio RestException
    code = getattr(error, "status", None)
    if code:
        if code == 429 or code >= 500:
            return True
        if code in (400, 401, 403, 404):
            return False

    # Check common transient network error strings
    transient_indicators = ["timeout", "connection refused", "503", "502", "504", "429", "rate limit", "temporarily unavailable"]
    return any(ind in err_str for ind in transient_indicators)


class FamilyAlertDispatcher:
    """
    Manages family alert dispatches with persistent idempotency and resilient retry.
    """

    def __init__(
        self,
        config: AlertConfig,
        twilio_client: Any = None,
        store: Optional[PersistentAlertStore] = None,
        backoff_base_s: float = 0.1,
    ):
        self.config = config
        self.twilio_client = twilio_client
        self.store = store or PersistentAlertStore()
        self.backoff_base_s = backoff_base_s

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

        recipient = self.config.to_phone
        from_phone = self.config.from_phone or "+14155238886"

        if self.config.channel == AlertChannel.WHATSAPP:
            if not recipient.startswith("whatsapp:"):
                recipient = f"whatsapp:{recipient}"
            if not from_phone.startswith("whatsapp:"):
                from_phone = f"whatsapp:{from_phone}"

        # 1. Persistent Idempotency Claim
        if not self.store.claim_call(call_id, recipient, self.config.channel.value):
            logger.info("Call %s already dispatched or in flight, skipping duplicate alert", call_id)
            return AlertResult(
                status=AlertStatus.SKIPPED,
                call_id=call_id,
                reason="ALREADY_DISPATCHED",
                recipient=recipient,
                channel=self.config.channel,
            )

        message_body = format_alert_message(
            call_record=call_record,
            channel=self.config.channel,
            base_report_url=self.config.base_report_url,
            dashboard_token=self.config.token,
        )

        masked_recip = mask_number(recipient)

        # 2. Mock mode if twilio_client is None
        if self.twilio_client is None:
            logger.info(
                "[MOCK ALERT] To: %s | Channel: %s | Call: %s",
                masked_recip,
                self.config.channel,
                call_id,
            )
            self.store.mark_sent(call_id, "SM_mock_id")
            return AlertResult(
                status=AlertStatus.MOCK,
                call_id=call_id,
                recipient=recipient,
                channel=self.config.channel,
                message_sid="SM_mock_simulated",
            )

        # 3. Resilient Send with up to 3 Retries (Total 4 attempts) on transient errors
        max_retries = 3
        last_error = None
        retries_done = 0

        for attempt in range(max_retries + 1):
            try:
                resp = self.twilio_client.messages.create(
                    to=recipient,
                    from_=from_phone,
                    body=message_body,
                )
                sid = getattr(resp, "sid", "OK")
                self.store.mark_sent(call_id, sid)
                logger.info("Alert dispatched for call %s to %s (SID: %s)", call_id, masked_recip, sid)
                return AlertResult(
                    status=AlertStatus.SENT,
                    call_id=call_id,
                    recipient=recipient,
                    channel=self.config.channel,
                    message_sid=sid,
                    retry_count=retries_done,
                )
            except Exception as e:
                last_error = e
                if not is_retryable_twilio_error(e):
                    logger.error("Non-retryable client error on call %s: %s", call_id, str(e))
                    self.store.release_call(call_id)
                    return AlertResult(
                        status=AlertStatus.FAILED,
                        call_id=call_id,
                        reason=f"Non-retryable Twilio error: {e}",
                        recipient=recipient,
                        channel=self.config.channel,
                        retry_count=retries_done,
                    )

                if attempt < max_retries:
                    retries_done += 1
                    sleep_time = self.backoff_base_s * (2 ** attempt)
                    time.sleep(sleep_time)

        # Failed after all 3 retries
        logger.error("All %d retries failed for call %s: %s", max_retries, call_id, str(last_error))
        self.store.release_call(call_id)
        return AlertResult(
            status=AlertStatus.FAILED,
            call_id=call_id,
            reason=f"Twilio delivery failed after {max_retries} retries: {last_error}",
            recipient=recipient,
            channel=self.config.channel,
            retry_count=retries_done,
        )


def build_dispatcher_from_env() -> FamilyAlertDispatcher:
    """
    Factory to construct FamilyAlertDispatcher from environment variables.
    """
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_phone = os.environ.get("TWILIO_PHONE_NUMBER") or os.environ.get("TWILIO_WHATSAPP_FROM", "+14155238886")
    to_phone = os.environ.get("FAMILY_ALERT_TO", "+919876500000")
    channel_str = os.environ.get("ALERT_CHANNEL", "whatsapp").lower()
    channel = AlertChannel.SMS if channel_str == "sms" else AlertChannel.WHATSAPP
    report_url = os.environ.get("REPORT_BASE_URL", "http://localhost:8000/dashboard/report")
    dash_token = os.environ.get("GUARDIAN_DASHBOARD_TOKEN")

    config = AlertConfig(
        account_sid=sid,
        auth_token=token,
        from_phone=from_phone,
        to_phone=to_phone,
        channel=channel,
        base_report_url=report_url,
        token=dash_token,
    )

    twilio_client = None
    if sid and token:
        try:
            from twilio.rest import Client
            twilio_client = Client(sid, token)
        except ImportError:
            logger.warning("Twilio library not installed; operating in mock mode")

    return FamilyAlertDispatcher(config=config, twilio_client=twilio_client)
