"""
Multi-Caretaker / Multi-Dependent Family Registry (Seam 1).
File: app/core/family.py

Models a many-to-many household graph where multiple Caretakers (e.g. both Mother and Father)
monitor multiple Dependents (e.g. Grandparents and Kids).
"""

import hashlib
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class DependentRole(str, Enum):
    GRANDPARENT = "grandparent"
    PARENT = "parent"
    CHILD = "child"
    OTHER = "other"


class CaretakerRole(str, Enum):
    PARENT = "parent"
    CARETAKER = "caretaker"
    OTHER = "other"


def normalize_family_phone(raw_phone: Optional[str]) -> str:
    """
    Normalizes telephone numbers into canonical E.164 format matching Android's PhoneNumberNormalizer:
      - 10-digit Indian mobile -> +91XXXXXXXXXX
      - 11-digit with leading 0 -> +91XXXXXXXXXX
      - 12-digit starting with 91 -> +91XXXXXXXXXX
      - International with + or 00 -> +<digits>
    """
    if not raw_phone:
        return ""
    trimmed = str(raw_phone).strip()
    if not trimmed:
        return ""

    digits_and_plus = re.sub(r"[^0-9+]", "", trimmed)
    if digits_and_plus.startswith("00"):
        digits_and_plus = "+" + digits_and_plus[2:]

    if digits_and_plus.startswith("+"):
        pure = re.sub(r"[^0-9]", "", digits_and_plus[1:])
        return f"+{pure}" if pure else ""

    pure = re.sub(r"[^0-9]", "", digits_and_plus)
    if not pure:
        return ""
    if len(pure) == 12 and pure.startswith("91"):
        return f"+{pure}"
    if len(pure) == 11 and pure.startswith("0"):
        return f"+91{pure[1:]}"
    if len(pure) == 10 and not pure.startswith("0"):
        return f"+91{pure}"
    return f"+{pure}" if len(pure) > 10 else pure


def _stable_id(prefix: str, phone: str, name: str) -> str:
    seed = f"{phone}:{name.strip().lower()}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()[:10]
    return f"{prefix}_{digest}"


