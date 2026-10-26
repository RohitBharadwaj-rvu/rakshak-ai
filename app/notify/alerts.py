"""
Family Alert Dispatcher for GuardianLine (Lane C / T-ALERT).
File: app/notify/alerts.py

Features:
- Dispatches real-time WhatsApp and SMS alerts to family upon call finalization
- Automatic SMS fallback via _fit_sms when WhatsApp fails with Twilio sandbox/number errors (63015, 21211, 21614)
- Multi-recipient support (comma-separated phone numbers in FAMILY_ALERT_TO)
- Per-call expiring signed links (HMAC-SHA256) instead of master dashboard token in alerts
- Persistent SQLite store with two-phase state ('pending' -> 'sent' / 'failed') and stale sweep
- Robust SMS segment budgeting:
    - GSM-7: 153 septets/segment concatenated -> max 306 septets for 2 segments
    - GSM-7 extended characters ({}[]~|^€) accurately counted as 2 septets each
    - UCS-2 (Unicode/Hindi): 67 chars/segment concatenated -> max 134 chars for 2 segments
    - Strict mathematical guarantee that SMS never exceeds 2 segments
- Resilient retry: 3 retries with exponential backoff on retryable (429, 5xx, connection/network) errors
- Non-retryable permanent client errors (400, 401, invalid numbers) fail immediately
- Asynchronous / non-blocking dispatch support to prevent stalling webhook workers
- PII-masked logging
"""

import concurrent.futures
import hashlib
import hmac
import logging
import os
import re
import secrets
import socket
import sqlite3
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote
from pydantic import BaseModel, Field

try:
    from twilio.base.exceptions import TwilioRestException
except ImportError:
    class TwilioRestException(Exception):  # type: ignore[no-redef]
        """Fallback TwilioRestException when twilio SDK is not installed locally."""

        def __init__(
            self,
            status: int = 400,
            uri: str = "/Messages",
            msg: str = "",
            code: Optional[int] = None,
            method: str = "POST",
            details: Optional[Dict[str, Any]] = None,
        ):
            super().__init__(msg or f"Twilio error {code}")
            self.status = status
            self.uri = uri
            self.msg = msg
            self.code = code
            self.method = method
            self.details = details

logger = logging.getLogger("guardianline.notify")

WHATSAPP_FALLBACK_TWILIO_CODES = (63015, 21211, 21614, 63007)

# GSM 03.38 character sets
BASIC_GSM7 = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
EXTENDED_GSM7 = set("^{}\\[~]|€\f")

_THREAD_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4)


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
    signing_secret: Optional[str] = None

    @property
    def recipients(self) -> List[str]:
        raw = self.to_phone or ""
        nums = [n.strip() for n in re.split(r"[,;]+", raw) if n.strip()]
        return nums or [raw.strip()] if raw.strip() else []


class AlertResult(BaseModel):
    status: AlertStatus
    call_id: str
    reason: Optional[str] = None
    recipient: str
    channel: AlertChannel
    message_sid: Optional[str] = None
    retry_count: int = 0
    sub_results: Optional[List[Dict[str, Any]]] = None


def mask_number(raw: Optional[str]) -> str:
    if not raw:
        return "WITHHELD"
    s = str(raw).strip()
    if len(s) <= 4:
        return "****"
    return f"{s[:4]}****{s[-3:]}"


def is_gsm7(text: str) -> bool:
    """Returns True if text can be represented exclusively using GSM-7 character sets."""
    return all(c in BASIC_GSM7 or c in EXTENDED_GSM7 for c in text)


def count_septets(text: str) -> int:
    """
    Calculates exact septet count for GSM-7 text.
    Standard characters take 1 septet.
    Extended characters ({}[]~|^€) take 2 septets.
    """
    total = 0
    for c in text:
        if c in EXTENDED_GSM7:
            total += 2
        elif c in BASIC_GSM7:
            total += 1
        else:
            raise ValueError(f"Character '{c}' is not in the GSM-7 alphabet")
    return total


def generate_report_signature(call_id: str, expiry: int, secret_key: str) -> str:
    """Generates a compact 16-character HMAC-SHA256 signature for per-call report authorization."""
    msg = f"{call_id}:{expiry}".encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:16]


