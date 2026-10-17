package ai.guardianline

import ai.guardianline.screening.GuardianCallScreeningService
import android.app.role.RoleManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    private lateinit var statusText: TextView
    private lateinit var btnEnableScreening: Button
    private lateinit var btnSetupForwarding: Button

    private val requestRoleLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        checkScreeningRoleStatus()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Simple programmatic UI for elderly accessibility and clean testing
        val layout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(48, 48, 48, 48)
        }

        val title = TextView(this).apply {
            text = "GuardianLine Call Shield"
            textSize = 24f
            setTypeface(null, android.graphics.Typeface.BOLD)
            setPadding(0, 0, 0, 32)
        }
        layout.addView(title)

        statusText = TextView(this).apply {
            textSize = 16f
            setPadding(0, 0, 0, 48)
        }
        layout.addView(statusText)

        btnEnableScreening = Button(this).apply {
            text = "1. Enable Screening Protection"
            textSize = 16f
            setOnClickListener { requestCallScreeningRole() }
        }
        layout.addView(btnEnableScreening)

        btnSetupForwarding = Button(this).apply {
            text = "2. Activate Carrier Forwarding (**67*)"
            textSize = 16f
            setOnClickListener { triggerCarrierForwardingDialer() }
        }
        layout.addView(btnSetupForwarding)

        setContentView(layout)
    }

    override fun onResume() {
        super.onResume()
        checkScreeningRoleStatus()
    }

    private fun checkScreeningRoleStatus() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val roleManager = getSystemService(Context.ROLE_SERVICE) as? RoleManager
            val isHeld = roleManager?.isRoleHeld(RoleManager.ROLE_CALL_SCREENING) == true
            if (isHeld) {
                statusText.text = "Status: ACTIVE & PROTECTED\nUnknown callers are screened automatically."
                statusText.setTextColor(android.graphics.Color.parseColor("#2E7D32")) // Green
            } else {
                statusText.text = "Status: NOT CONFIGURED\nTap below to enable call screening."
                statusText.setTextColor(android.graphics.Color.parseColor("#C62828")) // Red
            }
        } else {
            statusText.text = "Android 10+ required for app mode.\nPlease use Basic Mode carrier forwarding."
        }
    }

    private fun requestCallScreeningRole() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val roleManager = getSystemService(Context.ROLE_SERVICE) as? RoleManager
            if (roleManager != null && roleManager.isRoleAvailable(RoleManager.ROLE_CALL_SCREENING)) {
                val intent = roleManager.createRequestRoleIntent(RoleManager.ROLE_CALL_SCREENING)
                requestRoleLauncher.launch(intent)
            } else {
                Toast.makeText(this, "Call Screening Role unavailable on this device", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun triggerCarrierForwardingDialer() {
        val gatewayNumber = GuardianCallScreeningService.BOLNA_GATEWAY_NUMBER
        // USSD code **67*<number># requires URL-encoding for # (%23) in tel URI
        val ussdCode = "**67*${gatewayNumber}#"
        val encodedUssd = Uri.encode(ussdCode)
        val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:$encodedUssd"))
        startActivity(intent)
    }
}
