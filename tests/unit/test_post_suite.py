"""
tests/unit/test_post_suite.py - Mirror of T-POST so `pytest tests/unit` runs T-POST checks.
"""

from tests.integration.test_post import (  # noqa: F401
    client,
    test_reflection_and_enrichment_run_on_all_6_fixtures_within_60s,
    test_reflection_or_enrichment_failure_is_logged_and_leaves_call_record_intact,
    test_tasks_start_after_record_saved_and_after_family_alert,
    test_webhook_retry_heals_cleanup_pending_and_csv_export_works,
)
