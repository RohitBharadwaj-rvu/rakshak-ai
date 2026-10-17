import pytest
from app.screening.screener import (
    CallScreeningEngine,
    ScreeningAction,
    ScreeningDecision,
    normalize_phone_number,
    DEFAULT_EMERGENCY_NUMBERS,
)

BOLNA_NUMBER = "+919988776655"


@pytest.fixture
def screener():
    return CallScreeningEngine(bolna_proxy_number=BOLNA_NUMBER)


class TestPhoneNumberNormalization:
    def test_normalizes_standard_10_digit(self):
        assert normalize_phone_number("9876543210") == "+919876543210"

    def test_normalizes_plus_91_with_spaces_and_dashes(self):
        assert normalize_phone_number("+91 98765-43210") == "+919876543210"

    def test_normalizes_leading_zero(self):
        assert normalize_phone_number("098765 43210") == "+919876543210"

    def test_normalizes_emergency_short_codes(self):
        assert normalize_phone_number("112") == "112"
        assert normalize_phone_number("100") == "100"
        assert normalize_phone_number("1930") == "1930"
        assert normalize_phone_number("108") == "108"

    def test_withheld_or_empty_number(self):
        assert normalize_phone_number(None) is None
        assert normalize_phone_number("") is None
        assert normalize_phone_number("   ") is None


class TestCallScreeningDecisions:
    def test_saved_contact_rings(self, screener):
        contacts = ["+919876543210", "9123456789"]
        decision = screener.evaluate_call("+91 98765 43210", contacts)
        assert decision.action == ScreeningAction.ALLOW
        assert decision.reason == "SAVED_CONTACT"

    def test_contact_in_different_formats_matches(self, screener):
        # Contact saved as 10-digit
        contacts = ["9876543210"]
        # Inbound arrives with leading 0 and dashes
        decision = screener.evaluate_call("098765-43210", contacts)
        assert decision.action == ScreeningAction.ALLOW
        assert decision.reason == "SAVED_CONTACT"

        # Inbound arrives as +91
        decision2 = screener.evaluate_call("+919876543210", contacts)
        assert decision2.action == ScreeningAction.ALLOW

    def test_bolna_number_always_rings_to_prevent_call_loop(self, screener):
        # Bolna proxy agent calling elder (e.g. transfer mode)
        contacts = ["9876543210"]
        decision = screener.evaluate_call(BOLNA_NUMBER, contacts)
        assert decision.action == ScreeningAction.ALLOW
        assert decision.reason == "BOLNA_AGENT_PROXY"

    def test_unknown_number_is_rejected_for_screening(self, screener):
        contacts = ["9876543210", "9811122233"]
        decision = screener.evaluate_call("+91 99999 88888", contacts)
        assert decision.action == ScreeningAction.SCREEN
        assert decision.reason == "UNKNOWN_CALLER_SCREEN"

    def test_withheld_number_is_screened(self, screener):
        contacts = ["9876543210"]
        decision = screener.evaluate_call(None, contacts)
        assert decision.action == ScreeningAction.SCREEN
        assert decision.reason == "WITHHELD_NUMBER_SCREEN"

        decision_empty = screener.evaluate_call("", contacts)
        assert decision_empty.action == ScreeningAction.SCREEN
        assert decision_empty.reason == "WITHHELD_NUMBER_SCREEN"

    def test_emergency_numbers_always_ring(self, screener):
        contacts = []  # Even with zero contacts
        for num in DEFAULT_EMERGENCY_NUMBERS:
            decision = screener.evaluate_call(num, contacts)
            assert decision.action == ScreeningAction.ALLOW
            assert decision.reason == "EMERGENCY_WHITELIST"

    def test_empty_contacts_list_screens_unknowns_allows_whitelist(self, screener):
        contacts = []
        # Unknown gets screened
        decision = screener.evaluate_call("9876543210", contacts)
        assert decision.action == ScreeningAction.SCREEN

        # Emergency still rings
        decision_em = screener.evaluate_call("112", contacts)
        assert decision_em.action == ScreeningAction.ALLOW

        # Bolna proxy still rings
        decision_bolna = screener.evaluate_call(BOLNA_NUMBER, contacts)
        assert decision_bolna.action == ScreeningAction.ALLOW