class FamilyRegistry:
    """
    SQLite-backed registry managing Dependents, Caretakers, and their many-to-many monitoring links.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("FAMILY_DB_PATH", ":memory:")
        self._lock = threading.RLock()
        self._is_mem = self.db_path == ":memory:"
        self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False) if self._is_mem else None
        if self._mem_conn:
            self._mem_conn.row_factory = sqlite3.Row
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _close_if_file(self, conn: sqlite3.Connection) -> None:
        if not self._is_mem:
            conn.close()

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS family_dependents (
                        dependent_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        phone_number TEXT NOT NULL UNIQUE,
                        role TEXT NOT NULL DEFAULT 'grandparent',
                        device_status TEXT NOT NULL DEFAULT 'active',
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS family_caretakers (
                        caretaker_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        phone_number TEXT NOT NULL UNIQUE,
                        role TEXT NOT NULL DEFAULT 'parent',
                        channel TEXT NOT NULL DEFAULT 'whatsapp',
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS family_links (
                        caretaker_id TEXT NOT NULL,
                        dependent_id TEXT NOT NULL,
                        relationship_label TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (caretaker_id, dependent_id)
                    )
                    """
                )
                conn.commit()
            finally:
                self._close_if_file(conn)

    def register_dependent(
        self,
        name: str,
        phone_number: str,
        role: str = DependentRole.GRANDPARENT.value,
        dependent_id: Optional[str] = None,
        device_status: str = "active",
    ) -> Dict[str, Any]:
        norm_phone = normalize_family_phone(phone_number)
        if not norm_phone:
            raise ValueError("Dependent phone_number must not be blank")
        clean_name = name.strip() or "Dependent"
        role_val = role.value if isinstance(role, Enum) else str(role or "grandparent").lower()
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            conn = self._get_conn()
            try:
                existing = conn.execute(
                    "SELECT * FROM family_dependents WHERE phone_number = ? OR dependent_id = ?",
                    (norm_phone, dependent_id or ""),
                ).fetchone()
                dep_id = (
                    existing["dependent_id"]
                    if existing
                    else (dependent_id or _stable_id("dep", norm_phone, clean_name))
                )
                conn.execute(
                    """
                    INSERT INTO family_dependents (dependent_id, name, phone_number, role, device_status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(dependent_id) DO UPDATE SET
                        name = excluded.name,
                        phone_number = excluded.phone_number,
                        role = excluded.role,
                        device_status = excluded.device_status
                    """,
                    (dep_id, clean_name, norm_phone, role_val, device_status, now_iso),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM family_dependents WHERE dependent_id = ?", (dep_id,)
                ).fetchone()
                return dict(row)
            finally:
                self._close_if_file(conn)

    def register_caretaker(
        self,
        name: str,
        phone_number: str,
        role: str = CaretakerRole.PARENT.value,
        channel: str = "whatsapp",
        caretaker_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        norm_phone = normalize_family_phone(phone_number)
        if not norm_phone:
            raise ValueError("Caretaker phone_number must not be blank")
        clean_name = name.strip() or "Caretaker"
        role_val = role.value if isinstance(role, Enum) else str(role or "parent").lower()
        chan_val = str(channel or "whatsapp").lower()
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            conn = self._get_conn()
            try:
                existing = conn.execute(
                    "SELECT * FROM family_caretakers WHERE phone_number = ? OR caretaker_id = ?",
                    (norm_phone, caretaker_id or ""),
                ).fetchone()
                ct_id = (
                    existing["caretaker_id"]
                    if existing
                    else (caretaker_id or _stable_id("ct", norm_phone, clean_name))
                )
                conn.execute(
                    """
                    INSERT INTO family_caretakers (caretaker_id, name, phone_number, role, channel, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(caretaker_id) DO UPDATE SET
                        name = excluded.name,
                        phone_number = excluded.phone_number,
                        role = excluded.role,
                        channel = excluded.channel
                    """,
                    (ct_id, clean_name, norm_phone, role_val, chan_val, now_iso),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM family_caretakers WHERE caretaker_id = ?", (ct_id,)
                ).fetchone()
                return dict(row)
            finally:
                self._close_if_file(conn)

    def link_caretaker_to_dependent(
        self,
        caretaker_id: str,
        dependent_id: str,
        relationship_label: str = "",
    ) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._get_conn()
            try:
                ct = self._find_caretaker_row(conn, caretaker_id)
                dep = self._find_dependent_row(conn, dependent_id)
                if not ct:
                    raise ValueError(f"Caretaker '{caretaker_id}' not found")
                if not dep:
                    raise ValueError(f"Dependent '{dependent_id}' not found")

                ct_id = ct["caretaker_id"]
                dep_id = dep["dependent_id"]
                conn.execute(
                    """
                    INSERT INTO family_links (caretaker_id, dependent_id, relationship_label, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(caretaker_id, dependent_id) DO UPDATE SET
                        relationship_label = excluded.relationship_label
                    """,
                    (ct_id, dep_id, relationship_label.strip(), now_iso),
                )
                conn.commit()
                return {
                    "caretaker_id": ct_id,
                    "dependent_id": dep_id,
                    "relationship_label": relationship_label.strip(),
                    "created_at": now_iso,
                }
            finally:
                self._close_if_file(conn)

    def unlink_caretaker_from_dependent(self, caretaker_id: str, dependent_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                ct = self._find_caretaker_row(conn, caretaker_id)
                dep = self._find_dependent_row(conn, dependent_id)
                ct_id = ct["caretaker_id"] if ct else caretaker_id
                dep_id = dep["dependent_id"] if dep else dependent_id
                cur = conn.execute(
                    "DELETE FROM family_links WHERE caretaker_id = ? AND dependent_id = ?",
                    (ct_id, dep_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                self._close_if_file(conn)

    def _find_caretaker_row(self, conn: sqlite3.Connection, id_or_phone: str) -> Optional[sqlite3.Row]:
        if not id_or_phone:
            return None
        row = conn.execute(
            "SELECT * FROM family_caretakers WHERE caretaker_id = ?", (id_or_phone,)
        ).fetchone()
        if row:
            return row
        norm = normalize_family_phone(id_or_phone)
        if norm:
            return conn.execute(
                "SELECT * FROM family_caretakers WHERE phone_number = ?", (norm,)
            ).fetchone()
        return None

    def _find_dependent_row(self, conn: sqlite3.Connection, id_or_phone: str) -> Optional[sqlite3.Row]:
        if not id_or_phone:
            return None
        row = conn.execute(
            "SELECT * FROM family_dependents WHERE dependent_id = ?", (id_or_phone,)
        ).fetchone()
        if row:
            return row
        norm = normalize_family_phone(id_or_phone)
        if norm:
            return conn.execute(
                "SELECT * FROM family_dependents WHERE phone_number = ?", (norm,)
            ).fetchone()
        return None

    def get_dependent(self, dependent_id_or_phone: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = self._find_dependent_row(conn, dependent_id_or_phone)
                return dict(row) if row else None
            finally:
                self._close_if_file(conn)

    def get_caretaker(self, caretaker_id_or_phone: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = self._find_caretaker_row(conn, caretaker_id_or_phone)
                return dict(row) if row else None
            finally:
                self._close_if_file(conn)

    def get_dependents_for_caretaker(self, caretaker_id_or_phone: str) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                ct = self._find_caretaker_row(conn, caretaker_id_or_phone)
                if not ct:
                    return []
                rows = conn.execute(
                    """
                    SELECT d.*, l.relationship_label
                    FROM family_dependents d
                    JOIN family_links l ON d.dependent_id = l.dependent_id
                    WHERE l.caretaker_id = ?
                    ORDER BY d.created_at ASC, d.dependent_id ASC
                    """,
                    (ct["caretaker_id"],),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                self._close_if_file(conn)

    def get_caretakers_for_dependent(self, dependent_id_or_phone: str) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                dep = self._find_dependent_row(conn, dependent_id_or_phone)
                if not dep:
                    return []
                rows = conn.execute(
                    """
                    SELECT c.*, l.relationship_label
                    FROM family_caretakers c
                    JOIN family_links l ON c.caretaker_id = l.caretaker_id
                    WHERE l.dependent_id = ?
                    ORDER BY c.created_at ASC, c.caretaker_id ASC
                    """,
                    (dep["dependent_id"],),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                self._close_if_file(conn)

    def list_dependents(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM family_dependents ORDER BY created_at ASC, dependent_id ASC"
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                self._close_if_file(conn)

    def list_caretakers(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM family_caretakers ORDER BY created_at ASC, caretaker_id ASC"
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                self._close_if_file(conn)

    def list_links(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM family_links ORDER BY created_at ASC"
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                self._close_if_file(conn)

    def resolve_dependent_for_call(self, call_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Matches a call_record to a registered dependent via `dependent_id`, `dependent_phone`,
        `protected_phone`, or `forwarded_from`.
        """
        for key in ("dependent_id", "dependent_phone", "protected_phone", "forwarded_from"):
            val = call_record.get(key)
            if val:
                dep = self.get_dependent(str(val))
                if dep:
                    return dep
        return None

    def resolve_alert_recipients_for_call(
        self,
        call_record: Dict[str, Any],
        fallback_recipients: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Returns deduplicated E.164 caretaker phone numbers for the dependent targeted by `call_record`.
        If the call matches a registered dependent with linked caretakers, returns those caretakers
        (plus any explicit `fallback_recipients`).
        """
        recipients: List[str] = []
        dep = self.resolve_dependent_for_call(call_record)
        if dep:
            caretakers = self.get_caretakers_for_dependent(dep["dependent_id"])
            for c in caretakers:
                ph = c.get("phone_number")
                if ph and ph not in recipients:
                    recipients.append(ph)

        if fallback_recipients:
            for fb in fallback_recipients:
                norm_fb = normalize_family_phone(fb)
                if norm_fb and norm_fb not in recipients:
                    recipients.append(norm_fb)

        return recipients

    def get_family_topology(self, caretaker_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns the enriched family graph with each dependent's caretakers and each caretaker's dependents.
        """
        dependents = (
            self.get_dependents_for_caretaker(caretaker_id)
            if caretaker_id
            else self.list_dependents()
        )
        caretakers = self.list_caretakers()
        links = self.list_links()

        enriched_deps = []
        for d in dependents:
            d_copy = dict(d)
            d_copy["caretakers"] = self.get_caretakers_for_dependent(d["dependent_id"])
            enriched_deps.append(d_copy)

        enriched_cts = []
        for c in caretakers:
            c_copy = dict(c)
            c_copy["dependents"] = self.get_dependents_for_caretaker(c["caretaker_id"])
            enriched_cts.append(c_copy)

        return {
            "dependents": enriched_deps,
            "caretakers": enriched_cts,
            "links": links,
        }

    def clear(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM family_links")
                conn.execute("DELETE FROM family_dependents")
                conn.execute("DELETE FROM family_caretakers")
                conn.commit()
            finally:
                self._close_if_file(conn)


_GLOBAL_FAMILY_REGISTRY: Optional[FamilyRegistry] = None


def get_family_registry() -> FamilyRegistry:
    global _GLOBAL_FAMILY_REGISTRY
    if _GLOBAL_FAMILY_REGISTRY is None:
        _GLOBAL_FAMILY_REGISTRY = FamilyRegistry()
    return _GLOBAL_FAMILY_REGISTRY


def set_family_registry(registry: Optional[FamilyRegistry]) -> None:
    global _GLOBAL_FAMILY_REGISTRY
    _GLOBAL_FAMILY_REGISTRY = registry
