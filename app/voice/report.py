"""
app/voice/report.py - 1930 National Cybercrime Reporting Portal Report Generator (T-RPT).

Generates a deterministic, human-readable 1930 cybercrime report from a finalized CallRecord.
Requirements (T-RPT):
  - Includes: scammer number, every UPI ID, bank account and IFSC, call date and time in IST,
    duration, summary, and a verification notice asking the family to check before reporting.
  - Any field the call did not capture prints "Not captured" — never a blank or a guess.
  - Covers all fields needed for a National Cybercrime Reporting Portal (cybercrime.gov.in / 1930)
    form walk-through without guessing uncaptured data.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

IST = timezone(timedelta(hours=5, minutes=30))

GENERATION_TIME_PLACEHOLDER = "<GENERATED_AT_IST>"


def _format_ist_timestamp(iso_str: Optional[str]) -> str:
    """Convert an ISO-8601 timestamp to 'YYYY-MM-DD HH:MM:SS IST', or 'Not captured'."""
    if not iso_str or not isinstance(iso_str, str) or not iso_str.strip():
        return "Not captured"
    raw = iso_str.strip()
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ist_dt = dt.astimezone(IST)
        return ist_dt.strftime("%Y-%m-%d %H:%M:%S IST")
    except Exception:
        return "Not captured"


def _format_duration(seconds: Any) -> str:
    """Format call duration in seconds into a human-readable string, or 'Not captured'."""
    if seconds is None or not isinstance(seconds, (int, float)) or seconds < 0:
        return "Not captured"
    total_sec = float(seconds)
    mins = int(total_sec) // 60
    rem_sec = int(total_sec) % 60
    return f"{total_sec:.1f} seconds ({mins:02d}m {rem_sec:02d}s)"


def _format_list_field(values: Optional[List[str]]) -> str:
    """Format a list of extracted strings or return 'Not captured' if empty."""
    if not values:
        return "Not captured"
    cleaned = [str(v).strip() for v in values if str(v).strip()]
    if not cleaned:
        return "Not captured"
    return ", ".join(cleaned)


def _format_str_field(val: Optional[str]) -> str:
    """Return stripped non-empty string or 'Not captured'."""
    if not val or not isinstance(val, str) or not val.strip():
        return "Not captured"
    return val.strip()


def generate_1930_report(
    record: Dict[str, Any],
    generated_at_ist: Optional[str] = None,
    mask_generation_time: bool = False,
) -> str:
    """
    Generate the pre-filled 1930 / National Cybercrime Reporting Portal text report
    for a CallRecord.

    If `mask_generation_time=True`, substitutes `<GENERATED_AT_IST>` for the report
    generation timestamp so golden-file comparisons are 100% deterministic.
    """
    if mask_generation_time:
        gen_time_str = GENERATION_TIME_PLACEHOLDER
    elif generated_at_ist:
        gen_time_str = generated_at_ist
    else:
        gen_time_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

    call_id = _format_str_field(record.get("call_id"))
    verdict = _format_str_field(record.get("verdict"))
    caller_number = _format_str_field(record.get("caller_number"))
    call_datetime_ist = _format_ist_timestamp(record.get("start_time") or record.get("created_at"))
    raw_duration = record.get("duration") if record.get("duration") is not None else record.get("call_duration")
    duration_str = _format_duration(raw_duration)
    summary_str = _format_str_field(record.get("summary"))

    intel = record.get("extracted_intel") or {}
    upi_str = _format_list_field(intel.get("upi_ids"))
    account_str = _format_list_field(intel.get("bank_accounts"))
    ifsc_str = _format_list_field(intel.get("ifsc_codes"))
    phone_str = _format_list_field(intel.get("phone_numbers"))
    pan_str = _format_list_field(intel.get("pan_numbers"))
    link_str = _format_list_field(intel.get("links"))

    lines = [
        "========================================================================",
        "         GUARDIANLINE — 1930 CYBERCRIME INCIDENT REPORT DRAFT",
        "     (National Cybercrime Reporting Portal / Helpline 1930 Reference)",
        "========================================================================",
        f"Report Generated At (IST) : {gen_time_str}",
        f"Call Reference ID         : {call_id}",
        f"Incident Classification   : {verdict}",
        "------------------------------------------------------------------------",
        "1. INCIDENT TIMELINE & CALL METADATA",
        "------------------------------------------------------------------------",
        f"Call Date & Time (IST)    : {call_datetime_ist}",
        f"Call Duration             : {duration_str}",
        f"Suspect / Scammer Number  : {caller_number}",
        "Incident Category         : Online Financial Fraud / Impersonation Scam Call",
        "Money Lost by Victim      : INR 0 (Intercepted by GuardianLine Honeypot)",
        "------------------------------------------------------------------------",
        "2. SUSPECT FINANCIAL & CONTACT IDENTIFIERS (FOR 1930 / NCRP FORM)",
        "------------------------------------------------------------------------",
        f"UPI IDs                   : {upi_str}",
        f"Bank Account Numbers      : {account_str}",
        f"IFSC Codes                : {ifsc_str}",
        f"Suspect Phone Numbers     : {phone_str}",
        f"PAN Numbers               : {pan_str}",
        f"Suspicious Links / URLs   : {link_str}",
        "------------------------------------------------------------------------",
        "3. INCIDENT SUMMARY",
        "------------------------------------------------------------------------",
        f"{summary_str}",
        "------------------------------------------------------------------------",
        "4. FAMILY VERIFICATION NOTICE (READ BEFORE REPORTING)",
        "------------------------------------------------------------------------",
        "IMPORTANT: Please review and verify every field in this pre-filled report",
        "with your family before calling 1930 or submitting a complaint on the",
        "National Cybercrime Reporting Portal (https://cybercrime.gov.in).",
        "Fields marked 'Not captured' were not spoken during the call — do not",
        "guess or fill in unverified values.",
        "========================================================================",
    ]
    return "\n".join(lines) + "\n"


def mask_report_generation_time(report_text: str) -> str:
    """Replace any concrete 'Report Generated At (IST) : ...' timestamp with the placeholder."""
    return re.sub(
        r"^Report Generated At \(IST\) : .*$",
        f"Report Generated At (IST) : {GENERATION_TIME_PLACEHOLDER}",
        report_text,
        flags=re.MULTILINE,
    )
