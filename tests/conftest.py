"""
tests/conftest.py - Pytest configuration and shared test fixtures.
"""

import os
import pytest

TEST_API_TOKEN = "test_api_token_not_secret"


@pytest.fixture(autouse=True)
def clean_test_env(monkeypatch):
    """
    Ensure ambient .env variables (such as live LLM keys and webhook secrets) do not
    cause unit and integration tests to make nondeterministic live API calls or fail
    unauthenticated requests with 401.
    """
    monkeypatch.setenv("BOLNA_WEBHOOK_SECRET", "")
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED_WEBHOOK", "true")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GUARDIANLINE_API_TOKEN", TEST_API_TOKEN)
    monkeypatch.setenv("FAMILY_DB_PATH", ":memory:")
    from app.core.family import set_family_registry
    set_family_registry(None)
