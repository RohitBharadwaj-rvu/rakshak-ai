"""
app/voice/syndicate.py - Scam Syndicate Clustering, Global Identifiers Table & Penny-Drop Pipeline (Rakshak v2).

Pipeline:
  log_intel -> global_scam_identifiers table -> syndicate clustering (by shared UPI/IFSC/phone/account)
  -> penny-drop API enrichment -> 1930 auto-report packet -> Community Bloom filter -> Android push payload.
"""

import hashlib
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.notify.bloom import get_community_bloom_filter
from app.voice.store import get_db_path

logger = logging.getLogger(__name__)

_SYNDICATE_LOCK = threading.RLock()

BANK_IFSC_DIRECTORY = {
    "SBIN": "State Bank of India",
    "PUNB": "Punjab National Bank",
    "CNRB": "Canara Bank",
    "BARB": "Bank of Baroda",
    "UBIN": "Union Bank of India",
    "IOBA": "Indian Overseas Bank",
    "BKID": "Bank of India",
    "CBIN": "Central Bank of India",
    "IDIB": "Indian Bank",
    "UCBA": "UCO Bank",
    "MAHB": "Bank of Maharashtra",
    "PSIB": "Punjab & Sind Bank",
    "HDFC": "HDFC Bank",
    "ICIC": "ICICI Bank",
    "UTIB": "Axis Bank",
    "KKBK": "Kotak Mahindra Bank",
    "INDB": "IndusInd Bank",
    "YESB": "Yes Bank",
    "FDRL": "Federal Bank",
    "IDFB": "IDFC FIRST Bank",
}


