"""
app/voice/store.py - SQLite CallRecord Store & `call.finalized` Event Bus (T-HOOK, T-TOOLS, T-PRIV).
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_LOCK = threading.RLock()
_CUSTOM_DB_PATH: Optional[str] = None
_FINALIZED_LISTENERS: List[Callable[[Dict[str, Any]], None]] = []
_FINALIZED_EVENTS_LOG: List[Dict[str, Any]] = []


def mask_phone(phone: Optional[str]) -> str:
    """
    Mask all but the last 4 digits of a caller phone number for privacy-safe logging (T-PRIV).
    Example: '+919876543210' -> '*********3210'
    """
    if not phone:
        return "<withheld>"
    s = str(phone).strip()
    if len(s) <= 4:
        return "****"
    return "*" * (len(s) - 4) + s[-4:]


def get_db_path() -> str:
    if _CUSTOM_DB_PATH:
        return _CUSTOM_DB_PATH
    return os.getenv("GUARDIANLINE_DB_PATH", "guardianline_calls.db")


def set_db_path(path: Optional[str]) -> None:
    """Override the SQLite database path (used by integration tests for throwaway DBs)."""
    global _CUSTOM_DB_PATH
    with _DB_LOCK:
        _CUSTOM_DB_PATH = path
        if path:
            init_db(path)


def register_call_finalized_listener(listener: Callable[[Dict[str, Any]], None]) -> None:
    """Register a callback invoked once whenever a CallRecord is finalized."""
    if listener not in _FINALIZED_LISTENERS:
        _FINALIZED_LISTENERS.append(listener)


def clear_call_finalized_events() -> None:
    """Clear in-memory finalized event history (for test assertions)."""
    _FINALIZED_EVENTS_LOG.clear()


def get_call_finalized_events(call_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return recorded `call.finalized` events, optionally filtered by `call_id`."""
    if call_id is None:
        return list(_FINALIZED_EVENTS_LOG)
    return [e for e in _FINALIZED_EVENTS_LOG if e.get("call_id") == call_id]