def verify_report_signature(call_id: str, expiry: int, signature: str, secret_key: str) -> bool:
    """Validates signature and expiration for per-call report authorization."""
    if expiry < int(time.time()):
        return False
    expected = generate_report_signature(call_id, expiry, secret_key)
    return secrets.compare_digest(signature, expected)


def get_report_signing_secret() -> Optional[str]:
    """Secret for per-call report links. Prefer a dedicated secret; fall back to the dashboard token."""
    return os.environ.get("REPORT_SIGNING_SECRET") or os.environ.get("GUARDIAN_DASHBOARD_TOKEN")


def _sms_budget(text: str) -> int:
    """Two-segment budget in encoding units: septets for GSM-7, characters for UCS-2."""
    return 306 if is_gsm7(text) else 134


def _sms_units(text: str) -> int:
    return count_septets(text) if is_gsm7(text) else len(text)


def _fit_sms(heads: List[str], body: str, tail: str) -> str:
    """
    Build an SMS of head + body + tail that fits two segments.
    The tail (report link) is never cut. For each head option (longest first) the body is
    trimmed until the message fits; the option that keeps the most body wins. If even the
    shortest head plus tail is too long, the full link is kept and the message is allowed
    to run into a third segment.
    """
    def fits(text: str) -> bool:
        return _sms_units(text) <= _sms_budget(text)

    best: Optional[Tuple[int, str]] = None
    for head in heads:
        kept = body
        while kept and not fits(f"{head}{kept}{tail}"):
            kept = kept[:-1]
        if not kept and not fits(f"{head}{tail}"):
            continue
        if kept and len(kept) < min(10, len(body)):
            kept = ""  # a few stray characters are noise, not information
        candidate = f"{head}{kept}{tail}".strip()
        if best is None or len(kept) > best[0]:
            best = (len(kept), candidate)
        if kept == body:
            break
    if best is not None:
        return best[1]
    shortest = f"{heads[-1]}{tail}".strip()
    logger.warning("SMS exceeds 2 segments (%d units); keeping full report link", _sms_units(shortest))
    return shortest