def _get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_syndicate_tables(db_path: Optional[str] = None) -> None:
    """Ensure `global_scam_identifiers` table exists in SQLite."""
    with _SYNDICATE_LOCK:
        conn = _get_conn(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS global_scam_identifiers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identifier_type TEXT NOT NULL,
                    normalized_value TEXT NOT NULL,
                    call_id TEXT NOT NULL,
                    cluster_id TEXT,
                    penny_drop_json TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    sightings INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(identifier_type, normalized_value, call_id)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def verify_penny_drop(
    identifier_type: str,
    normalized_value: str,
    ifsc_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Simulated penny-drop verification enrichment for UPI IDs, bank accounts, and IFSC codes.
    Deterministically derives a mule account holder status for offline/sandbox verification.
    """
    norm = (normalized_value or "").strip()
    digest = hashlib.sha256(f"{identifier_type}:{norm}".encode("utf-8")).digest()
    mule_names = [
        "Raju Traders Pvt Ltd",
        "Om Sai Enterprise",
        "Mahadev Digital Services",
        "Kiran Logistics Mule A/C",
        "Apex FastPay Solutions",
        "Balaji Telecom Center",
    ]
    beneficiary = mule_names[digest[0] % len(mule_names)]

    bank_name = "Unknown Bank"
    if identifier_type == "ifsc" and len(norm) >= 4:
        bank_name = BANK_IFSC_DIRECTORY.get(norm[:4].upper(), "Scheduled Commercial Bank")
    elif ifsc_code and len(ifsc_code) >= 4:
        bank_name = BANK_IFSC_DIRECTORY.get(ifsc_code[:4].upper(), "Scheduled Commercial Bank")
    elif identifier_type == "upi" and "@" in norm:
        handle = norm.split("@", 1)[1].lower()
        if "sbi" in handle:
            bank_name = "State Bank of India"
        elif "axis" in handle:
            bank_name = "Axis Bank"
        elif "icici" in handle:
            bank_name = "ICICI Bank"
        elif "hdfc" in handle:
            bank_name = "HDFC Bank"
        elif "pnb" in handle:
            bank_name = "Punjab National Bank"
        else:
            bank_name = f"NPCI PSP ({handle})"

    return {
        "verified": True,
        "identifier_type": identifier_type,
        "normalized_value": norm,
        "beneficiary_name": beneficiary,
        "bank_name": bank_name,
        "account_status": "ACTIVE_MULE_SUSPECT",
    }


def cluster_syndicates(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Cluster calls into scam syndicates whenever they share any normalized UPI, IFSC, phone, or account.
    Uses Union-Find over calls linked by shared identifiers in `global_scam_identifiers`.
    """
    init_syndicate_tables(db_path)
    with _SYNDICATE_LOCK:
        conn = _get_conn(db_path)
        try:
            rows = conn.execute(
                "SELECT identifier_type, normalized_value, call_id, penny_drop_json FROM global_scam_identifiers"
            ).fetchall()
        finally:
            conn.close()

    if not rows:
        return []

    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            if ra < rb:
                parent[rb] = ra
            else:
                parent[ra] = rb

    ident_to_calls: Dict[Tuple[str, str], List[str]] = {}
    call_to_idents: Dict[str, List[Dict[str, Any]]] = {}

    for row in rows:
        itype = row["identifier_type"]
        ival = row["normalized_value"]
        cid = row["call_id"]
        find(cid)
        ident_to_calls.setdefault((itype, ival), []).append(cid)
        call_to_idents.setdefault(cid, []).append(
            {
                "type": itype,
                "value": ival,
                "penny_drop": json.loads(row["penny_drop_json"]) if row["penny_drop_json"] else None,
            }
        )

    for (_itype, _ival), cids in ident_to_calls.items():
        first_cid = cids[0]
        for other_cid in cids[1:]:
            union(first_cid, other_cid)

    groups: Dict[str, Set[str]] = {}
    for cid in parent:
        root = find(cid)
        groups.setdefault(root, set()).add(cid)

    clusters: List[Dict[str, Any]] = []
    for root, call_ids in sorted(groups.items()):
        sorted_calls = sorted(call_ids)
        cluster_seed = ",".join(sorted_calls)
        cluster_id = "SYN-" + hashlib.sha256(cluster_seed.encode("utf-8")).hexdigest()[:10].upper()

        shared_upis: Set[str] = set()
        shared_ifscs: Set[str] = set()
        shared_phones: Set[str] = set()
        shared_accounts: Set[str] = set()
        penny_drops: List[Dict[str, Any]] = []
        seen_pd: Set[Tuple[str, str]] = set()

        for cid in sorted_calls:
            for item in call_to_idents.get(cid, []):
                t, v = item["type"], item["value"]
                if t == "upi":
                    shared_upis.add(v)
                elif t == "ifsc":
                    shared_ifscs.add(v)
                elif t == "phone":
                    shared_phones.add(v)
                elif t == "account":
                    shared_accounts.add(v)
                if item.get("penny_drop") and (t, v) not in seen_pd:
                    seen_pd.add((t, v))
                    penny_drops.append(item["penny_drop"])

        clusters.append(
            {
                "cluster_id": cluster_id,
                "call_ids": sorted_calls,
                "call_count": len(sorted_calls),
                "upi_ids": sorted(shared_upis),
                "ifsc_codes": sorted(shared_ifscs),
                "phone_numbers": sorted(shared_phones),
                "bank_accounts": sorted(shared_accounts),
                "penny_drop_verifications": penny_drops,
                "auto_1930_ready": len(sorted_calls) >= 1 and bool(
                    shared_upis or shared_accounts or shared_phones
                ),
            }
        )

    # Persist cluster_id back to global_scam_identifiers
    with _SYNDICATE_LOCK:
        conn = _get_conn(db_path)
        try:
            for cl in clusters:
                for cid in cl["call_ids"]:
                    conn.execute(
                        "UPDATE global_scam_identifiers SET cluster_id = ? WHERE call_id = ?",
                        (cl["cluster_id"], cid),
                    )
            conn.commit()
        finally:
            conn.close()

    return clusters


def ingest_scam_identifier(
    call_id: str,
    identifier_type: str,
    normalized_value: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Record a normalized scammer identifier into `global_scam_identifiers`, run penny-drop
    enrichment, re-cluster syndicates, add to the Community Bloom filter, and build an
    Android push + 1930 auto-report summary.
    """
    init_syndicate_tables(db_path)
    itype = (identifier_type or "other").strip().lower()
    norm = (normalized_value or "").strip()
    now_iso = datetime.now(timezone.utc).isoformat()

    penny_drop = verify_penny_drop(itype, norm) if itype in ("upi", "account", "ifsc") else None
    pd_json = json.dumps(penny_drop, ensure_ascii=False) if penny_drop else None

    with _SYNDICATE_LOCK:
        conn = _get_conn(db_path)
        try:
            existing = conn.execute(
                """
                SELECT id, sightings FROM global_scam_identifiers
                WHERE identifier_type = ? AND normalized_value = ? AND call_id = ?
                """,
                (itype, norm, call_id),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE global_scam_identifiers
                    SET last_seen_at = ?, sightings = sightings + 1, penny_drop_json = COALESCE(?, penny_drop_json)
                    WHERE id = ?
                    """,
                    (now_iso, pd_json, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO global_scam_identifiers
                    (identifier_type, normalized_value, call_id, penny_drop_json, first_seen_at, last_seen_at, sightings)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    """,
                    (itype, norm, call_id, pd_json, now_iso, now_iso),
                )
            conn.commit()
        finally:
            conn.close()

    # Update Community Blocklist Bloom Filter
    bloom = get_community_bloom_filter()
    bloom.add(norm, kind=itype)

    # Recompute syndicate clusters
    clusters = cluster_syndicates(db_path)
    matched_cluster = next((c for c in clusters if call_id in c["call_ids"]), None)
    cluster_id = matched_cluster["cluster_id"] if matched_cluster else None

    return {
        "call_id": call_id,
        "identifier_type": itype,
        "normalized_value": norm,
        "cluster_id": cluster_id,
        "cluster": matched_cluster,
        "penny_drop": penny_drop,
        "bloom_push_payload": bloom.export_android_push_payload(cluster_id=cluster_id),
    }
