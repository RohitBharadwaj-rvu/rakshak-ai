package ai.guardianline.screening

object PhoneNumberNormalizer {

    val EMERGENCY_NUMBERS = setOf("112", "100", "108", "1930", "1091")

    /**
     * Normalizes phone numbers to standard E.164 (+91XXXXXXXXXX) format
     * or raw emergency short codes (112, 100, 108, 1930).
     * Returns null if number is blank or invalid.
     */
    fun normalize(rawNumber: String?): String? {
        if (rawNumber.isNullOrBlank()) return null

        val trimmed = rawNumber.trim()
        val digitsOnly = trimmed.replace(Regex("[^0-9+]"), "")

        // Emergency short codes check
        if (EMERGENCY_NUMBERS.contains(digitsOnly) || EMERGENCY_NUMBERS.contains(trimmed)) {
            return digitsOnly.replace("+", "")
        }

        val pureDigits = trimmed.replace(Regex("[^0-9]"), "")
        if (pureDigits.isBlank()) return null

        if (EMERGENCY_NUMBERS.contains(pureDigits)) {
            return pureDigits
        }

        // Standard 12-digit format with 91 prefix
        if (pureDigits.length == 12 && pureDigits.startsWith("91")) {
            return "+91" + pureDigits.substring(2)
        }

        // 11-digit with leading zero (e.g., 09876543210)
        if (pureDigits.length == 11 && pureDigits.startsWith("0")) {
            return "+91" + pureDigits.substring(1)
        }

        // Standard 10-digit Indian mobile number
        if (pureDigits.length == 10) {
            return "+91$pureDigits"
        }

        // International format if preceded by +
        if (digitsOnly.startsWith("+")) {
            return "+$pureDigits"
        }

        return if (pureDigits.length >= 10) "+91$pureDigits" else pureDigits
    }
}
