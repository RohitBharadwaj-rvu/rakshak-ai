"""
tests/unit/test_sprint4_suite.py - Mirror of T-HOST and Sprint 4 checks for `pytest tests/unit`.
"""

from tests.integration.test_host_smoke import (  # noqa: F401
    test_sprint4_extraction_miss_analyzer_and_online_db_backup,
    test_t_host_smoke_health_tools_schema_restart_and_call_id_logging,
)