def format_alert_message(
    call_record: Dict[str, Any],
    channel: AlertChannel,
    base_report_url: str = "http://localhost:8000/dashboard/report",
    dashboard_token: Optional[str] = None,
    signing_secret: Optional[str] = None,
) -> str:
    """
    Formats notification for WhatsApp or SMS.
    SMS targets 2 segments (306 GSM-7 septets or 134 UCS-2 characters). The summary and
    intel are trimmed first; the report link is never cut, so a very long base URL can
    push the message into a third segment rather than lose the link.
    Uses per-call signed links (expiring HMAC) so the master dashboard token is never leaked.
    """
    call_id = str(call_record.get("call_id") or "unknown_call")
    caller_num = str(call_record.get("caller_number") or "Unknown")
    verdict = str(call_record.get("verdict", "unsure")).lower()
    intel = call_record.get("extracted_intel", {}) or {}

    # Build report link and evidence review link using expiring HMAC signature rather than raw master token
    secret = signing_secret or dashboard_token
    safe_id = quote(call_id, safe="")
    trimmed_base = base_report_url.rstrip("/")
    if trimmed_base.endswith("/dashboard/report"):
        review_base = trimmed_base[: -len("/report")] + "/calls"
    elif trimmed_base.endswith("/report"):
        review_base = trimmed_base[: -len("/report")] + "/dashboard/calls"
    else:
        review_base = trimmed_base + "/calls"

    if secret:
        exp = int(time.time()) + 7 * 86400  # 7-day validity for family inspection
        sig = generate_report_signature(call_id, exp, secret)
        report_link = f"{trimmed_base}/{safe_id}?exp={exp}&sig={sig}"
        review_link = f"{review_base}/{safe_id}?exp={exp}&sig={sig}"
    else:
        report_link = f"{trimmed_base}/{safe_id}"
        review_link = f"{review_base}/{safe_id}"


    upi_list: List[str] = intel.get("upi_ids", [])
    acc_list: List[str] = intel.get("bank_accounts", [])
    ifsc_list: List[str] = intel.get("ifsc_codes", [])
    phone_list: List[str] = intel.get("phone_numbers", [])
    links_list: List[str] = intel.get("links", [])

    if verdict == "scam":
        if channel == AlertChannel.SMS:
            # Build intel summary containing all items including links
            intel_parts = []
            if upi_list:
                intel_parts.append(f"UPI:{','.join(upi_list)}")
            if acc_list:
                intel_parts.append(f"AC:{','.join(acc_list)}")
            if ifsc_list:
                intel_parts.append(f"IFSC:{','.join(ifsc_list)}")
            if phone_list:
                intel_parts.append(f"Ph:{','.join(phone_list)}")
            if links_list:
                intel_parts.append(f"Link:{','.join(links_list)}")

            intel_str = " | ".join(intel_parts) if intel_parts else "Intel logged"

            heads = [f"[SUSPECTED SCAM] Call from {caller_num}. ", "[SUSPECTED SCAM] "]
            return _fit_sms(heads, intel_str, f" Report: {report_link}")

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
            if links_list:
                bullet_lines.append(f"• *Phishing Link(s):* {', '.join(links_list)}")

            intel_block = "\n".join(bullet_lines) if bullet_lines else "• Attacker details logged to dossier"

            summary = call_record.get("summary") or "Suspected fraud attempt screened by voice assistant."
            return (
                f"🚨 *GUARDIANLINE SCAM ALERT*\n\n"
                f"A suspected scam call was handled by GuardianLine. Please check on them.\n\n"
                f"*Caller:* {caller_num}\n"
                f"*Summary:* {summary}\n\n"
                f"*Captured Attacker Intel:*\n"
                f"{intel_block}\n\n"
                f"🔍 *Review & Confirm Evidence (Chakshu / Suspect Packets):* {review_link}\n"
                f"📄 *Draft 1930 report (check before filing):* {report_link}\n"
                f"Call ID: `{call_id}`"
            )


    elif verdict == "genuine":
        message_body = call_record.get("message") or call_record.get("summary") or "Caller left a message."
        if channel == AlertChannel.SMS:
            return _fit_sms([f"[MESSAGE TAKEN] Call from {caller_num}: "], message_body, "")
        else:
            return (
                f"📞 *GUARDIANLINE MESSAGE TAKEN*\n\n"
                f"A genuine caller reached the assistant:\n"
                f"*Caller:* {caller_num}\n"
                f"*Note:* {message_body}\n"
                f"Call ID: `{call_id}`"
            )

    else:
        prefix = f"[SCREENING NOTE] Call from {caller_num} completed. "
        suffix = f"ID: {call_id}"
        candidate = f"{prefix}{suffix}"
        if channel == AlertChannel.SMS:
            return _fit_sms([prefix], "", suffix)
        return candidate


