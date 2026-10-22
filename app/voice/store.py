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


_PG_RESTORED: bool = False


def _get_pg_conn():
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url or _CUSTOM_DB_PATH is not None:
        return None
    try:
        import psycopg2
        if db_url.startswith("postgres://"):
            db_url = "postgresql://" + db_url[len("postgres://") :]
        return psycopg2.connect(db_url)
    except Exception as exc:
        logger.warning("Postgres mirror connection unavailable: %s", exc)
        return None


def _sync_sqlite_row_to_pg(conn: sqlite3.Connection, call_id: str) -> None:
    pg_conn = _get_pg_conn()
    if pg_conn is None:
        return
    try:
        row = conn.execute("SELECT * FROM call_records WHERE call_id = ?", (call_id,)).fetchone()
        if not row:
            return
        row_dict = {k: row[k] for k in row.keys()}
        row_json = json.dumps(row_dict, ensure_ascii=False)
        with pg_conn:
            with pg_conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS guardianline_call_records_mirror (
                        call_id TEXT PRIMARY KEY,
                        row_json TEXT NOT NULL,
                        updated_at TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO guardianline_call_records_mirror (call_id, row_json, updated_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (call_id) DO UPDATE
                    SET row_json = EXCLUDED.row_json,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (call_id, row_json, row_dict.get("updated_at") or ""),
                )
    except Exception as exc:
        logger.warning("Postgres mirror sync failed for call_id=%s: %s", call_id, exc)
    finally:
        try:
            pg_conn.close()
        except Exception:
            pass


def _restore_from_pg_if_needed(conn: sqlite3.Connection) -> None:
    global _PG_RESTORED
    if _PG_RESTORED or _CUSTOM_DB_PATH is not None:
        return
    _PG_RESTORED = True
    pg_conn = _get_pg_conn()
    if pg_conn is None:
        return
    try:
        with pg_conn:
            with pg_conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS guardianline_call_records_mirror (
                        call_id TEXT PRIMARY KEY,
                        row_json TEXT NOT NULL,
                        updated_at TEXT
                    )
                    """
                )
                cur.execute("SELECT row_json FROM guardianline_call_records_mirror")
                pg_rows = cur.fetchall()
        for (r_json,) in pg_rows:
            d = json.loads(r_json)
            cols = list(d.keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            conn.execute(
                f"INSERT OR IGNORE INTO call_records ({col_names}) VALUES ({placeholders})",
                [d[c] for c in cols],
            )
        conn.commit()
        if pg_rows:
            logger.info("Restored %d CallRecords from DATABASE_URL Postgres mirror into SQLite", len(pg_rows))
    except Exception as exc:
        logger.warning("Postgres mirror restore failed: %s", exc)
    finally:
        try:
            pg_conn.close()
        except Exception:
            pass


# Columns added after the original schema; ALTERed onto existing databases in init_db().
_ADDED_COLUMNS = [
    ("stage2_ran", "INTEGER"),  # NULL = unknown (pending / pre-flag records)
    ("classifier_method", "TEXT DEFAULT ''"),
    ("transcript_sha256", "TEXT DEFAULT NULL"),
    ("recording_sha256", "TEXT DEFAULT NULL"),
    ("recording_hash_error", "TEXT DEFAULT NULL"),
    ("hashed_at", "TEXT DEFAULT NULL"),
    ("money_lost", "INTEGER DEFAULT 0"),
    ("evidence_status", "TEXT DEFAULT 'draft'"),
    ("confirmed_at", "TEXT DEFAULT NULL"),
]


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
            existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(call_records)").fetchall()}
            for col, ddl in _ADDED_COLUMNS:
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE call_records ADD COLUMN {col} {ddl}")
            conn.commit()
            _restore_from_pg_if_needed(conn)
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
    row_keys = row.keys()
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
        "stage2_ran": None if row["stage2_ran"] is None else bool(row["stage2_ran"]),
        "classifier_method": row["classifier_method"] or "",
        "transcript_sha256": row["transcript_sha256"] if "transcript_sha256" in row_keys else None,
        "recording_sha256": row["recording_sha256"] if "recording_sha256" in row_keys else None,
        "recording_hash_error": row["recording_hash_error"] if "recording_hash_error" in row_keys else None,
        "hashed_at": row["hashed_at"] if "hashed_at" in row_keys else None,
        "money_lost": bool(row["money_lost"]) if "money_lost" in row_keys and row["money_lost"] is not None else False,
        "evidence_status": row["evidence_status"] if "evidence_status" in row_keys and row["evidence_status"] else "draft",
        "confirmed_at": row["confirmed_at"] if "confirmed_at" in row_keys else None,
    }


_PLACEHOLDER_ID_VALUES = {
    "",
    "null",
    "none",
    "undefined",
    "%(execution_id)s",
    "%(call_sid)s",
    "%(call_id)s",
}


def is_placeholder_id(value: Optional[str]) -> bool:
    """Return True if `value` is empty or an un-interpolated template/placeholder like `%(execution_id)s`."""
    if value is None:
        return True
    cleaned = str(value).strip()
    if not cleaned:
        return True
    lower = cleaned.lower()
    if lower in _PLACEHOLDER_ID_VALUES:
        return True
    if cleaned.startswith("%(") or cleaned.startswith("{{") or cleaned.startswith("${"):
        return True
    return False


def resolve_effective_tool_call_id(
    call_id: str,
    execution_id: Optional[str] = None,
) -> str:
    """
    Resolve the primary CallRecord key for a mid-call tool request:
      1. If `execution_id` is provided and not a literal placeholder (`%(execution_id)s`),
         use `execution_id` first so it joins directly with the webhook's `id`.
      2. Otherwise fall back to `call_id` (e.g., `%(call_sid)s` -> `telephony_data.provider_call_id`).
    """
    if not is_placeholder_id(execution_id):
        return str(execution_id).strip()
    return str(call_id).strip()


def _merge_intel_dicts(base_intel: Dict[str, Any], extra_intel: Dict[str, Any]) -> Dict[str, Any]:
    merged = _empty_intel()
    for src in (base_intel, extra_intel):
        if not isinstance(src, dict):
            continue
        for bucket in ("upi_ids", "phone_numbers", "bank_accounts", "ifsc_codes", "pan_numbers", "links"):
            for item in src.get(bucket, []):
                if item not in merged[bucket]:
                    merged[bucket].append(item)
        for log_entry in src.get("mid_call_logs", []):
            if log_entry not in merged["mid_call_logs"]:
                merged["mid_call_logs"].append(log_entry)
        for k, v in (src.get("entity_counts") or {}).items():
            merged["entity_counts"][k] = merged["entity_counts"].get(k, 0) + int(v)
        if src.get("enrichment"):
            merged["enrichment"].update(src["enrichment"])
        if src.get("reflection"):
            merged["reflection"].update(src["reflection"])
    return merged


def _adopt_or_merge_pending_row(conn: sqlite3.Connection, target_call_id: str, source_call_id: str) -> None:
    """
    Rename pending record `source_call_id` -> `target_call_id` (or merge into existing `target_call_id`
    if both exist) and remove `source_call_id`.
    """
    if source_call_id == target_call_id:
        return
    src_row = conn.execute(
        "SELECT * FROM call_records WHERE call_id = ?", (source_call_id,)
    ).fetchone()
    if not src_row:
        return

    tgt_row = conn.execute(
        "SELECT * FROM call_records WHERE call_id = ?", (target_call_id,)
    ).fetchone()

    if not tgt_row:
        bundle_json = src_row["persona_bundle_json"]
        if bundle_json:
            try:
                b = json.loads(bundle_json)
                if isinstance(b, dict):
                    b["call_id"] = target_call_id
                    bundle_json = json.dumps(b, ensure_ascii=False)
            except Exception:
                pass
        conn.execute(
            """
            UPDATE call_records
            SET call_id = ?,
                persona_bundle_json = ?,
                report_link = ?
            WHERE call_id = ?
            """,
            (target_call_id, bundle_json, f"/api/calls/{target_call_id}/report", source_call_id),
        )
    else:
        tgt_intel = json.loads(tgt_row["extracted_intel_json"] or "{}")
        src_intel = json.loads(src_row["extracted_intel_json"] or "{}")
        merged_intel = _merge_intel_dicts(tgt_intel, src_intel)

        persona = (
            tgt_row["persona"]
            if tgt_row["persona"] and tgt_row["persona"] != "screening_receptionist"
            else src_row["persona"]
        )
        bundle_json = tgt_row["persona_bundle_json"] or src_row["persona_bundle_json"]
        switch_time = tgt_row["honeypot_switch_time"] or src_row["honeypot_switch_time"]
        verdict = "scam" if (tgt_row["verdict"] == "scam" or src_row["verdict"] == "scam") else tgt_row["verdict"]

        conn.execute(
            """
            UPDATE call_records
            SET persona = ?,
                persona_bundle_json = ?,
                honeypot_switch_time = ?,
                verdict = ?,
                extracted_intel_json = ?
            WHERE call_id = ?
            """,
            (
                persona,
                bundle_json,
                switch_time,
                verdict,
                json.dumps(merged_intel, ensure_ascii=False),
                target_call_id,
            ),
        )
        conn.execute("DELETE FROM call_records WHERE call_id = ?", (source_call_id,))
    conn.commit()
    _sync_sqlite_row_to_pg(conn, target_call_id)


SMOKE_CALL_ID_PREFIX = "smoke_"


def resolve_and_merge_pending_mid_call_record(
    call_id: str,
    provider_call_id: Optional[str] = None,
    active_window_seconds: int = 900,
) -> Optional[Dict[str, Any]]:
    """
    Locate and join any pending mid-call record (`switch_to_honeypot` / `log_intel`)
    for an incoming post-call webhook using the strict 3-step join priority:
      (a) Primary: `call_id` (matches `execution_id` when tool sent a real `execution_id`)
      (b) Secondary: `provider_call_id` (`telephony_data.provider_call_id` matching tool `%(call_sid)s`)
      (c) Fallback: ONLY when neither (a) nor (b) matched AND there is **exactly one**
          unfinalized `status='pending'` record active within `active_window_seconds`,
          merge it and log a WARNING. If 0 or >1 pending records exist, do not guess.
    """
    init_db()
    prov_id = str(provider_call_id or "").strip()
    now_utc = datetime.now(timezone.utc)

    with _DB_LOCK:
        conn = _get_conn()
        try:
            # Rule (a): Direct match on webhook `id` / `execution_id`
            row_a = conn.execute(
                "SELECT * FROM call_records WHERE call_id = ?", (call_id,)
            ).fetchone()
            if row_a and row_a["status"] == "finalized":
                return _row_to_record(row_a)

            # Rule (b): Match on `telephony_data.provider_call_id` (from `%(call_sid)s`)
            matched_b = False
            if prov_id and prov_id != call_id:
                row_b = conn.execute(
                    "SELECT * FROM call_records WHERE call_id = ? AND status = 'pending'",
                    (prov_id,),
                ).fetchone()
                if row_b:
                    matched_b = True
                    logger.info(
                        "Joined pending mid-call record via provider_call_id=%s -> call_id=%s",
                        prov_id,
                        call_id,
                    )
                    _adopt_or_merge_pending_row(conn, call_id, prov_id)

            # Rule (c): Fallback single-active-call window join (ONLY if neither a nor b matched)
            if not row_a and not matched_b:
                pending_rows = conn.execute(
                    "SELECT * FROM call_records WHERE status = 'pending'"
                ).fetchall()
                active_pending = []
                for p_row in pending_rows:
                    # Smoke-test records (scripts/smoke.sh) must never be guessed into a real call.
                    if str(p_row["call_id"]).startswith(SMOKE_CALL_ID_PREFIX):
                        continue
                    ts_str = p_row["updated_at"] or p_row["created_at"] or ""
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        age_s = (now_utc - ts).total_seconds()
                        if 0 <= age_s <= active_window_seconds:
                            active_pending.append(p_row)
                    except Exception:
                        active_pending.append(p_row)

                if len(active_pending) == 1:
                    only_row = active_pending[0]
                    old_cid = only_row["call_id"]
                    logger.warning(
                        "Fallback single-active-call join fired: merging pending call_id=%s into webhook call_id=%s (provider_call_id=%s)",
                        old_cid,
                        call_id,
                        prov_id or "<none>",
                    )
                    _adopt_or_merge_pending_row(conn, call_id, old_cid)
                elif len(active_pending) > 1:
                    logger.warning(
                        "Fallback single-active-call join skipped for webhook call_id=%s: %d overlapping pending calls active (%s)",
                        call_id,
                        len(active_pending),
                        [r["call_id"] for r in active_pending],
                    )

            final_lookup = conn.execute(
                "SELECT * FROM call_records WHERE call_id = ?", (call_id,)
            ).fetchone()
            return _row_to_record(final_lookup) if final_lookup else None
        finally:
            conn.close()


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
            _sync_sqlite_row_to_pg(conn, call_id)
            return bundle
        finally:
            conn.close()


_MID_CALL_OPTIONAL_FIELDS = ("elicitation", "quote", "turn_index", "seconds_from_start")


def _mid_call_dedup_key(entry: Dict[str, Any]) -> tuple:
    kind = str(entry.get("kind") or entry.get("type") or "other").lower()
    if not entry.get("unparseable") and entry.get("normalized_value"):
        return (kind, str(entry["normalized_value"]).lower())
    # Unparseable captures dedupe on what was heard, whitespace/case-insensitively.
    return (kind, "raw:" + " ".join(str(entry.get("value_as_heard") or "").lower().split()))


def append_mid_call_intel(
    call_id: str,
    intel_type: str,
    value_as_heard: str,
    normalized_value: str,
    unparseable: bool,
    elicitation: Optional[str] = None,
    quote: Optional[str] = None,
    turn_index: Optional[int] = None,
    seconds_from_start: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Append a mid-call `log_intel` capture to the CallRecord for `call_id`.
    Creates a `pending` CallRecord if one does not exist yet.

    A call may log many distinct identifiers (mule rotation: a second UPI after "payment failed").
    Re-logging the same identifier (e.g. a repeat-back) does not add a new entry: it bumps
    `times_logged`, fills any context fields the first capture lacked, and records the new tactic
    in `elicitations`. Persona bait values are kept for audit with `is_bait=True` but never enter
    the identifier buckets.
    """
    from app.core.rules import APPROVED_BAIT_VALUES

    init_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    is_bait = bool(normalized_value) and normalized_value.lower().strip() in APPROVED_BAIT_VALUES
    log_entry: Dict[str, Any] = {
        "type": intel_type,
        "kind": intel_type,
        "value_as_heard": value_as_heard,
        "value_raw": value_as_heard,
        "normalized_value": normalized_value,
        "value_normalized": normalized_value,
        "unparseable": unparseable,
        "status": "suspected",
        "is_bait": is_bait,
        "elicitation": elicitation,
        "elicitations": [elicitation] if elicitation else [],
        "quote": quote,
        "turn_index": turn_index,
        "seconds_from_start": seconds_from_start,
        "times_logged": 1,
        "first_logged_at": now_iso,
        "last_logged_at": now_iso,
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

            key = _mid_call_dedup_key(log_entry)
            existing = next(
                (e for e in intel["mid_call_logs"] if isinstance(e, dict) and _mid_call_dedup_key(e) == key),
                None,
            )
            duplicate = existing is not None
            if existing is not None:
                existing["times_logged"] = int(existing.get("times_logged") or 1) + 1
                existing["last_logged_at"] = now_iso
                for f in _MID_CALL_OPTIONAL_FIELDS:
                    if existing.get(f) is None and log_entry[f] is not None:
                        existing[f] = log_entry[f]
                tactics = existing.setdefault(
                    "elicitations", [existing["elicitation"]] if existing.get("elicitation") else []
                )
                if elicitation and elicitation not in tactics:
                    tactics.append(elicitation)
                log_entry = existing
            else:
                intel["mid_call_logs"].append(log_entry)
            if not unparseable and normalized_value and not is_bait:
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
            _sync_sqlite_row_to_pg(conn, call_id)
            result = dict(log_entry)
            result["duplicate"] = duplicate
            result["identifiers_logged"] = len(
                {_mid_call_dedup_key(e) for e in intel["mid_call_logs"] if isinstance(e, dict) and not e.get("is_bait")}
            )
            return result
        finally:
            conn.close()


def finalize_call_record_from_webhook(
    payload: Dict[str, Any],
    extracted_intel: Dict[str, Any],
    verdict: str,
    confidence: float,
    summary: str,
    status_value: str = "finalized",
    stage2_ran: Optional[bool] = None,
    classifier_method: str = "",
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
            stage2_val = None if stage2_ran is None else int(bool(stage2_ran))

            from app.voice.evidence import compute_canonical_transcript_hash, compute_recording_bytes_hash
            t_sha256 = compute_canonical_transcript_hash(transcript)
            r_sha256, r_hash_err = compute_recording_bytes_hash(recording_url)
            hashed_at_val = now_iso
            money_lost_val = 1 if bool(payload.get("money_lost") or metadata.get("money_lost")) else 0

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
                        stage2_ran = ?,
                        classifier_method = ?,
                        transcript_sha256 = ?,
                        recording_sha256 = ?,
                        recording_hash_error = ?,
                        hashed_at = ?,
                        money_lost = ?,
                        evidence_status = COALESCE(evidence_status, 'draft'),
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
                        stage2_val,
                        classifier_method,
                        t_sha256,
                        r_sha256,
                        r_hash_err,
                        hashed_at_val,
                        money_lost_val,
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
                        stage2_ran, classifier_method,
                        transcript_sha256, recording_sha256, recording_hash_error,
                        hashed_at, money_lost, evidence_status,
                        finalized_fired, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
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
                        stage2_val,
                        classifier_method,
                        t_sha256,
                        r_sha256,
                        r_hash_err,
                        hashed_at_val,
                        money_lost_val,
                        "draft",
                        now_iso,
                        now_iso,
                    ),
                )
            conn.commit()
            _sync_sqlite_row_to_pg(conn, call_id)
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
            _sync_sqlite_row_to_pg(conn, call_id)
            updated = conn.execute(
                "SELECT * FROM call_records WHERE call_id = ?",
                (call_id,),
            ).fetchone()
            return _row_to_record(updated)
        finally:
            conn.close()


def confirm_call_evidence(call_id: str) -> Optional[Dict[str, Any]]:
    """
    Transition evidence_status to 'confirmed_by_family' and record confirmed_at (UTC).
    Does NOT auto-submit to any external portal.
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
            conn.execute(
                """
                UPDATE call_records
                SET evidence_status = 'confirmed_by_family',
                    confirmed_at = ?,
                    updated_at = ?
                WHERE call_id = ?
                """,
                (now_iso, now_iso, call_id),
            )
            conn.commit()
            _sync_sqlite_row_to_pg(conn, call_id)
            updated = conn.execute(
                "SELECT * FROM call_records WHERE call_id = ?",
                (call_id,),
            ).fetchone()
            return _row_to_record(updated)
        finally:
            conn.close()


def export_all_raw_rows() -> List[Dict[str, Any]]:
    """Export all raw SQLite rows from `call_records` for JSON snapshot backup."""
    init_db()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT * FROM call_records ORDER BY created_at ASC").fetchall()
            return [{k: r[k] for k in r.keys()} for r in rows]
        finally:
            conn.close()


def restore_raw_rows(rows: List[Dict[str, Any]]) -> int:
    """Restore raw SQLite rows from a JSON snapshot backup and return number of rows restored."""
    init_db()
    count = 0
    with _DB_LOCK:
        conn = _get_conn()
        try:
            for d in rows or []:
                if not isinstance(d, dict) or not d.get("call_id"):
                    continue
                cols = list(d.keys())
                placeholders = ", ".join(["?"] * len(cols))
                col_names = ", ".join(cols)
                conn.execute(
                    f"INSERT OR REPLACE INTO call_records ({col_names}) VALUES ({placeholders})",
                    [d[c] for c in cols],
                )
                _sync_sqlite_row_to_pg(conn, str(d["call_id"]))
                count += 1
            conn.commit()
            return count
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

