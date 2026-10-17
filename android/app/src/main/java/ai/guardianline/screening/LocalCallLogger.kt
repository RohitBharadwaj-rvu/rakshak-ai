package ai.guardianline.screening

import android.content.Context
import android.util.Log
import java.io.File
import java.io.FileWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object LocalCallLogger {

    private const val TAG = "GuardianScreeningLog"
    private const val LOG_FILENAME = "screening_soak_log.jsonl"

    /**
     * Masks telephone number for privacy in logs and logcat:
     * e.g. "+919876543210" -> "+91 98**** *210"
     */
    fun maskPhoneNumber(rawNumber: String?): String {
        if (rawNumber == null) return "WITHHELD"
        val trimmed = rawNumber.trim()
        if (trimmed.length <= 4) return "****"
        val prefix = trimmed.take(4)
        val suffix = trimmed.takeLast(3)
        return "$prefix****$suffix"
    }

    /**
     * Appends an entry to the local soak test log file.
     */
    fun logDecision(context: Context, rawNumber: String?, decision: ScreeningDecision) {
        val masked = maskPhoneNumber(rawNumber)
        val nowIso = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).format(Date())

        val logEntryJson = """{"timestamp":"$nowIso","masked_caller":"$masked","action":"${decision.action}","reason":"${decision.reason}"}"""

        // Log masked entry to Logcat
        Log.i(TAG, "Screened Call: $logEntryJson")

        try {
            val logFile = File(context.filesDir, LOG_FILENAME)
            FileWriter(logFile, true).use { writer ->
                writer.append(logEntryJson).append("\n")
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to write local soak test log", e)
        }
    }
}
