package ai.guardianline.screening

import ai.guardianline.BuildConfig
import android.content.ContentResolver
import android.net.Uri
import android.os.Build
import android.provider.ContactsContract
import android.telecom.Call
import android.telecom.CallScreeningService
import android.util.Log
import androidx.annotation.RequiresApi

@RequiresApi(Build.VERSION_CODES.Q)
class GuardianCallScreeningService : CallScreeningService() {

    companion object {
        private const val TAG = "GuardianScreening"
    }

    private val screeningLogic = CallScreeningLogic(BuildConfig.BOLNA_GATEWAY_NUMBER)

    override fun onScreenCall(callDetails: Call.Details) {
        try {
            // Only screen incoming calls (API 30+ has DIRECTION_INCOMING)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                if (callDetails.callDirection != Call.Details.DIRECTION_INCOMING) {
                    Log.d(TAG, "Ignoring non-incoming call direction: ${callDetails.callDirection}")
                    respondAllow(callDetails)
                    return
                }
            }

            val handle: Uri? = callDetails.handle
            val rawNumber = handle?.schemeSpecificPart

            Log.i(TAG, "Inbound call screening evaluation started")

            // Evaluate with single-number contact lookup
            val decision = screeningLogic.evaluateCall(rawNumber) { numberToCheck ->
                isNumberInContacts(contentResolver, numberToCheck)
            }

            // Log decision to private soak log file and masked Logcat
            LocalCallLogger.logDecision(applicationContext, rawNumber, decision)

            val responseBuilder = CallResponse.Builder()
            when (decision.action) {
                ScreeningAction.ALLOW -> {
                    responseBuilder.setDisallowCall(false)
                        .setRejectCall(false)
                        .setSilenceCall(false)
                        .setSkipCallLog(false)
                        .setSkipNotification(false)
                }
                ScreeningAction.SCREEN -> {
                    // Reject call immediately so carrier triggers **67* busy forward to Bolna
                    responseBuilder.setDisallowCall(true)
                        .setRejectCall(true)
                        .setSilenceCall(true)
                        .setSkipNotification(true)
                        .setSkipCallLog(false) // Retain in device call history for transparency
                }
            }
            respondToCall(callDetails, responseBuilder.build())

        } catch (t: Throwable) {
            // FAIL-OPEN MANDATE: Any unexpected exception must NEVER block genuine calls.
            Log.e(TAG, "Exception during call screening, failing open to ring handset", t)
            respondAllow(callDetails)
        }
    }

    private fun respondAllow(callDetails: Call.Details) {
        val allowResponse = CallResponse.Builder()
            .setDisallowCall(false)
            .setRejectCall(false)
            .setSilenceCall(false)
            .setSkipCallLog(false)
            .setSkipNotification(false)
            .build()
        respondToCall(callDetails, allowResponse)
    }

    /**
     * Efficient single-number lookup via PhoneLookup URI.
     * Does not load the entire contact database into memory.
     */
    private fun isNumberInContacts(contentResolver: ContentResolver, normalizedNumber: String): Boolean {
        return try {
            val uri = Uri.withAppendedPath(
                ContactsContract.PhoneLookup.CONTENT_FILTER_URI,
                Uri.encode(normalizedNumber)
            )
            val projection = arrayOf(ContactsContract.PhoneLookup._ID)
            contentResolver.query(uri, projection, null, null, null)?.use { cursor ->
                cursor.moveToFirst()
            } ?: false
        } catch (e: SecurityException) {
            Log.w(TAG, "READ_CONTACTS permission not held; assuming non-contact", e)
            false
        } catch (e: Exception) {
            Log.w(TAG, "Error querying phone lookup URI", e)
            false
        }
    }
}
