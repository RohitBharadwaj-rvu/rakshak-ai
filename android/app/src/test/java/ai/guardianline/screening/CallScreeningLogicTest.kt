package ai.guardianline.screening

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.params.ParameterizedTest
import org.junit.jupiter.params.provider.MethodSource
import java.util.stream.Stream

data class ScreeningTestCase(
    val description: String,
    val caller_number: String?,
    val contacts: List<String>,
    val bolna_number: String,
    val expected_action: String,
    val expected_reason: String
)

class CallScreeningLogicTest {

    private val bolnaProxyNumber = "+919988776655"
    private lateinit var screeningLogic: CallScreeningLogic

    companion object {
        @JvmStatic
        fun provideSharedScreeningCases(): Stream<ScreeningTestCase> {
            // tests/data is a test resource dir (see app/build.gradle.kts)
            val stream = requireNotNull(CallScreeningLogicTest::class.java.getResourceAsStream("/screening_cases.json")) {
                "screening_cases.json not on the test classpath"
            }
            val jsonText = stream.bufferedReader().use { it.readText() }
            val listType = object : TypeToken<List<ScreeningTestCase>>() {}.type
            val cases: List<ScreeningTestCase> = Gson().fromJson(jsonText, listType)
            return cases.stream()
        }
    }

    @BeforeEach
    fun setUp() {
        screeningLogic = CallScreeningLogic(bolnaProxyNumber)
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("provideSharedScreeningCases")
    fun testSharedScreeningCasesFromCanonicalJson(testCase: ScreeningTestCase) {
        val logic = CallScreeningLogic(testCase.bolna_number)
        val decision = logic.evaluateCall(testCase.caller_number, testCase.contacts.toSet())
        val expectedAction = ScreeningAction.valueOf(testCase.expected_action)
        assertEquals(expectedAction, decision.action, "Action mismatch for case: ${testCase.description}")
        assertEquals(testCase.expected_reason, decision.reason, "Reason mismatch for case: ${testCase.description}")
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
        val contacts = setOf("9876543210")

        val decisionZero = screeningLogic.evaluateCall("098765-43210", contacts)
        assertEquals(ScreeningAction.ALLOW, decisionZero.action)

        val decisionPlus = screeningLogic.evaluateCall("+91 98765 43210", contacts)
        assertEquals(ScreeningAction.ALLOW, decisionPlus.action)
    }

    @Test
    fun testInternationalExitCodeDoubleZeroMatchesContact() {
        // Saved as E.164 USA number
        val contacts = setOf("+14155552671")

        // Inbound or dialed with 00 exit code
        val decision = screeningLogic.evaluateCall("0014155552671", contacts)
        assertEquals(ScreeningAction.ALLOW, decision.action)
        assertEquals("SAVED_CONTACT", decision.reason)
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
