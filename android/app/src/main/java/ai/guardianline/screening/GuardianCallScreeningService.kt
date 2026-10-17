package ai.guardianline.screening

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
        // In production, loaded from SharedPreferences / BuildConfig
        const val BOLNA_GATEWAY_NUMBER = "+919988776655"
    }

    private val screeningLogic = CallScreeningLogic(BOLNA_GATEWAY_NUMBER)

    override fun onScreenCall(callDetails: Call.Details) {
        val handle: Uri? = callDetails.handle
        val rawNumber = handle?.schemeSpecificPart

        Log.i(TAG, "Inbound call detected: $rawNumber")

        val contacts = fetchContacts()
        val decision = screeningLogic.evaluateCall(rawNumber, contacts)

        Log.i(TAG, "Screening Decision: ${decision.action} (${decision.reason})")

        val responseBuilder = CallResponse.Builder()

        when (decision.action) {
            ScreeningAction.ALLOW -> {
                // Allow call to ring device normally
                responseBuilder.setDisallowCall(false)
                    .setRejectCall(false)
                    .setSilenceCall(false)
                    .setSkipCallLog(false)
                    .setSkipNotification(false)
            }
            ScreeningAction.SCREEN -> {
                // Disallow & Reject call immediately so carrier triggers **67* busy forward to Bolna
                responseBuilder.setDisallowCall(true)
                    .setRejectCall(true)
                    .setSilenceCall(true)
                    .setSkipNotification(true)
                    .setSkipCallLog(false) // Keep in call history for elder transparency
            }
        }

        respondToCall(callDetails, responseBuilder.build())
    }

    private fun fetchContacts(): Set<String> {
        val contactsSet = mutableSetOf<String>()
        try {
            val cursor = contentResolver.query(
                ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                arrayOf(ContactsContract.CommonDataKinds.Phone.NUMBER),
                null,
                null,
                null
            )
            cursor?.use {
                val numberIndex = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.NUMBER)
                while (it.moveToNext()) {
                    val number = it.getString(numberIndex)
                    if (!number.isNullOrBlank()) {
                        contactsSet.add(number)
                    }
                }
            }
        } catch (e: SecurityException) {
            Log.e(TAG, "Contacts permission not granted, failing open for safety", e)
        }
        return contactsSet
    }
}
