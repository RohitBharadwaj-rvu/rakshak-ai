package ai.guardianline.screening

import ai.guardianline.BuildConfig
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

    @Test
    fun testBuildConfigGatewayNumberIsConfiguredAndScreeningContractHolds() {
        assertTrue(BuildConfig.BOLNA_GATEWAY_NUMBER.isNotBlank(), "BuildConfig.BOLNA_GATEWAY_NUMBER must not be blank")
        val serviceLogic = CallScreeningLogic(BuildConfig.BOLNA_GATEWAY_NUMBER)
        val contacts = setOf("+919876543210")

        // 1. Saved contacts ring
        val contactDecision = serviceLogic.evaluateCall("+91 98765 43210", contacts)
        assertEquals(ScreeningAction.ALLOW, contactDecision.action)
        assertEquals("SAVED_CONTACT", contactDecision.reason)

        // 2. Unknown numbers are rejected / screened
        val unknownDecision = serviceLogic.evaluateCall("+91 91111 22222", contacts)
        assertEquals(ScreeningAction.SCREEN, unknownDecision.action)
        assertEquals("UNKNOWN_CALLER_SCREEN", unknownDecision.reason)

        // 3. 112 and 1930 ring
        val decision112 = serviceLogic.evaluateCall("112", contacts)
        assertEquals(ScreeningAction.ALLOW, decision112.action)
        assertEquals("EMERGENCY_WHITELIST", decision112.reason)

        val decision1930 = serviceLogic.evaluateCall("1930", contacts)
        assertEquals(ScreeningAction.ALLOW, decision1930.action)
        assertEquals("EMERGENCY_WHITELIST", decision1930.reason)

        // 4. Configured BuildConfig.BOLNA_GATEWAY_NUMBER rings
        val gatewayDecision = serviceLogic.evaluateCall(BuildConfig.BOLNA_GATEWAY_NUMBER, contacts)
        assertEquals(ScreeningAction.ALLOW, gatewayDecision.action)
        assertEquals("BOLNA_AGENT_PROXY", gatewayDecision.reason)
    }
}

