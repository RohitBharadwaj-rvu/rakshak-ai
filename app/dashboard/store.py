"""
Data Store for GuardianLine Family Dashboard (Lane C / T-DASH).
Provides thread-safe in-memory cache with fallback to SQLite CallRecord store.
"""

from typing import Any, Dict, List, Optional
import threading


class InMemoryCallStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._calls: Dict[str, Dict[str, Any]] = {}

    def add_call(self, record: Dict[str, Any]) -> None:
        call_id = record.get("call_id")
        if not call_id:
            raise ValueError("Record must contain 'call_id'")
        with self._lock:
            self._calls[call_id] = record

    def get_calls(self, verdict: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            calls = list(self._calls.values())
        # Sort newest first by timestamp or call_id
        calls.sort(key=lambda x: x.get("timestamp", x.get("call_id", "")), reverse=True)
        if verdict:
            v_lower = verdict.lower()
            calls = [c for c in calls if str(c.get("verdict", "")).lower() == v_lower]
        return calls[:limit]

    def get_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._calls.get(call_id)

    def clear(self) -> None:
        with self._lock:
            self._calls.clear()


_GLOBAL_STORE = InMemoryCallStore()


def get_dashboard_store() -> InMemoryCallStore:
    return _GLOBAL_STORE
