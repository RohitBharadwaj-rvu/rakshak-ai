"""Re-export T-HOOK integration suite under tests/unit so CI runs it automatically."""

from tests.integration.test_webhook import *  # noqa: F401,F403
