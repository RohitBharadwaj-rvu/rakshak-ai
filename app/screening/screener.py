"""
Call Screening Decision Engine for GuardianLine (Lane C / T-AND).

Evaluates inbound telephone calls to determine whether to ALLOW the call
(ring on elder's handset) or SCREEN the call (disallow / reject so carrier
conditional forwarding redirects to the Bolna voice honeypot agent).
"""

import re
from enum import Enum
from typing import Iterable, Optional, Set
from pydantic import BaseModel, Field

DEFAULT_EMERGENCY_NUMBERS: Set[str] = {
    "112",   # Unified National Emergency
    "100",   # Police Helpline
    "108",   # Ambulance & Disaster Management
    "1930",  # National Cybercrime Reporting Helpline
    "1091",  # Women Helpline
}


class ScreeningAction(str, Enum):
    ALLOW = "allow"
    SCREEN = "screen"


class ScreeningDecision(BaseModel):
    action: ScreeningAction
    reason: str
    normalized_number: Optional[str] = None
    original_number: Optional[str] = None


def normalize_phone_number(raw_number: Optional[str]) -> Optional[str]:
    """
    Normalizes telephone number into E.164-style standard for Indian telecom.
    Handles +91, leading 0, spaces, dashes, parentheses, and emergency short codes.
    Returns None if number is empty, None, or withheld.
    """
    if raw_number is None:
        return None

    cleaned = str(raw_number).strip()
    if not cleaned:
        return None

    # Handle emergency short codes directly
    digits_only = re.sub(r"[^\d+]", "", cleaned)
    if digits_only in DEFAULT_EMERGENCY_NUMBERS:
        return digits_only

    # Remove non-digits
    pure_digits = re.sub(r"\D", "", cleaned)
    if not pure_digits:
        return None

    # If it's a short code (3-4 digits), keep as is
    if len(pure_digits) in (3, 4) and pure_digits in DEFAULT_EMERGENCY_NUMBERS:
        return pure_digits

    # Strip country code 91 if present as prefix of 12 digits
    if len(pure_digits) == 12 and pure_digits.startswith("91"):
        national_10 = pure_digits[2:]
        return f"+91{national_10}"

    # Strip leading zero if 11 digits (e.g. 09876543210)
    if len(pure_digits) == 11 and pure_digits.startswith("0"):
        national_10 = pure_digits[1:]
        return f"+91{national_10}"

    # Standard 10 digit Indian number
    if len(pure_digits) == 10:
        return f"+91{pure_digits}"

    # Fallback to standard + prefix if international
    if digits_only.startswith("+"):
        return f"+{pure_digits}"
    return f"+91{pure_digits}" if len(pure_digits) >= 10 else pure_digits


class CallScreeningEngine:
    """
    In-memory screening engine matching Android CallScreeningService rules.
    """

    def __init__(
        self,
        bolna_proxy_number: str,
        emergency_numbers: Optional[Set[str]] = None,
    ):
        self.bolna_proxy_number = normalize_phone_number(bolna_proxy_number)
        self.emergency_numbers = (
            set(emergency_numbers) if emergency_numbers is not None else DEFAULT_EMERGENCY_NUMBERS
        )

    def evaluate_call(
        self,
        caller_number: Optional[str],
        contacts: Iterable[str],
    ) -> ScreeningDecision:
        """
        Evaluates incoming call against emergency whitelist, Bolna proxy,
        and saved contact list.
        """
        normalized_caller = normalize_phone_number(caller_number)

        # 1. Withheld or Private number: SCREEN immediately
        if not normalized_caller:
            return ScreeningDecision(
                action=ScreeningAction.SCREEN,
                reason="WITHHELD_NUMBER_SCREEN",
                original_number=caller_number,
                normalized_number=None,
            )

        # 2. Emergency and helpline short codes: ALWAYS ALLOW
        if normalized_caller in self.emergency_numbers:
            return ScreeningDecision(
                action=ScreeningAction.ALLOW,
                reason="EMERGENCY_WHITELIST",
                original_number=caller_number,
                normalized_number=normalized_caller,
            )

        # 3. Bolna proxy number: ALWAYS ALLOW (prevents transfer loops)
        if self.bolna_proxy_number and normalized_caller == self.bolna_proxy_number:
            return ScreeningDecision(
                action=ScreeningAction.ALLOW,
                reason="BOLNA_AGENT_PROXY",
                original_number=caller_number,
                normalized_number=normalized_caller,
            )

        # 4. Normalized contact check
        normalized_contacts = {
            normalize_phone_number(c) for c in contacts if normalize_phone_number(c) is not None
        }

        if normalized_caller in normalized_contacts:
            return ScreeningDecision(
                action=ScreeningAction.ALLOW,
                reason="SAVED_CONTACT",
                original_number=caller_number,
                normalized_number=normalized_caller,
            )

        # 5. Unknown caller: SCREEN to Bolna agent
        return ScreeningDecision(
            action=ScreeningAction.SCREEN,
            reason="UNKNOWN_CALLER_SCREEN",
            original_number=caller_number,
            normalized_number=normalized_caller,
        )
