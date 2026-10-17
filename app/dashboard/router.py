"""
Backward-compatible wrapper for Family Dashboard router.
Points to app.core.gui as defined in the Lane C sprint plan.
"""

from app.core.gui import (
    router,
    verify_dashboard_auth,
    get_dashboard_store,
    InMemoryCallStore,
)

__all__ = [
    "router",
    "verify_dashboard_auth",
    "get_dashboard_store",
    "InMemoryCallStore",
]
