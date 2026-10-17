package ai.guardianline.screening

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test

class CallScreeningLogicTest {

    private val bolnaProxyNumber = "+919988776655"
    private lateinit var screeningLogic: CallScreeningLogic

    @BeforeEach
    fun setUp() {
        screeningLogic = CallScreeningLogic(bolnaProxyNumber)
    }

    @Test
    fun testSavedContactRings() {
        val contacts = setOf("+919876543210", "9123456789")
        val decision = screeningLogic.evaluateCall("+91 98765 43210", contacts)
        assertEquals(ScreeningAction.ALLOW, decision.action)
        assertEquals("SAVED_CONTACT", decision.reason)
    }

    @Test
    fun testBolnaNumberRingsToPreventTransferLoop() {
        val contacts = setOf("9876543210")
        val decision = screeningLogic.evaluateCall(bolnaProxyNumber, contacts)
        assertEquals(ScreeningAction.ALLOW, decision.action)
        assertEquals("BOLNA_AGENT_PROXY", decision.reason)
    }

    @Test
    fun testUnknownNumberIsRejectedForScreening() {
        val contacts = setOf("9876543210", "9811122233")
        val decision = screeningLogic.evaluateCall("+91 99999 88888", contacts)
        assertEquals(ScreeningAction.SCREEN, decision.action)
        assertEquals("UNKNOWN_CALLER_SCREEN", decision.reason)
    }

    @Test
    fun testPhoneNumberFormattingVariantsMatchContact() {
        // Saved as 10-digit
        val contacts = setOf("9876543210")

        // Incoming as leading zero with dashes
        val decisionZero = screeningLogic.evaluateCall("098765-43210", contacts)
        assertEquals(ScreeningAction.ALLOW, decisionZero.action)

        // Incoming with spaces and +91
        val decisionPlus = screeningLogic.evaluateCall("+91 98765 43210", contacts)
        assertEquals(ScreeningAction.ALLOW, decisionPlus.action)
    }

    @Test
    fun testWithheldNumberIsRejectedAndScreened() {
        val contacts = setOf("9876543210")

        val decisionNull = screeningLogic.evaluateCall(null, contacts)
        assertEquals(ScreeningAction.SCREEN, decisionNull.action)
        assertEquals("WITHHELD_NUMBER_SCREEN", decisionNull.reason)

        val decisionEmpty = screeningLogic.evaluateCall("", contacts)
        assertEquals(ScreeningAction.SCREEN, decisionEmpty.action)
        assertEquals("WITHHELD_NUMBER_SCREEN", decisionEmpty.reason)
    }

    @Test
    fun testEmergencyNumbersAlwaysRingEvenWithZeroContacts() {
        val contacts = emptySet<String>()
        val emergencyCodes = listOf("112", "100", "108", "1930")

        for (code in emergencyCodes) {
            val decision = screeningLogic.evaluateCall(code, contacts)
            assertEquals(ScreeningAction.ALLOW, decision.action)
            assertEquals("EMERGENCY_WHITELIST", decision.reason)
        }
    }

    @Test
    fun testEmptyContactListAllowsEmergencyAndBolnaAndScreensUnknowns() {
        val emptyContacts = emptySet<String>()

        val unknownDecision = screeningLogic.evaluateCall("9876543210", emptyContacts)
        assertEquals(ScreeningAction.SCREEN, unknownDecision.action)

        val emergencyDecision = screeningLogic.evaluateCall("112", emptyContacts)
        assertEquals(ScreeningAction.ALLOW, emergencyDecision.action)

        val bolnaDecision = screeningLogic.evaluateCall(bolnaProxyNumber, emptyContacts)
        assertEquals(ScreeningAction.ALLOW, bolnaDecision.action)
    }
}