def _get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    target = db_path or get_db_path()
    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    with _DB_LOCK:
        conn = _get_conn(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS call_records (
                    call_id TEXT PRIMARY KEY,
                    agent_id TEXT,
                    caller_number TEXT,
                    caller_number_missing INTEGER DEFAULT 1,
                    start_time TEXT,
                    duration REAL DEFAULT 0,
                    verdict TEXT DEFAULT 'unsure',
                    confidence REAL DEFAULT 0.5,
                    honeypot_switch_time TEXT,
                    persona TEXT DEFAULT '',
                    persona_bundle_json TEXT,
                    language TEXT DEFAULT 'hi',
                    call_recording_url TEXT DEFAULT '',
                    transcript_json TEXT DEFAULT '[]',
                    extracted_intel_json TEXT DEFAULT '{}',
                    summary TEXT DEFAULT '',
                    report_link TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    finalized_fired INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def _empty_intel() -> Dict[str, Any]:
    return {
        "upi_ids": [],
        "phone_numbers": [],
        "bank_accounts": [],
        "ifsc_codes": [],
        "pan_numbers": [],
        "links": [],
        "entity_counts": {},
        "mid_call_logs": [],
    }


def _row_to_record(row: sqlite3.Row) -> Dict[str, Any]:
    intel = json.loads(row["extracted_intel_json"] or "{}")
    for k, default_v in _empty_intel().items():
        if k not in intel:
            intel[k] = default_v
    transcript = json.loads(row["transcript_json"] or "[]")
    return {
        "call_id": row["call_id"],
        "agent_id": row["agent_id"] or "bolna_agent_guardianline_v0",
        "caller_number": row["caller_number"] or "",
        "caller_number_missing": bool(row["caller_number_missing"]),
        "start_time": row["start_time"] or row["created_at"] or datetime.now(timezone.utc).isoformat(),
        "duration": float(row["duration"] or 0.0),
        "verdict": row["verdict"] or "unsure",
        "confidence": float(row["confidence"] or 0.5),
        "honeypot_switch_time": row["honeypot_switch_time"],
        "persona": row["persona"] or "screening_receptionist",
        "language": row["language"] or "hi",
        "call_recording_url": row["call_recording_url"] or "",
        "transcript": transcript,
        "extracted_intel": intel,
        "summary": row["summary"] or "",
        "report_link": row["report_link"] or f"/api/calls/{row['call_id']}/report",
        "status": row["status"] or "pending",
    }


def get_call_record(call_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM call_records WHERE call_id = ?", (call_id,)
            ).fetchone()
            if not row:
                return None
            return _row_to_record(row)
        finally:
            conn.close()


def list_call_records(
    limit: int = 50,
    verdict: Optional[str] = None,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            if verdict:
                rows = conn.execute(
                    "SELECT * FROM call_records WHERE verdict = ? ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
                    (verdict, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM call_records ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [_row_to_record(r) for r in rows]
        finally:
            conn.close()


def get_or_assign_honeypot_persona(
    call_id: str,
    bundle_factory: Callable[[], Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Idempotently store and return the persona bundle for `call_id`.
    If `switch_to_honeypot` was already called for `call_id`, returns the stored bundle.
    """
    init_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT persona_bundle_json FROM call_records WHERE call_id = ?",
                (call_id,),
            ).fetchone()
            if row and row["persona_bundle_json"]:
                saved_bundle = json.loads(row["persona_bundle_json"])
                return saved_bundle

            bundle = bundle_factory()
            bundle_json = json.dumps(bundle, ensure_ascii=False)
            if row:
                conn.execute(
                    """
                    UPDATE call_records
                    SET persona = ?,
                        persona_bundle_json = ?,
                        language = ?,
                        verdict = 'scam',
                        honeypot_switch_time = COALESCE(honeypot_switch_time, ?),
                        updated_at = ?
                    WHERE call_id = ?
                    """,
                    (
                        bundle["persona_id"],
                        bundle_json,
                        bundle["language"],
                        now_iso,
                        now_iso,
                        call_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO call_records (
                        call_id, agent_id, caller_number, caller_number_missing,
                        start_time, duration, verdict, confidence, honeypot_switch_time,
                        persona, persona_bundle_json, language, transcript_json,
                        extracted_intel_json, summary, report_link, status,
                        finalized_fired, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        call_id,
                        "bolna_agent_guardianline_v0",
                        "",
                        1,
                        now_iso,
                        0.0,
                        "scam",
                        0.95,
                        now_iso,
                        bundle["persona_id"],
                        bundle_json,
                        bundle["language"],
                        "[]",
                        json.dumps(_empty_intel()),
                        "",
                        f"/api/calls/{call_id}/report",
                        "pending",
                        now_iso,
                        now_iso,
                    ),
                )
            conn.commit()
            return bundle
        finally:
            conn.close()


def append_mid_call_intel(
    call_id: str,
    intel_type: str,
    value_as_heard: str,
    normalized_value: str,
    unparseable: bool,
) -> Dict[str, Any]:
    """
    Append a mid-call `log_intel` capture to the CallRecord for `call_id`.
    Creates a `pending` CallRecord if one does not exist yet.
    """
    init_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    log_entry = {
        "type": intel_type,
        "value_as_heard": value_as_heard,
        "normalized_value": normalized_value,
        "unparseable": unparseable,
    }
    with _DB_LOCK:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT extracted_intel_json FROM call_records WHERE call_id = ?",
                (call_id,),
            ).fetchone()
            if row:
                intel = json.loads(row["extracted_intel_json"] or "{}")
                for k, default_v in _empty_intel().items():
                    if k not in intel:
                        intel[k] = default_v
            else:
                intel = _empty_intel()

            intel["mid_call_logs"].append(log_entry)
            if not unparseable and normalized_value:
                bucket_map = {
                    "upi": "upi_ids",
                    "phone": "phone_numbers",
                    "account": "bank_accounts",
                    "ifsc": "ifsc_codes",
                    "pan": "pan_numbers",
                    "link": "links",
                }
                bucket = bucket_map.get(intel_type)
                if bucket:
                    if normalized_value not in intel[bucket]:
                        intel[bucket].append(normalized_value)
                    counts = intel.get("entity_counts", {})
                    counts[normalized_value] = counts.get(normalized_value, 0) + 1
                    intel["entity_counts"] = counts

            intel_json = json.dumps(intel, ensure_ascii=False)
            if row:
                conn.execute(
                    "UPDATE call_records SET extracted_intel_json = ?, updated_at = ? WHERE call_id = ?",
                    (intel_json, now_iso, call_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO call_records (
                        call_id, agent_id, caller_number, caller_number_missing,
                        start_time, duration, verdict, confidence, honeypot_switch_time,
                        persona, language, transcript_json, extracted_intel_json,
                        summary, report_link, status, finalized_fired, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        call_id,
                        "bolna_agent_guardianline_v0",
                        "",
                        1,
                        now_iso,
                        0.0,
                        "unsure",
                        0.5,
                        None,
                        "screening_receptionist",
                        "hi",
                        "[]",
                        intel_json,
                        "",
                        f"/api/calls/{call_id}/report",
                        "pending",
                        now_iso,
                        now_iso,
                    ),
                )
            conn.commit()
            return log_entry
        finally:
            conn.close()


def finalize_call_record_from_webhook(
    payload: Dict[str, Any],
    extracted_intel: Dict[str, Any],
    verdict: str,
    confidence: float,
    summary: str,
    status_value: str = "finalized",
) -> Dict[str, Any]:
    """
    Create or update the CallRecord from the post-call webhook payload, merging any
    pending mid-call state, and fire `call.finalized` at most once per `call_id`.
    """
    init_db()
    call_id = str(payload["call_id"])
    now_iso = datetime.now(timezone.utc).isoformat()
    caller_number = str(payload.get("caller_number") or "").strip()
    caller_missing = 1 if not caller_number else 0
    duration = float(payload.get("call_duration") or 0.0)
    agent_id = str(payload.get("agent_id") or "bolna_agent_guardianline_v0")
    recording_url = str(payload.get("call_recording_url") or "")
    transcript = payload.get("transcript") or []
    metadata = payload.get("metadata") or {}
    language = str(metadata.get("language") or "hi")
    meta_persona = str(metadata.get("persona") or "")

    start_time_val = str(
        payload.get("created_at")
        or payload.get("start_time")
        or metadata.get("created_at")
        or now_iso
    )

    should_fire_event = False
    event_payload: Optional[Dict[str, Any]] = None

    with _DB_LOCK:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM call_records WHERE call_id = ?",
                (call_id,),
            ).fetchone()

            if row and row["finalized_fired"] and row["status"] == "finalized":
                # Duplicate webhook delivery: return existing record without firing a second event
                logger.info(
                    "Duplicate webhook ignored for call_id=%s caller=%s",
                    call_id,
                    mask_phone(caller_number),
                )
                return _row_to_record(row)

            already_fired = bool(row["finalized_fired"]) if row else False
            honeypot_switch_time = row["honeypot_switch_time"] if row else None
            persona = (
                (row["persona"] if row and row["persona"] != "screening_receptionist" else None)
                or meta_persona
                or ("ramesh" if verdict == "scam" else "screening_receptionist")
            )
            if verdict == "scam" and not honeypot_switch_time:
                honeypot_switch_time = start_time_val

            report_link = f"/api/calls/{call_id}/report"
            transcript_json = json.dumps(transcript, ensure_ascii=False)
            intel_json = json.dumps(extracted_intel, ensure_ascii=False)

            if row:
                conn.execute(
                    """
                    UPDATE call_records
                    SET agent_id = ?,
                        caller_number = ?,
                        caller_number_missing = ?,
                        start_time = ?,
                        duration = ?,
                        verdict = ?,
                        confidence = ?,
                        honeypot_switch_time = ?,
                        persona = ?,
                        language = ?,
                        call_recording_url = ?,
                        transcript_json = ?,
                        extracted_intel_json = ?,
                        summary = ?,
                        report_link = ?,
                        status = ?,
                        finalized_fired = 1,
                        updated_at = ?
                    WHERE call_id = ?
                    """,
                    (
                        agent_id,
                        caller_number,
                        caller_missing,
                        start_time_val,
                        duration,
                        verdict,
                        confidence,
                        honeypot_switch_time,
                        persona,
                        language,
                        recording_url,
                        transcript_json,
                        intel_json,
                        summary,
                        report_link,
                        status_value,
                        now_iso,
                        call_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO call_records (
                        call_id, agent_id, caller_number, caller_number_missing,
                        start_time, duration, verdict, confidence, honeypot_switch_time,
                        persona, language, call_recording_url, transcript_json,
                        extracted_intel_json, summary, report_link, status,
                        finalized_fired, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        call_id,
                        agent_id,
                        caller_number,
                        caller_missing,
                        start_time_val,
                        duration,
                        verdict,
                        confidence,
                        honeypot_switch_time,
                        persona,
                        language,
                        recording_url,
                        transcript_json,
                        intel_json,
                        summary,
                        report_link,
                        status_value,
                        now_iso,
                        now_iso,
                    ),
                )
            conn.commit()
            updated_row = conn.execute(
                "SELECT * FROM call_records WHERE call_id = ?", (call_id,)
            ).fetchone()
            record = _row_to_record(updated_row)

            if not already_fired:
                should_fire_event = True
                event_payload = {
                    "event": "call.finalized",
                    "call_id": call_id,
                    "verdict": record["verdict"],
                    "caller_number": record["caller_number"],
                    "timestamp": now_iso,
                    "report_link": record["report_link"],
                    "extracted_intel": record["extracted_intel"],
                }
        finally:
            conn.close()

    if should_fire_event and event_payload:
        _FINALIZED_EVENTS_LOG.append(event_payload)
        logger.info(
            "Fired call.finalized for call_id=%s verdict=%s caller=%s",
            call_id,
            event_payload["verdict"],
            mask_phone(caller_number),
        )
        for listener in list(_FINALIZED_LISTENERS):
            try:
                listener(event_payload)
            except Exception as exc:
                logger.error("Error in call.finalized listener for call_id=%s: %s", call_id, exc)

    return record


def save_post_call_enrichment_and_reflection(
    call_id: str,
    reflection: Optional[Dict[str, Any]] = None,
    enrichment: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Attach post-call `reflection` and `enrichment` results onto an already-saved CallRecord
    without altering `status`, `verdict`, `summary`, or `finalized_fired` (T-POST).
    """
    init_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM call_records WHERE call_id = ?",
                (call_id,),
            ).fetchone()
            if not row:
                return None
            intel = json.loads(row["extracted_intel_json"] or "{}")
            for k, default_v in _empty_intel().items():
                if k not in intel:
                    intel[k] = default_v
            if reflection is not None:
                intel["reflection"] = reflection
            if enrichment is not None:
                intel["enrichment"] = enrichment

            intel_json = json.dumps(intel, ensure_ascii=False)
            conn.execute(
                "UPDATE call_records SET extracted_intel_json = ?, updated_at = ? WHERE call_id = ?",
                (intel_json, now_iso, call_id),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM call_records WHERE call_id = ?",
                (call_id,),
            ).fetchone()
            return _row_to_record(updated)
        finally:
            conn.close()


CSV_EXPORT_FIELDNAMES = [
    "call_id",
    "scenario_id",
    "language",
    "caller_number",
    "final_verdict",
    "verdict",
    "confidence",
    "switched_to_honeypot",
    "persona",
    "total_turns",
    "call_duration",
    "upi_ids",
    "phone_numbers",
    "bank_accounts",
    "ifsc_codes",
    "pan_numbers",
    "links",
    "bait_leaks",
    "adversarial_leaks",
    "status",
    "summary",
    "start_time",
]


def export_call_records_to_csv_string() -> str:
    """
    Export all stored CallRecords as a CSV string compatible with `scripts/compute_metrics.py`
    (Sprint 3 & 4 metrics pipeline).
    """
    import csv
    import io

    records = list_call_records(limit=10000, offset=0)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_EXPORT_FIELDNAMES)
    writer.writeheader()
    for rec in records:
        intel = rec.get("extracted_intel") or {}
        switched = bool(rec.get("honeypot_switch_time")) or rec.get("verdict") == "scam"
        writer.writerow(
            {
                "call_id": rec.get("call_id", ""),
                "scenario_id": rec.get("call_id", ""),
                "language": rec.get("language", "hi"),
                "caller_number": rec.get("caller_number", ""),
                "final_verdict": rec.get("verdict", "unsure"),
                "verdict": rec.get("verdict", "unsure"),
                "confidence": rec.get("confidence", 0.5),
                "switched_to_honeypot": str(switched),
                "persona": rec.get("persona", ""),
                "total_turns": len(rec.get("transcript") or []),
                "call_duration": rec.get("duration", 0.0),
                "upi_ids": ";".join(intel.get("upi_ids") or []),
                "phone_numbers": ";".join(intel.get("phone_numbers") or []),
                "bank_accounts": ";".join(intel.get("bank_accounts") or []),
                "ifsc_codes": ";".join(intel.get("ifsc_codes") or []),
                "pan_numbers": ";".join(intel.get("pan_numbers") or []),
                "links": ";".join(intel.get("links") or []),
                "bait_leaks": 0,
                "adversarial_leaks": 0,
                "status": rec.get("status", "finalized"),
                "summary": rec.get("summary", ""),
                "start_time": rec.get("start_time", ""),
            }
        )
    return buf.getvalue()


def export_call_records_csv(csv_path: str) -> str:
    """Write all CallRecords to `csv_path` and return the path."""
    content = export_call_records_to_csv_string()
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    return csv_path


def backup_call_records_db(backup_path: str) -> str:
    """
    Create a safe, consistent online SQLite backup of the active CallRecord database
    using `sqlite3.Connection.backup()` (Sprint 4 backup requirement).
    """
    init_db()
    abs_target = os.path.abspath(backup_path)
    os.makedirs(os.path.dirname(abs_target), exist_ok=True)
    with _DB_LOCK:
        src_conn = _get_conn()
        dst_conn = sqlite3.connect(abs_target)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()
    logger.info("SQLite database backed up safely to %s", abs_target)
    return abs_target

