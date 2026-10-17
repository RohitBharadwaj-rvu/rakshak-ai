"""Re-export T-API suite under tests/unit so CI runs it automatically."""

from tests.integration.test_api import *  # noqa: F401,F403
