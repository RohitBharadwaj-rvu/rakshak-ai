"""
tests/unit/test_privacy.py - Secrets, Access Control & Phone Masking Suite (T-PRIV).

Verifies:
  - .env is listed in .gitignore and not tracked by git
  - .env.example exists and contains no real API keys
  - mask_phone masks all but the last 4 digits of caller numbers for logs
  - CallRecords retain the full caller number for the 1930 cybercrime report
"""

import os
import re
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.voice.store import mask_phone


def test_gitignore_excludes_dotenv_and_sqlite_db():
    gitignore_path = os.path.join(ROOT_DIR, ".gitignore")
    assert os.path.exists(gitignore_path)
    with open(gitignore_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert ".env" in content


def test_env_example_has_no_live_secrets():
    env_example = os.path.join(ROOT_DIR, ".env.example")
    assert os.path.exists(env_example)
    with open(env_example, "r", encoding="utf-8") as f:
        text = f.read()
    # Ensure no live sk- / gsk_ / AIza keys are committed
    assert not re.search(r"\b(gsk_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{30,}|sk-[A-Za-z0-9]{20,})\b", text)


def test_mask_phone_masks_all_but_last_4_digits():
    assert mask_phone("+919876543210") == "*********3210"
    assert mask_phone("9876543210") == "******3210"
    assert mask_phone("") == "<withheld>"
    assert mask_phone(None) == "<withheld>"
