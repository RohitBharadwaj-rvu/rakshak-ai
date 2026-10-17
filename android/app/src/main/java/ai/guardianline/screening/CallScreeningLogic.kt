package ai.guardianline.screening

enum class ScreeningAction {
    ALLOW,
    SCREEN
}

data class ScreeningDecision(
    val action: ScreeningAction,
    val reason: String,
    val normalizedNumber: String? = null
)

/**
 * Core decision logic for call screening.
 *
 * TRANSFER LOOP MITIGATION:
 * Whitelisting the Bolna gateway number ensures that when Bolna initiates an outbound transfer
 * of a genuine caller to the elder, the device allows it to ring instead of rejecting.
 * OPEN INTERFACE ITEM FOR LANE A (T-XFER):
 * If the elder declines the call or is busy, the carrier's **67* rule forwards the call back
 * to Bolna. Before T-XFER testing, Lane A and Lane C must agree on:
 * 1) What caller ID Bolna's transfer leg presents to the elder's handset.
 * 2) Agent behaviour when an inbound call originates from its own gateway or forwarded number.
 */
class CallScreeningLogic(
    bolnaProxyNumber: String?,
    private val emergencyNumbers: Set<String> = PhoneNumberNormalizer.EMERGENCY_NUMBERS
) {
    val normalizedBolnaNumber: String? = PhoneNumberNormalizer.normalize(bolnaProxyNumber)

    /**
     * Evaluates incoming caller against emergency whitelist, Bolna proxy, and contacts.
     */
    fun evaluateCall(
        rawCallerNumber: String?,
        isSavedContact: (String) -> Boolean
    ): ScreeningDecision {
        val normalizedCaller = PhoneNumberNormalizer.normalize(rawCallerNumber)

        // 1. Withheld or Private numbers -> SCREEN to voice agent
        if (normalizedCaller == null) {
            return ScreeningDecision(
                action = ScreeningAction.SCREEN,
                reason = "WITHHELD_NUMBER_SCREEN",
                normalizedNumber = null
            )
        }

        // 2. Emergency helpline numbers (112, 100, 108, 1930) -> ALWAYS ALLOW
        if (emergencyNumbers.contains(normalizedCaller)) {
            return ScreeningDecision(
                action = ScreeningAction.ALLOW,
                reason = "EMERGENCY_WHITELIST",
                normalizedNumber = normalizedCaller
            )
        }

        // 3. Bolna proxy number -> ALWAYS ALLOW (prevents device rejection on genuine caller transfer)
        if (normalizedBolnaNumber != null && normalizedCaller == normalizedBolnaNumber) {
            return ScreeningDecision(
                action = ScreeningAction.ALLOW,
                reason = "BOLNA_AGENT_PROXY",
                normalizedNumber = normalizedCaller
            )
        }

        // 4. Saved Contacts check via single lookup
        if (isSavedContact(normalizedCaller)) {
            return ScreeningDecision(
                action = ScreeningAction.ALLOW,
                reason = "SAVED_CONTACT",
                normalizedNumber = normalizedCaller
            )
        }

        // 5. Unknown caller -> SCREEN to Bolna Honeypot
        return ScreeningDecision(
            action = ScreeningAction.SCREEN,
            reason = "UNKNOWN_CALLER_SCREEN",
            normalizedNumber = normalizedCaller
        )
    }

    /**
     * Overload for Set<String> contacts in unit tests.
     */
    fun evaluateCall(
        rawCallerNumber: String?,
        contacts: Set<String>
    ): ScreeningDecision {
        val normalizedContacts = contacts.mapNotNull { PhoneNumberNormalizer.normalize(it) }.toSet()
        return evaluateCall(rawCallerNumber) { normalizedContacts.contains(it) }
    }
}