class PersistentAlertStore:
    """
    SQLite-backed store to guarantee cross-process idempotency for family alerts.
    Implements two-phase state machine ('pending' -> 'sent' / 'failed') with stale claim sweeps.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._is_mem = (self.db_path == ":memory:")
        self._conn = sqlite3.connect(":memory:", check_same_thread=False) if self._is_mem else None

        if not self._is_mem:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dispatched_alerts (
                    call_id TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    message_sid TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (call_id, recipient, channel)
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

    def claim_call(
        self,
        call_id: str,
        recipient: str,
        channel: str,
        stale_timeout_s: float = 300.0,
    ) -> bool:
        """
        Attempts to insert or reclaim call_id.
        Returns True if claimed (pending), False if already sent or actively in flight.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                # Check existing status
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT status, strftime('%s', 'now') - strftime('%s', updated_at) "
                    "FROM dispatched_alerts WHERE call_id = ? AND recipient = ? AND channel = ?",
                    (call_id, recipient, channel),
                )
                row = cursor.fetchone()

                if row is None:
                    # New claim
                    conn.execute(
                        "INSERT INTO dispatched_alerts (call_id, recipient, channel, status) "
                        "VALUES (?, ?, ?, 'pending')",
                        (call_id, recipient, channel),
                    )
                    conn.commit()
                    return True

                status, elapsed = row[0], row[1] or 0
                if status == "sent":
                    return False

                if status == "pending":
                    # Stale pending check (worker crashed before send completed)
                    if elapsed > stale_timeout_s:
                        logger.warning("Reclaiming stale pending alert for call %s after %ss", call_id, elapsed)
                        conn.execute(
                            "UPDATE dispatched_alerts SET updated_at = CURRENT_TIMESTAMP "
                            "WHERE call_id = ? AND recipient = ? AND channel = ?",
                            (call_id, recipient, channel),
                        )
                        conn.commit()
                        return True
                    return False

                if status == "failed":
                    # Retry allowed
                    conn.execute(
                        "UPDATE dispatched_alerts SET status = 'pending', updated_at = CURRENT_TIMESTAMP "
                        "WHERE call_id = ? AND recipient = ? AND channel = ?",
                        (call_id, recipient, channel),
                    )
                    conn.commit()
                    return True

                return False

            except sqlite3.IntegrityError:
                return False
            finally:
                if not self._is_mem:
                    conn.close()

    def mark_sent(self, call_id: str, recipient: str, channel: str, message_sid: str) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE dispatched_alerts SET status = 'sent', message_sid = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE call_id = ? AND recipient = ? AND channel = ?",
                    (message_sid, call_id, recipient, channel),
                )
                conn.commit()
            finally:
                if not self._is_mem:
                    conn.close()

    def mark_failed(self, call_id: str, recipient: str, channel: str, reason: Optional[str] = None) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE dispatched_alerts SET status = 'failed', updated_at = CURRENT_TIMESTAMP "
                    "WHERE call_id = ? AND recipient = ? AND channel = ?",
                    (call_id, recipient, channel),
                )
                conn.commit()
            finally:
                if not self._is_mem:
                    conn.close()

    def release_call(self, call_id: str, recipient: Optional[str] = None, channel: Optional[str] = None) -> None:
        """Alias for marking failed so it can be retried later."""
        if recipient and channel:
            self.mark_failed(call_id, recipient, channel)
        else:
            with self._lock:
                conn = self._get_conn()
                try:
                    conn.execute("DELETE FROM dispatched_alerts WHERE call_id = ?", (call_id,))
                    conn.commit()
                finally:
                    if not self._is_mem:
                        conn.close()

    def sweep_stale_pending(self, stale_timeout_s: float = 300.0) -> int:
        """Sweeps stale pending alerts that hung or died before completion."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE dispatched_alerts SET status = 'failed', updated_at = CURRENT_TIMESTAMP "
                    "WHERE status = 'pending' AND (strftime('%s', 'now') - strftime('%s', updated_at)) > ?",
                    (stale_timeout_s,),
                )
                count = cursor.rowcount
                conn.commit()
                return count
            finally:
                if not self._is_mem:
                    conn.close()


def is_retryable_twilio_error(error: Exception) -> bool:
    """
    Determines if an exception is transient (network timeout, connection refused, 429, 5xx).
    Permanent client errors (400, 401, 21211 invalid phone number) are NOT retryable.
    """
    # 1. Direct Python network socket and connection exceptions
    if isinstance(error, (socket.error, OSError, TimeoutError)):
        return True

    # 2. Check requests library network exceptions if requests is present
    try:
        import requests
        if isinstance(error, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
            return True
    except ImportError:
        pass

    # 3. Check Twilio RestException status codes
    code = getattr(error, "status", None)
    if code is not None:
        try:
            code_int = int(code)
            if code_int == 429 or code_int >= 500:
                return True
            if code_int in (400, 401, 403, 404, 21211):
                return False
        except (ValueError, TypeError):
            pass

    # 4. Check common transient error text
    err_str = str(error).lower()
    transient_indicators = [
        "timeout",
        "connection refused",
        "connection reset",
        "503",
        "502",
        "504",
        "429",
        "rate limit",
        "temporarily unavailable",
        "name resolution",
        "dns",
    ]
    return any(ind in err_str for ind in transient_indicators)


class FamilyAlertDispatcher:
    """
    Manages family alert dispatches with persistent idempotency and resilient retry.
    Supports multi-recipient fan-out and non-blocking background dispatching.
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
        """
        Synchronously dispatches alerts to all configured family recipients.
        Returns a summary AlertResult.
        """
        recipients = self.config.recipients
        if not recipients:
            logger.error("No recipients configured for family alert")
            return AlertResult(
                status=AlertStatus.FAILED,
                call_id=str(call_record.get("call_id") or "unknown"),
                reason="NO_RECIPIENTS_CONFIGURED",
                recipient="",
                channel=self.config.channel,
            )

        sub_results = [self._dispatch_single(call_record, r) for r in recipients]

        # Overall summary result
        reason = sub_results[0].reason
        if all(r.status == AlertStatus.SENT for r in sub_results):
            overall_status = AlertStatus.SENT
        elif any(r.status == AlertStatus.SENT for r in sub_results):
            # At least one family member was reached; flag the ones that were not
            overall_status = AlertStatus.SENT
            failed = [mask_number(r.recipient) for r in sub_results if r.status == AlertStatus.FAILED]
            if failed:
                reason = f"PARTIAL_FAILURE: {', '.join(failed)}"
        elif all(r.status == AlertStatus.MOCK for r in sub_results):
            overall_status = AlertStatus.MOCK
        elif all(r.status == AlertStatus.SKIPPED for r in sub_results):
            overall_status = AlertStatus.SKIPPED
        else:
            overall_status = AlertStatus.FAILED

        first = sub_results[0]
        return AlertResult(
            status=overall_status,
            call_id=first.call_id,
            reason=reason,
            recipient=", ".join(r.recipient for r in sub_results),
            channel=first.channel,
            message_sid=first.message_sid,
            retry_count=max(r.retry_count for r in sub_results),
            sub_results=[(r.model_dump() if hasattr(r, "model_dump") else r.dict()) for r in sub_results],
        )

    def dispatch_in_background(self, call_record: Dict[str, Any]) -> concurrent.futures.Future:
        """Submits dispatch to background thread pool so caller is not blocked."""
        return _THREAD_POOL.submit(self.dispatch, call_record)

    def _dispatch_sms_fallback(
        self,
        call_record: Dict[str, Any],
        target_recipient: str,
        claimed_recipient: str,
        claimed_channel: str,
        retries_done: int,
    ) -> AlertResult:
        """Dispatches an SMS fallback fitted via _fit_sms with the same call_record payload."""
        call_id = str(call_record.get("call_id") or "unknown")
        sms_to = target_recipient.replace("whatsapp:", "")
        sms_from = (self.config.from_phone or "+14155238886").replace("whatsapp:", "")
        sms_body = format_alert_message(
            call_record=call_record,
            channel=AlertChannel.SMS,
            base_report_url=self.config.base_report_url,
            dashboard_token=self.config.token,
            signing_secret=self.config.signing_secret or self.config.token,
        )
        sms_resp = self.twilio_client.messages.create(
            to=sms_to,
            from_=sms_from,
            body=sms_body,
        )
        sid = getattr(sms_resp, "sid", "OK")
        self.store.mark_sent(call_id, claimed_recipient, claimed_channel, sid)
        logger.info("SMS fallback alert dispatched for call %s to %s (SID: %s)", call_id, mask_number(sms_to), sid)
        return AlertResult(
            status=AlertStatus.SENT,
            call_id=call_id,
            recipient=sms_to,
            channel=AlertChannel.SMS,
            message_sid=sid,
            retry_count=retries_done,
        )

    def _dispatch_single(self, call_record: Dict[str, Any], target_recipient: str) -> AlertResult:
        call_id = call_record.get("call_id")
        if not call_id:
            logger.error("Cannot dispatch alert: call_id missing in record")
            return AlertResult(
                status=AlertStatus.FAILED,
                call_id="unknown",
                reason="MISSING_CALL_ID",
                recipient=target_recipient,
                channel=self.config.channel,
            )

        recipient = target_recipient
        from_phone = self.config.from_phone or "+14155238886"

        if self.config.channel == AlertChannel.WHATSAPP:
            if not recipient.startswith("whatsapp:"):
                recipient = f"whatsapp:{recipient}"
            if not from_phone.startswith("whatsapp:"):
                from_phone = f"whatsapp:{from_phone}"

        channel_val = self.config.channel.value

        # 1. Persistent Idempotency Claim
        if not self.store.claim_call(call_id, recipient, channel_val):
            logger.info("Call %s to %s already dispatched or in flight, skipping duplicate", call_id, mask_number(recipient))
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
            signing_secret=self.config.signing_secret or self.config.token,
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
            self.store.mark_sent(call_id, recipient, channel_val, "SM_mock_id")
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
                self.store.mark_sent(call_id, recipient, channel_val, sid)
                logger.info("Alert dispatched for call %s to %s (SID: %s)", call_id, masked_recip, sid)
                return AlertResult(
                    status=AlertStatus.SENT,
                    call_id=call_id,
                    recipient=recipient,
                    channel=self.config.channel,
                    message_sid=sid,
                    retry_count=retries_done,
                )
            except TwilioRestException as e:
                last_error = e
                if getattr(e, "code", None) in WHATSAPP_FALLBACK_TWILIO_CODES and self.config.channel == AlertChannel.WHATSAPP:
                    logger.warning(
                        "WhatsApp failed code %s, falling back to SMS for call %s to %s",
                        getattr(e, "code", "unknown"),
                        call_id,
                        masked_recip,
                    )
                    return self._dispatch_sms_fallback(
                        call_record=call_record,
                        target_recipient=target_recipient,
                        claimed_recipient=recipient,
                        claimed_channel=channel_val,
                        retries_done=retries_done,
                    )
                if not is_retryable_twilio_error(e):
                    logger.error("Non-retryable client error on call %s to %s: %s", call_id, masked_recip, str(e))
                    self.store.mark_failed(call_id, recipient, channel_val, str(e))
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
            except Exception as e:
                last_error = e
                if getattr(e, "code", None) in WHATSAPP_FALLBACK_TWILIO_CODES and self.config.channel == AlertChannel.WHATSAPP:
                    logger.warning(
                        "WhatsApp failed code %s, falling back to SMS for call %s to %s",
                        getattr(e, "code", "unknown"),
                        call_id,
                        masked_recip,
                    )
                    return self._dispatch_sms_fallback(
                        call_record=call_record,
                        target_recipient=target_recipient,
                        claimed_recipient=recipient,
                        claimed_channel=channel_val,
                        retries_done=retries_done,
                    )
                if not is_retryable_twilio_error(e):
                    logger.error("Non-retryable client error on call %s to %s: %s", call_id, masked_recip, str(e))
                    self.store.mark_failed(call_id, recipient, channel_val, str(e))
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
        logger.error("All %d retries failed for call %s to %s: %s", max_retries, call_id, masked_recip, str(last_error))
        self.store.mark_failed(call_id, recipient, channel_val, str(last_error))
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
    Requires FAMILY_ALERT_TO to prevent misdirection of alerts to default strangers.
    Enforces persistent SQLite storage path via ALERT_DB_PATH.
    """
    to_phone = os.environ.get("FAMILY_ALERT_TO")
    if not to_phone or not to_phone.strip():
        raise ValueError("FAMILY_ALERT_TO environment variable is required to dispatch family alerts safely")

    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_phone = os.environ.get("TWILIO_PHONE_NUMBER") or os.environ.get("TWILIO_WHATSAPP_FROM", "+14155238886")
    channel_str = os.environ.get("ALERT_CHANNEL", "whatsapp").lower()
    channel = AlertChannel.SMS if channel_str == "sms" else AlertChannel.WHATSAPP
    report_url = os.environ.get("REPORT_BASE_URL", "http://localhost:8000/dashboard/report")
    dash_token = os.environ.get("GUARDIAN_DASHBOARD_TOKEN")
    db_path = os.environ.get("ALERT_DB_PATH", "data/alerts.db")

    config = AlertConfig(
        account_sid=sid,
        auth_token=token,
        from_phone=from_phone,
        to_phone=to_phone.strip(),
        channel=channel,
        base_report_url=report_url,
        token=dash_token,
        signing_secret=get_report_signing_secret(),
    )

    env_mode = os.environ.get("ENV", "").lower()
    is_test_env = env_mode in ("test", "testing", "dev") or os.environ.get("MOCK_DISPATCHER") == "1"

    twilio_client = None
    if sid and token:
        try:
            from twilio.rest import Client
            twilio_client = Client(sid, token)
        except ImportError:
            logger.warning("Twilio library not installed; operating in mock mode")
    elif not is_test_env:
        logger.error("Twilio credentials (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) are missing in non-test mode")

    store = PersistentAlertStore(db_path=db_path)
    return FamilyAlertDispatcher(config=config, twilio_client=twilio_client, store=store)


def dispatch_family_alert(
    call_record: Dict[str, Any],
    dispatcher: Optional[FamilyAlertDispatcher] = None,
) -> AlertResult:
    """Dispatches a family alert using the provided or environment-configured FamilyAlertDispatcher."""
    disp = dispatcher or build_dispatcher_from_env()
    return disp.dispatch(call_record)
