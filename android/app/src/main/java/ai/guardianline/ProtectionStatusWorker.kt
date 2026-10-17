package ai.guardianline

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.role.RoleManager
import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

/**
 * Checks every 15 minutes that GuardianLine still holds the call-screening role (T-AND step 8).
 * If the role was revoked (by the user, an OS update or a cleaner app), it posts a persistent
 * notification so the elder or family sees that protection is off without opening the app.
 */
class ProtectionStatusWorker(context: Context, params: WorkerParameters) : Worker(context, params) {

    override fun doWork(): Result {
        val ctx = applicationContext
        if (isScreeningRoleHeld(ctx)) {
            clearWarning(ctx)
        } else {
            postWarning(ctx)
        }
        return Result.success()
    }

    companion object {
        private const val TAG = "GuardianStatus"
        private const val WORK_NAME = "guardianline_protection_status"
        private const val CHANNEL_ID = "guardianline_protection_status"
        private const val NOTIFICATION_ID = 1001

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<ProtectionStatusWorker>(15, TimeUnit.MINUTES).build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork(WORK_NAME, ExistingPeriodicWorkPolicy.KEEP, request)
        }

        fun isScreeningRoleHeld(context: Context): Boolean {
            val roleManager = context.getSystemService(RoleManager::class.java) ?: return false
            return roleManager.isRoleHeld(RoleManager.ROLE_CALL_SCREENING)
        }

        fun clearWarning(context: Context) {
            NotificationManagerCompat.from(context).cancel(NOTIFICATION_ID)
        }

        fun postWarning(context: Context) {
            val manager = NotificationManagerCompat.from(context)
            if (!manager.areNotificationsEnabled()) {
                Log.w(TAG, "Protection is off but notifications are disabled")
                return
            }
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    context.getString(R.string.notification_channel_name),
                    NotificationManager.IMPORTANCE_HIGH
                )
            )
            val openApp = PendingIntent.getActivity(
                context,
                0,
                Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            val notification = NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.stat_sys_warning)
                .setContentTitle(context.getString(R.string.notification_protection_disabled))
                .setContentText(context.getString(R.string.status_warning_revoked))
                .setStyle(NotificationCompat.BigTextStyle().bigText(context.getString(R.string.status_warning_revoked)))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setOngoing(true)
                .setContentIntent(openApp)
                .build()
            try {
                manager.notify(NOTIFICATION_ID, notification)
            } catch (e: SecurityException) {
                Log.w(TAG, "POST_NOTIFICATIONS not granted; cannot show protection warning", e)
            }
        }
    }
}
