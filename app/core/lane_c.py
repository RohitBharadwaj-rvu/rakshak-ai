"""
Lane C wiring into the GuardianLine backend.
File: app/core/lane_c.py

Lane B owns `app/main.py`, the CallRecord store (`app.voice.store`) and the 1930 report
(`app.voice.report`). Lane C plugs into them instead of keeping copies:

    from app.core.lane_c import install
    install(app)

install() mounts the family dashboard and the event route, subscribes family alerts to
B's in-process `call.finalized` bus, points the dashboard at B's SQLite store, and renders
reports with B's generator. When B's modules are not importable (lane C on its own),
the dashboard keeps its in-memory store and alerts can still be driven over HTTP.
"""

import logging
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI

from app.core import gui
from app.notify import listener

logger = logging.getLogger("guardianline.lane_c")


class LaneBCallStore(gui.BaseCallStore):
    """Read-only dashboard adapter over Lane B's CallRecord store."""

    def __init__(self, store_module: Any):
        self._store = store_module

    def add_call(self, record: Dict[str, Any]) -> None:
        raise NotImplementedError("CallRecords are written by Lane B's webhook, not the dashboard")

    def _count(
        self,
        verdict: Optional[str],
        dependent_id: Optional[str] = None,
        dependent_ids: Optional[List[str]] = None,
    ) -> int:
        self._store.init_db()
        conn = sqlite3.connect(self._store.get_db_path())
        try:
            clauses: List[str] = []
            params: List[Any] = []
            if verdict:
                clauses.append("verdict = ?")
                params.append(verdict)
            if dependent_id:
                clauses.append("dependent_id = ?")
                params.append(dependent_id)
            elif dependent_ids is not None:
                if not dependent_ids:
                    return 0
                placeholders = ", ".join(["?"] * len(dependent_ids))
                clauses.append(f"dependent_id IN ({placeholders})")
                params.extend(dependent_ids)
            where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            row = conn.execute(f"SELECT COUNT(*) FROM call_records{where_sql}", params).fetchone()
            return int(row[0])
        finally:
            conn.close()

    def get_calls(
        self,
        verdict: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
        dependent_id: Optional[str] = None,
        dependent_ids: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        offset = max(0, (page - 1) * limit)
        calls = self._store.list_call_records(
            limit=limit,
            verdict=verdict,
            offset=offset,
            dependent_id=dependent_id,
            dependent_ids=dependent_ids,
        )
        return calls, self._count(verdict, dependent_id=dependent_id, dependent_ids=dependent_ids)

    def get_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get_call_record(call_id)

    def confirm_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        if hasattr(self._store, "confirm_call_evidence"):
            return self._store.confirm_call_evidence(call_id)
        return super().confirm_call(call_id)

    def clear(self) -> None:
        raise NotImplementedError("CallRecords are owned by Lane B")



def install(app: FastAPI) -> bool:
    """Mount Lane C routes and connect them to Lane B. Returns True if Lane B was found."""
    if not getattr(app.state, "_lane_c_installed", False):
        app.include_router(gui.router)
        app.include_router(listener.router)
        app.state._lane_c_installed = True



    try:
        from app.voice import store as lane_b_store
        from app.voice.report import generate_1930_report
    except ImportError:
        logger.warning("Lane B backend not found; dashboard uses in-memory store, alerts via /events only")
        return False

    gui.set_dashboard_store(LaneBCallStore(lane_b_store))
    gui.set_report_renderer(generate_1930_report)
    listener.set_record_loader(lane_b_store.get_call_record)
    lane_b_store.register_call_finalized_listener(listener.on_call_finalized)
    logger.info("Lane C connected to Lane B store, report generator and call.finalized bus")
    return True


def create_app() -> FastAPI:
    """Standalone app for running Lane C on its own (demo, tests). Production uses Lane B's app/main.py."""
    app = FastAPI(title="GuardianLine family dashboard and alerts")
    try:
        from app.api.classifier_router import router as classifier_router
        app.include_router(classifier_router)
    except ImportError:
        pass
    install(app)

    @app.get("/healthz")
    def health_check():
        return {"status": "healthy", "service": "guardianline"}

    return app
