package ai.guardianline.screening

object PhoneNumberNormalizer {

    val EMERGENCY_NUMBERS = setOf("112", "100", "108", "1930", "1091")

    /**
     * Normalizes telephone numbers into consistent formats for lookup:
     * - Emergency short codes: raw digits ("112", "100", "108", "1930")
     * - Indian mobile/landline numbers: "+91" followed by 10 national digits
     * - International numbers with "+" or "00" prefix: "+<country_code><national_number>"
     * Returns null if raw number is null, blank, or has no digits.
     */
    fun normalize(rawNumber: String?): String? {
        if (rawNumber.isNullOrBlank()) return null

        val trimmed = rawNumber.trim()
        val digitsOnly = trimmed.replace(Regex("[^0-9+]"), "")

        // Emergency short codes check
        if (EMERGENCY_NUMBERS.contains(digitsOnly) || EMERGENCY_NUMBERS.contains(trimmed)) {
            return digitsOnly.replace("+", "")
        }

        // Handle ITU-T international exit code prefix "00" (e.g. 001415... -> +1415...)
        var working = digitsOnly
        if (working.startsWith("00")) {
            working = "+" + working.substring(2)
        }

        if (working.startsWith("+")) {
            val pureDigits = working.substring(1).replace(Regex("[^0-9]"), "")
            if (pureDigits.length == 12 && pureDigits.startsWith("91")) {
                return "+$pureDigits"
            }
            // Retain full international format without forced +91 substitution
            return "+$pureDigits"
        }

        val pureDigits = working.replace(Regex("[^0-9]"), "")
        if (pureDigits.isBlank()) return null

        if (EMERGENCY_NUMBERS.contains(pureDigits)) {
            return pureDigits
        }

        // Standard Indian 12-digit format with 91 prefix
        if (pureDigits.length == 12 && pureDigits.startsWith("91")) {
            return "+91" + pureDigits.substring(2)
        }

        // Standard Indian 11-digit format with leading trunk zero (e.g., 09876543210)
        if (pureDigits.length == 11 && pureDigits.startsWith("0")) {
            return "+91" + pureDigits.substring(1)
        }

        // Standard 10-digit Indian mobile number
        if (pureDigits.length == 10 && !pureDigits.startsWith("0")) {
            return "+91$pureDigits"
        }

        // Do not blindly append +91 to arbitrary non-Indian numbers; return pure digits
        return pureDigits
    }
}
