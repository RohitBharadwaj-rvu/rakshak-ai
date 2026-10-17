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
    private const val MAX_LOG_SIZE_BYTES = 500_000L // 500 KB limit for soak test logs

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

    fun getLogFile(context: Context): File {
        return File(context.filesDir, LOG_FILENAME)
    }

    fun readLogContent(context: Context): String {
        val file = getLogFile(context)
        return if (file.exists()) file.readText() else ""
    }

    fun clearLog(context: Context) {
        val file = getLogFile(context)
        if (file.exists()) file.delete()
    }

    /**
     * Appends an entry to the local soak test log file with verified UTC timestamp.
     * Enforces maximum file size cap to prevent runaway disk usage.
     */
    fun logDecision(context: Context, rawNumber: String?, decision: ScreeningDecision) {
        val masked = maskPhoneNumber(rawNumber)
        val nowIso = java.time.Instant.now().toString()

        val logEntryJson = """{"timestamp":"$nowIso","masked_caller":"$masked","action":"${decision.action}","reason":"${decision.reason}"}"""

        // Log masked entry to Logcat
        Log.i(TAG, "Screened Call: $logEntryJson")

        try {
            val logFile = getLogFile(context)
            if (logFile.exists() && logFile.length() > MAX_LOG_SIZE_BYTES) {
                // Keep the most recent 1000 lines
                val lines = logFile.readLines()
                val keepLines = lines.takeLast(1000)
                logFile.writeText(keepLines.joinToString("\n") + "\n")
            }
            FileWriter(logFile, true).use { writer ->
                writer.append(logEntryJson).append("\n")
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to write local soak test log", e)
        }
    }
}
