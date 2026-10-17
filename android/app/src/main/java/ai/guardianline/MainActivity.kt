package ai.guardianline

import ai.guardianline.BuildConfig
import android.Manifest
import android.app.role.RoleManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {

    private lateinit var statusText: TextView
    private lateinit var permText: TextView
    private lateinit var btnEnableScreening: Button
    private lateinit var btnSetupForwarding: Button

    private val requestRoleLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { _ ->
        checkScreeningRoleStatus()
    }

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { _ ->
        checkPermissionsStatus()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val layout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(48, 48, 48, 48)
        }

        val title = TextView(this).apply {
            text = getString(R.string.title_shield)
            textSize = 28f
            setTypeface(null, android.graphics.Typeface.BOLD)
            setPadding(0, 0, 0, 16)
        }
        layout.addView(title)

        val subtitle = TextView(this).apply {
            text = getString(R.string.subtitle_shield)
            textSize = 18f
            setTextColor(android.graphics.Color.DKGRAY)
            setPadding(0, 0, 0, 32)
        }
        layout.addView(subtitle)

        statusText = TextView(this).apply {
            textSize = 22f
            setTypeface(null, android.graphics.Typeface.BOLD)
            setPadding(0, 0, 0, 24)
        }
        layout.addView(statusText)

        permText = TextView(this).apply {
            textSize = 18f
            setPadding(0, 0, 0, 36)
        }
        layout.addView(permText)

        btnEnableScreening = Button(this).apply {
            text = getString(R.string.btn_enable_screening)
            textSize = 20f
            setTypeface(null, android.graphics.Typeface.BOLD)
            setPadding(32, 32, 32, 32)
            setOnClickListener { requestCallScreeningRole() }
        }
        layout.addView(btnEnableScreening)

        btnSetupForwarding = Button(this).apply {
            text = getString(R.string.btn_setup_forwarding)
            textSize = 20f
            setTypeface(null, android.graphics.Typeface.BOLD)
            setPadding(32, 32, 32, 32)
            setOnClickListener { triggerCarrierForwardingDialer() }
        }
        layout.addView(btnSetupForwarding)

        setContentView(layout)
    }

    override fun onResume() {
        super.onResume()
        checkScreeningRoleStatus()
        checkPermissionsStatus()
    }

    private fun checkScreeningRoleStatus() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val roleManager = getSystemService(Context.ROLE_SERVICE) as? RoleManager
            val isHeld = roleManager?.isRoleHeld(RoleManager.ROLE_CALL_SCREENING) == true
            if (isHeld) {
                statusText.text = getString(R.string.status_active)
                statusText.setTextColor(android.graphics.Color.parseColor("#2E7D32")) // Green
            } else {
                statusText.text = getString(R.string.status_warning_revoked)
                statusText.setTextColor(android.graphics.Color.parseColor("#C62828")) // Red
            }
        } else {
            statusText.text = getString(R.string.status_unsupported)
            statusText.setTextColor(android.graphics.Color.parseColor("#E65100"))
        }
    }

    private fun checkPermissionsStatus() {
        val hasContacts = ContextCompat.checkSelfPermission(
            this, Manifest.permission.READ_CONTACTS
        ) == PackageManager.PERMISSION_GRANTED

        if (hasContacts) {
            permText.text = getString(R.string.perm_contacts_granted)
            permText.setTextColor(android.graphics.Color.parseColor("#2E7D32"))
        } else {
            permText.text = getString(R.string.perm_contacts_missing)
            permText.setTextColor(android.graphics.Color.parseColor("#C62828"))
            permText.setOnClickListener {
                requestPermissionLauncher.launch(Manifest.permission.READ_CONTACTS)
            }
        }
    }

    private fun requestCallScreeningRole() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val roleManager = getSystemService(Context.ROLE_SERVICE) as? RoleManager
            if (roleManager != null && roleManager.isRoleAvailable(RoleManager.ROLE_CALL_SCREENING)) {
                val intent = roleManager.createRequestRoleIntent(RoleManager.ROLE_CALL_SCREENING)
                requestRoleLauncher.launch(intent)
            } else {
                Toast.makeText(this, getString(R.string.toast_role_unavailable), Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun triggerCarrierForwardingDialer() {
        val gatewayNumber = BuildConfig.BOLNA_GATEWAY_NUMBER.trim()
        if (gatewayNumber.isBlank()) {
            Toast.makeText(this, getString(R.string.gateway_not_configured), Toast.LENGTH_LONG).show()
            return
        }
        val ussdCode = "**67*${gatewayNumber}#"
        val encodedUssd = Uri.encode(ussdCode)
        val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:$encodedUssd"))
        startActivity(intent)
    }
}
