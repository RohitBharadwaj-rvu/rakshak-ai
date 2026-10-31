package ai.guardianline

import ai.guardianline.caretaker.CaretakerProfile
import ai.guardianline.caretaker.CaretakerRole
import ai.guardianline.caretaker.DependentProfile
import ai.guardianline.caretaker.DependentRole
import ai.guardianline.caretaker.ExtractedIntel
import ai.guardianline.caretaker.FamilyCircleManager
import ai.guardianline.caretaker.ScreenedCallDossier
import ai.guardianline.caretaker.TranscriptTurn
import ai.guardianline.screening.LocalCallLogger
import android.Manifest
import android.app.AlertDialog
import android.app.role.RoleManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {

    private lateinit var statusText: TextView
    private lateinit var permText: TextView
    private lateinit var btnEnableScreening: Button
    private lateinit var btnSetupForwarding: Button
    private lateinit var btnShareLog: Button
    private lateinit var dependentEnrollmentSummary: TextView

    private lateinit var tabShieldBtn: Button
    private lateinit var tabCaretakerBtn: Button
    private lateinit var shieldContainer: LinearLayout
    private lateinit var caretakerContainer: LinearLayout

    // Caretaker dashboard state
    private val familyManager = FamilyCircleManager()
    private var activeCaretakerId: String? = null
    private var selectedDependentId: String? = null
    private var selectedRoleFilter: DependentRole? = null

    private lateinit var caretakerSelectRow: LinearLayout
    private lateinit var dependentFilterRow: LinearLayout
    private lateinit var scamIntelContainer: LinearLayout
    private lateinit var callsListContainer: LinearLayout

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

    private val requestNotificationLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { _ -> }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        familyManager.seedDefaultMultiGenerationHousehold()
        activeCaretakerId = familyManager.listCaretakers().firstOrNull()?.caretakerId

        val rootScroll = ScrollView(this).apply {
            setBackgroundColor(Color.parseColor("#0F172A"))
            isFillViewport = true
        }

        val rootLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 36, 36, 48)
        }
        rootScroll.addView(rootLayout)

        // Top Mode Switcher: Dependent Shield vs Caretaker Dashboard
        val modeBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(8, 8, 8, 8)
            background = roundedBg("#1E293B", 24f)
        }

        tabShieldBtn = Button(this).apply {
            text = getString(R.string.tab_dependent_shield)
            textSize = 13f
            isAllCaps = false
            setTypeface(null, Typeface.BOLD)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                marginEnd = 6
            }
            setOnClickListener { switchMode(isCaretakerMode = false) }
        }
        tabCaretakerBtn = Button(this).apply {
            text = getString(R.string.tab_caretaker_dashboard)
            textSize = 13f
            isAllCaps = false
            setTypeface(null, Typeface.BOLD)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                marginStart = 6
            }
            setOnClickListener { switchMode(isCaretakerMode = true) }
        }
        modeBar.addView(tabShieldBtn)
        modeBar.addView(tabCaretakerBtn)
        rootLayout.addView(modeBar, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 28 })

        // Container 1: Dependent Shield (Protect This Phone)
        shieldContainer = buildDependentShieldView()
        rootLayout.addView(shieldContainer)

        // Container 2: Caretaker Dashboard (Monitor Multiple Dependents)
        caretakerContainer = buildCaretakerDashboardView()
        rootLayout.addView(caretakerContainer)

        setContentView(rootScroll)

        switchMode(isCaretakerMode = false)
        refreshCaretakerDashboard()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestNotificationLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        ProtectionStatusWorker.schedule(this)
    }

    private fun switchMode(isCaretakerMode: Boolean) {
        if (isCaretakerMode) {
            shieldContainer.visibility = View.GONE
            caretakerContainer.visibility = View.VISIBLE
            tabCaretakerBtn.background = roundedBg("#2563EB", 18f)
            tabCaretakerBtn.setTextColor(Color.WHITE)
            tabShieldBtn.background = roundedBg("#1E293B", 18f)
            tabShieldBtn.setTextColor(Color.parseColor("#94A3B8"))
            refreshCaretakerDashboard()
        } else {
            shieldContainer.visibility = View.VISIBLE
            caretakerContainer.visibility = View.GONE
            tabShieldBtn.background = roundedBg("#2563EB", 18f)
            tabShieldBtn.setTextColor(Color.WHITE)
            tabCaretakerBtn.background = roundedBg("#1E293B", 18f)
            tabCaretakerBtn.setTextColor(Color.parseColor("#94A3B8"))
            updateDependentEnrollmentSummary()
        }
    }

    private fun buildDependentShieldView(): LinearLayout {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        val title = TextView(this).apply {
            text = getString(R.string.title_shield)
            textSize = 24f
            setTextColor(Color.parseColor("#38BDF8"))
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, 8)
        }
        layout.addView(title)

        val subtitle = TextView(this).apply {
            text = getString(R.string.subtitle_shield)
            textSize = 15f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, 0, 0, 24)
        }
        layout.addView(subtitle)

        // Family Enrollment Card for this Dependent Handset
        val enrollmentCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = roundedBg("#1E293B", 24f, strokeColor = "#334155")
            setPadding(32, 28, 32, 28)
        }
        val enrollTitle = TextView(this).apply {
            text = "👨‍👩‍👧‍👦 Protected Family Handset Profile"
            textSize = 16f
            setTextColor(Color.WHITE)
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, 10)
        }
        enrollmentCard.addView(enrollTitle)

        dependentEnrollmentSummary = TextView(this).apply {
            textSize = 14f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, 0, 0, 16)
        }
        enrollmentCard.addView(dependentEnrollmentSummary)

        val btnConfigureDeviceOwner = Button(this).apply {
            text = "Enroll / Assign Caretakers for This Handset"
            textSize = 14f
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = roundedBg("#334155", 16f)
            setOnClickListener { showManageFamilyDialog() }
        }
        enrollmentCard.addView(btnConfigureDeviceOwner)
        layout.addView(enrollmentCard, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 24 })

        val statusCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = roundedBg("#1E293B", 24f)
            setPadding(32, 28, 32, 28)
        }

        statusText = TextView(this).apply {
            textSize = 18f
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, 16)
        }
        statusCard.addView(statusText)

        permText = TextView(this).apply {
            textSize = 15f
            setPadding(0, 0, 0, 8)
        }
        statusCard.addView(permText)

        layout.addView(statusCard, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 24 })

        btnEnableScreening = Button(this).apply {
            text = getString(R.string.btn_enable_screening)
            textSize = 17f
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = roundedBg("#2563EB", 20f)
            setTypeface(null, Typeface.BOLD)
            setPadding(32, 28, 32, 28)
            setOnClickListener { requestCallScreeningRole() }
        }
        layout.addView(btnEnableScreening, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 16 })

        btnSetupForwarding = Button(this).apply {
            text = getString(R.string.btn_setup_forwarding)
            textSize = 17f
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = roundedBg("#059669", 20f)
            setTypeface(null, Typeface.BOLD)
            setPadding(32, 28, 32, 28)
            setOnClickListener { triggerCarrierForwardingDialer() }
        }
        layout.addView(btnSetupForwarding, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 16 })

        btnShareLog = Button(this).apply {
            text = getString(R.string.btn_share_log)
            textSize = 15f
            isAllCaps = false
            setTextColor(Color.parseColor("#E2E8F0"))
            background = roundedBg("#334155", 20f)
            setPadding(24, 24, 24, 24)
            setOnClickListener { shareSoakLog() }
        }
        layout.addView(btnShareLog, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ))

        updateDependentEnrollmentSummary()
        return layout
    }

    private fun updateDependentEnrollmentSummary() {
        val prefs = getSharedPreferences("guardian_family_prefs", Context.MODE_PRIVATE)
        val enrolledDepId = prefs.getString("this_device_dependent_id", "dep-grandpa")
        val dep = familyManager.listDependents().firstOrNull { it.dependentId == enrolledDepId }
            ?: familyManager.listDependents().firstOrNull()
        if (dep != null) {
            val caretakers = familyManager.getCaretakersForDependent(dep.dependentId)
            val ctNames = caretakers.joinToString(", ") { "${it.name} (${it.phoneNumber})" }.ifBlank { "None assigned" }
            dependentEnrollmentSummary.text =
                "Handset Owner: ${dep.name} · ${dep.role.displayLabel}\n" +
                "Phone: ${dep.phoneNumber}\n" +
                "Monitored By Caretakers: $ctNames"
        } else {
            dependentEnrollmentSummary.text = "Not enrolled yet. Tap below to register this device and link parents/caretakers."
        }
    }

    private fun buildCaretakerDashboardView(): LinearLayout {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        val headerTitle = TextView(this).apply {
            text = "🛡️ Family Protection Dashboard"
            textSize = 22f
            setTextColor(Color.parseColor("#38BDF8"))
            setTypeface(null, Typeface.BOLD)
        }
        layout.addView(headerTitle)

        val headerSub = TextView(this).apply {
            text = "Multi-Caretaker ↔ Multi-Dependent Hub (Parents monitoring Grandparents & Kids)"
            textSize = 13f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, 4, 0, 18)
        }
        layout.addView(headerSub)

        // Action row: Add/Link Family Member + Sync Server
        val topActions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        val btnManageFamily = Button(this).apply {
            text = getString(R.string.btn_manage_family)
            textSize = 13f
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = roundedBg("#2563EB", 16f)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1.2f).apply {
                marginEnd = 8
            }
            setOnClickListener { showManageFamilyDialog() }
        }
        val btnSyncServer = Button(this).apply {
            text = getString(R.string.btn_sync_server)
            textSize = 13f
            isAllCaps = false
            setTextColor(Color.parseColor("#E2E8F0"))
            background = roundedBg("#334155", 16f)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 0.8f).apply {
                marginStart = 8
            }
            setOnClickListener { showServerSyncDialog() }
        }
        topActions.addView(btnManageFamily)
        topActions.addView(btnSyncServer)
        layout.addView(topActions, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 20 })

        // Section: Viewing as Caretaker (Parent selector)
        val ctLabel = TextView(this).apply {
            text = "👁️ Viewing as Caretaker (Parent / Guardian):"
            textSize = 13f
            setTextColor(Color.parseColor("#94A3B8"))
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, 8)
        }
        layout.addView(ctLabel)

        val ctScroll = HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
        }
        caretakerSelectRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        ctScroll.addView(caretakerSelectRow)
        layout.addView(ctScroll, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 16 })

        // Section: Monitored Dependents Filter (All, Grandparents, Kids, or specific Dependent)
        val depLabel = TextView(this).apply {
            text = "🛡️ Filter by Protected Dependent (Grandparents & Kids):"
            textSize = 13f
            setTextColor(Color.parseColor("#94A3B8"))
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, 8)
        }
        layout.addView(depLabel)

        val depScroll = HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
        }
        dependentFilterRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        depScroll.addView(dependentFilterRow)
        layout.addView(depScroll, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 20 })

        // Scam Intelligence Cross-Dependent Map Card
        scamIntelContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        layout.addView(scamIntelContainer, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 20 })

        // Screened Calls Header
        val callsHeader = TextView(this).apply {
            text = "📞 Screened Calls, Replay & 1930 / Chakshu Dossiers"
            textSize = 16f
            setTextColor(Color.WHITE)
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, 12)
        }
        layout.addView(callsHeader)

        callsListContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        layout.addView(callsListContainer)

        return layout
    }

    private fun refreshCaretakerDashboard() {
        // 1. Render Caretaker selector pills
        caretakerSelectRow.removeAllViews()
        val caretakers = familyManager.listCaretakers()
        for (ct in caretakers) {
            val isSelected = ct.caretakerId == activeCaretakerId
            val monitoredCount = familyManager.getDependentsForCaretaker(ct.caretakerId).size
            val pill = Button(this).apply {
                text = "${ct.name} · $monitoredCount protected"
                textSize = 12f
                isAllCaps = false
                setTextColor(if (isSelected) Color.WHITE else Color.parseColor("#CBD5E1"))
                background = roundedBg(
                    if (isSelected) "#0284C7" else "#1E293B",
                    18f,
                    strokeColor = if (isSelected) "#38BDF8" else "#334155"
                )
                setPadding(28, 14, 28, 14)
                setOnClickListener {
                    activeCaretakerId = ct.caretakerId
                    refreshCaretakerDashboard()
                }
            }
            caretakerSelectRow.addView(pill, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { marginEnd = 10 })
        }

        // 2. Render Dependent filter pills for active caretaker
        dependentFilterRow.removeAllViews()
        val monitoredDeps = if (activeCaretakerId != null) {
            familyManager.getDependentsForCaretaker(activeCaretakerId!!)
        } else {
            familyManager.listDependents()
        }

        fun addDepFilterPill(label: String, isActive: Boolean, onClick: () -> Unit) {
            val btn = Button(this).apply {
                text = label
                textSize = 12f
                isAllCaps = false
                setTextColor(if (isActive) Color.WHITE else Color.parseColor("#CBD5E1"))
                background = roundedBg(
                    if (isActive) "#059669" else "#1E293B",
                    18f,
                    strokeColor = if (isActive) "#34D399" else "#334155"
                )
                setPadding(24, 12, 24, 12)
                setOnClickListener { onClick() }
            }
            dependentFilterRow.addView(btn, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { marginEnd = 8 })
        }

        addDepFilterPill(
            label = "All Monitored (${monitoredDeps.size})",
            isActive = selectedDependentId == null && selectedRoleFilter == null
        ) {
            selectedDependentId = null
            selectedRoleFilter = null
            refreshCaretakerDashboard()
        }

        addDepFilterPill(
            label = "👴 Grandparents",
            isActive = selectedDependentId == null && selectedRoleFilter == DependentRole.GRANDPARENT
        ) {
            selectedDependentId = null
            selectedRoleFilter = DependentRole.GRANDPARENT
            refreshCaretakerDashboard()
        }

        addDepFilterPill(
            label = "🧒 Kids",
            isActive = selectedDependentId == null && selectedRoleFilter == DependentRole.CHILD
        ) {
            selectedDependentId = null
            selectedRoleFilter = DependentRole.CHILD
            refreshCaretakerDashboard()
        }

        for (dep in monitoredDeps) {
            val icon = when (dep.role) {
                DependentRole.GRANDPARENT -> "👴"
                DependentRole.CHILD -> "🧒"
                else -> "🛡️"
            }
            addDepFilterPill(
                label = "$icon ${dep.name}",
                isActive = selectedDependentId == dep.dependentId
            ) {
                selectedDependentId = dep.dependentId
                selectedRoleFilter = null
                refreshCaretakerDashboard()
            }
        }

        // 3. Render Scam Intelligence Map Card (cross-dependent syndicate correlation)
        scamIntelContainer.removeAllViews()
        val clusters = familyManager.buildScamIntelligenceClusters()
        val intelCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = roundedBg("#1E293B", 24f, strokeColor = "#38BDF8")
            setPadding(28, 24, 28, 24)
        }
        val intelHeader = TextView(this).apply {
            text = "🔗 Scam Intelligence Map · Linked Syndicates (${clusters.size})"
            textSize = 15f
            setTextColor(Color.parseColor("#38BDF8"))
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, 8)
        }
        intelCard.addView(intelHeader)

        if (clusters.isEmpty()) {
            val emptyIntel = TextView(this).apply {
                text = "Correlates repeat scam syndicates sharing UPI IDs or bank accounts across Grandparents and Kids."
                textSize = 13f
                setTextColor(Color.parseColor("#94A3B8"))
            }
            intelCard.addView(emptyIntel)
        } else {
            for (cl in clusters) {
                val kindBadge = if (cl.kind == "upi") "UPI Handle" else "Bank A/C"
                val row = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    background = roundedBg("#0F172A", 14f)
                    setPadding(20, 16, 20, 16)
                }
                val titleLine = TextView(this).apply {
                    text = "⚠️ $kindBadge: ${cl.identifier} (Shared across ${cl.callCount} calls)"
                    textSize = 13f
                    setTextColor(Color.parseColor("#FCA5A5"))
                    setTypeface(null, Typeface.BOLD)
                }
                val depLine = TextView(this).apply {
                    val targeted = cl.targetedDependents.joinToString(", ").ifBlank { "Multiple family members" }
                    text = "Targeted Dependents: $targeted"
                    textSize = 12f
                    setTextColor(Color.parseColor("#CBD5E1"))
                    setPadding(0, 4, 0, 6)
                }
                val copyClusterBtn = Button(this).apply {
                    text = "Copy Syndicate Identifier (${cl.identifier})"
                    textSize = 11f
                    isAllCaps = false
                    setTextColor(Color.WHITE)
                    background = roundedBg("#334155", 12f)
                    setOnClickListener {
                        copyToClipboard("Syndicate ${cl.kind}", cl.identifier)
                    }
                }
                row.addView(titleLine)
                row.addView(depLine)
                row.addView(copyClusterBtn)
                intelCard.addView(row, LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { topMargin = 10 })
            }
        }
        scamIntelContainer.addView(intelCard)

        // 4. Render Filtered Call Cards
        callsListContainer.removeAllViews()
        val calls = familyManager.getCalls(
            caretakerId = activeCaretakerId,
            dependentId = selectedDependentId,
            roleFilter = selectedRoleFilter
        )

        if (calls.isEmpty()) {
            val emptyView = TextView(this).apply {
                text = "🛡️ No screened calls match this dependent filter yet."
                textSize = 14f
                setTextColor(Color.parseColor("#94A3B8"))
                gravity = Gravity.CENTER
                setPadding(32, 48, 32, 48)
                background = roundedBg("#1E293B", 20f)
            }
            callsListContainer.addView(emptyView)
        } else {
            for (call in calls) {
                callsListContainer.addView(buildCallCard(call), LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { bottomMargin = 20 })
            }
        }
    }

    private fun buildCallCard(call: ScreenedCallDossier): LinearLayout {
        val isScam = call.verdict.lowercase() == "scam"
        val strokeCol = if (isScam) "#EF4444" else "#22C55E"

        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = roundedBg("#1E293B", 24f, strokeColor = strokeCol)
            setPadding(28, 24, 28, 24)
        }

        // Top badge row: Verdict + Evidence Verification status + Duration
        val topRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val verdictBadge = TextView(this).apply {
            text = if (isScam) "🚨 SUSPECTED SCAM" else "✅ GENUINE"
            textSize = 11f
            setTypeface(null, Typeface.BOLD)
            setTextColor(if (isScam) Color.parseColor("#FCA5A5") else Color.parseColor("#86EFAC"))
            background = roundedBg(if (isScam) "#7F1D1D" else "#14532D", 10f)
            setPadding(16, 6, 16, 6)
        }
        val evBadge = TextView(this).apply {
            val isConfirmed = call.evidenceStatus == "confirmed_by_family"
            text = if (isConfirmed) "✅ CONFIRMED BY FAMILY" else "⏳ DRAFT EVIDENCE"
            textSize = 11f
            setTypeface(null, Typeface.BOLD)
            setTextColor(if (isConfirmed) Color.parseColor("#86EFAC") else Color.parseColor("#FDE047"))
            background = roundedBg(if (isConfirmed) "#064E3B" else "#422006", 10f)
            setPadding(16, 6, 16, 6)
        }
        val durText = TextView(this).apply {
            text = "${call.durationSeconds}s"
            textSize = 12f
            setTextColor(Color.parseColor("#94A3B8"))
            gravity = Gravity.END
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        }
        topRow.addView(verdictBadge)
        topRow.addView(evBadge, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { marginStart = 10 })
        topRow.addView(durText)
        card.addView(topRow)

        // Protected Dependent & Monitored Caretakers tag
        val depName = call.dependentName ?: "Protected Family Member"
        val caretakersForDep = call.dependentId?.let { familyManager.getCaretakersForDependent(it) }.orEmpty()
        val ctNamesShort = caretakersForDep.joinToString(", ") { it.name.substringBefore(" ") }
        val depBadge = TextView(this).apply {
            text = "🛡️ Protected: $depName (${call.dependentRole.displayLabel})" +
                if (ctNamesShort.isNotBlank()) " · Guardians: $ctNamesShort" else ""
            textSize = 12f
            setTextColor(Color.parseColor("#38BDF8"))
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 10, 0, 4)
        }
        card.addView(depBadge)

        val callerTv = TextView(this).apply {
            text = "Caller: ${call.callerNumber}"
            textSize = 17f
            setTextColor(Color.WHITE)
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 2, 0, 6)
        }
        card.addView(callerTv)

        val summaryTv = TextView(this).apply {
            text = call.summary
            textSize = 14f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, 0, 0, 12)
        }
        card.addView(summaryTv)

        // Extracted Intel tags (tap any chip to copy to clipboard)
        val intel = call.extractedIntel
        if (!intel.isEmpty()) {
            val intelTitle = TextView(this).apply {
                text = "Captured Scammer Intel (Tap to copy):"
                textSize = 12f
                setTextColor(Color.parseColor("#94A3B8"))
                setPadding(0, 0, 0, 6)
            }
            card.addView(intelTitle)

            val intelWrap = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
            }
            for (upi in intel.upiIds) {
                intelWrap.addView(buildCopyableIntelChip("UPI ID", upi, "#312E81", "#C7D2FE"))
            }
            for (acc in intel.bankAccounts) {
                intelWrap.addView(buildCopyableIntelChip("Bank A/C", acc, "#064E3B", "#A7F3D0"))
            }
            for (ifsc in intel.ifscCodes) {
                intelWrap.addView(buildCopyableIntelChip("IFSC", ifsc, "#14532D", "#BBF7D0"))
            }
            for (ph in intel.phoneNumbers) {
                intelWrap.addView(buildCopyableIntelChip("Scammer Phone", ph, "#701A75", "#F5D0FE"))
            }
            for (lnk in intel.phishingLinks) {
                intelWrap.addView(buildCopyableIntelChip("Phishing Link", lnk, "#831843", "#FBCFE8"))
            }
            card.addView(intelWrap, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = 12 })
        }

        // Primary Actions: Replay & Full Dossier | Confirm Evidence | 1-Click Police & DoT Packets
        val actionRow1 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        val btnInspectReplay = Button(this).apply {
            text = "🎧 Replay, Transcript & Evidence Dossier"
            textSize = 13f
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = roundedBg("#2563EB", 16f)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            setOnClickListener { showCallDossierDialog(call.callId) }
        }
        actionRow1.addView(btnInspectReplay)
        card.addView(actionRow1, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 8 })

        val actionRow2 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        val btnChakshu = Button(this).apply {
            text = "📋 Copy Chakshu (DoT)"
            textSize = 12f
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = roundedBg("#334155", 14f)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                marginEnd = 6
            }
            setOnClickListener {
                val pkt = familyManager.formatChakshuPacket(call.callId)
                copyToClipboard("Chakshu Packet", pkt)
            }
        }
        val btn1930 = Button(this).apply {
            text = "🚨 Copy 1930 Report"
            textSize = 12f
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = roundedBg("#334155", 14f)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                marginStart = 6
            }
            setOnClickListener {
                val pkt = familyManager.format1930ReportPacket(call.callId)
                copyToClipboard("1930 Cybercrime Packet", pkt)
            }
        }
        actionRow2.addView(btnChakshu)
        actionRow2.addView(btn1930)
        card.addView(actionRow2)

        return card
    }

    private fun buildCopyableIntelChip(label: String, value: String, bgHex: String, textHex: String): TextView {
        return TextView(this).apply {
            text = "📋 $label: $value"
            textSize = 12f
            setTextColor(Color.parseColor(textHex))
            background = roundedBg(bgHex, 12f)
            setPadding(20, 10, 20, 10)
            setOnClickListener {
                copyToClipboard(label, value)
            }
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = 6 }
        }
    }

    private fun showCallDossierDialog(callId: String) {
        val call = familyManager.getCall(callId) ?: return
        val scroll = ScrollView(this)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 32, 40, 32)
            setBackgroundColor(Color.parseColor("#0F172A"))
        }
        scroll.addView(container)

        val title = TextView(this).apply {
            text = "🎧 Full Call Replay & Evidence Dossier"
            textSize = 19f
            setTextColor(Color.parseColor("#38BDF8"))
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, 8)
        }
        container.addView(title)

        val meta = TextView(this).apply {
            text = "Protected Member: ${call.dependentName ?: "Family"} (${call.dependentRole.displayLabel})\n" +
                "Suspect Caller: ${call.callerNumber} · Duration: ${call.durationSeconds}s\n" +
                "Evidence Status: ${call.evidenceStatus}" + (call.confirmedAt?.let { " ($it)" } ?: "")
            textSize = 13f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, 0, 0, 16)
        }
        container.addView(meta)

        // Audio Recording Playback / Open Link Button
        if (!call.callRecordingUrl.isNullOrBlank()) {
            val btnPlayAudio = Button(this).apply {
                text = "▶️ Play / Open Call Audio Recording"
                textSize = 13f
                isAllCaps = false
                setTextColor(Color.WHITE)
                background = roundedBg("#0284C7", 16f)
                setOnClickListener {
                    openUrl(call.callRecordingUrl)
                }
            }
            container.addView(btnPlayAudio, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = 16 })
        }

        // Turn-by-turn Hinglish/Hindi Transcript
        val transHeader = TextView(this).apply {
            text = "💬 Turn-by-Turn Hinglish / Hindi Transcript:"
            textSize = 15f
            setTextColor(Color.WHITE)
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, 8)
        }
        container.addView(transHeader)

        if (call.transcript.isEmpty()) {
            val noTrans = TextView(this).apply {
                text = "No dialogue turns recorded."
                textSize = 13f
                setTextColor(Color.parseColor("#94A3B8"))
            }
            container.addView(noTrans)
        } else {
            for (turn in call.transcript) {
                val isCaller = turn.role.lowercase() in listOf("caller", "user", "scammer")
                val turnBox = TextView(this).apply {
                    val speaker = if (isCaller) "🚨 Scammer" else "🤖 GuardianLine AI"
                    text = "$speaker: ${turn.content}"
                    textSize = 13f
                    setTextColor(Color.parseColor(if (isCaller) "#FCA5A5" else "#A7F3D0"))
                    background = roundedBg(if (isCaller) "#450A0A" else "#064E3B", 14f)
                    setPadding(20, 14, 20, 14)
                }
                container.addView(turnBox, LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { bottomMargin = 8 })
            }
        }

        // Evidence Verification Button (draft -> confirmed_by_family)
        val verifyHeader = TextView(this).apply {
            text = "✅ Step 1: Family Evidence Verification"
            textSize = 15f
            setTextColor(Color.WHITE)
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 16, 0, 8)
        }
        container.addView(verifyHeader)

        val btnConfirmEvidence = Button(this).apply {
            val isConfirmed = call.evidenceStatus == "confirmed_by_family"
            text = if (isConfirmed) "✅ Evidence Confirmed by Family" else "Review and Confirm Evidence (draft → confirmed_by_family)"
            textSize = 13f
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = roundedBg(if (isConfirmed) "#059669" else "#D97706", 16f)
            setOnClickListener {
                val updated = familyManager.confirmEvidence(call.callId)
                if (updated != null) {
                    text = "✅ Evidence Confirmed by Family (${updated.confirmedAt})"
                    background = roundedBg("#059669", 16f)
                    meta.text = "Protected Member: ${updated.dependentName ?: "Family"} (${updated.dependentRole.displayLabel})\n" +
                        "Suspect Caller: ${updated.callerNumber} · Duration: ${updated.durationSeconds}s\n" +
                        "Evidence Status: ${updated.evidenceStatus} (${updated.confirmedAt})"
                    refreshCaretakerDashboard()
                    Toast.makeText(this@MainActivity, "Evidence confirmed! Ready for Chakshu & 1930 filing.", Toast.LENGTH_SHORT).show()
                }
            }
        }
        container.addView(btnConfirmEvidence, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 16 })

        // 1-Click Police & DoT Portals
        val portalHeader = TextView(this).apply {
            text = "🏛️ Step 2: 1-Click Police (1930) & DoT Chakshu Portals"
            textSize = 15f
            setTextColor(Color.WHITE)
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 8, 0, 8)
        }
        container.addView(portalHeader)

        val btnCopyAndOpenChakshu = Button(this).apply {
            text = "📋 Copy Packet & Open Chakshu (sancharsaathi.gov.in)"
            textSize = 13f
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = roundedBg("#2563EB", 16f)
            setOnClickListener {
                copyToClipboard("Chakshu Packet", familyManager.formatChakshuPacket(call.callId))
                openUrl("https://sancharsaathi.gov.in/sfc/")
            }
        }
        container.addView(btnCopyAndOpenChakshu, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 10 })

        val btnCopyAndOpen1930 = Button(this).apply {
            text = "🚨 Copy Dossier & Open Cybercrime Portal (cybercrime.gov.in)"
            textSize = 13f
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = roundedBg("#DC2626", 16f)
            setOnClickListener {
                copyToClipboard("1930 Cybercrime Dossier", familyManager.format1930ReportPacket(call.callId))
                openUrl("https://cybercrime.gov.in/")
            }
        }
        container.addView(btnCopyAndOpen1930, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 10 })

        val btnDial1930 = Button(this).apply {
            text = "📞 Dial 1930 National Cybercrime Helpline"
            textSize = 13f
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = roundedBg("#334155", 16f)
            setOnClickListener {
                startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:1930")))
            }
        }
        container.addView(btnDial1930)

        AlertDialog.Builder(this)
            .setView(scroll)
            .setPositiveButton("Close", null)
            .show()
    }

    private fun showManageFamilyDialog() {
        val scroll = ScrollView(this)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 32, 40, 24)
        }
        scroll.addView(layout)

        val title = TextView(this).apply {
            text = "👨‍👩‍👧‍👦 Add & Link Family Members"
            textSize = 18f
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, 8)
        }
        layout.addView(title)

        val desc = TextView(this).apply {
            text = "Supports multiple Caretakers (e.g. Father & Mother) monitoring multiple Dependents (Grandparents & Kids)."
            textSize = 13f
            setPadding(0, 0, 0, 16)
        }
        layout.addView(desc)

        val typeSpinner = Spinner(this)
        val typeOptions = listOf(
            "Protected Dependent (Grandparent)",
            "Protected Dependent (Kid / Child)",
            "Protected Dependent (Parent)",
            "Caretaker / Guardian (Parent)"
        )
        typeSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, typeOptions)
        layout.addView(typeSpinner)

        val inputName = EditText(this).apply {
            hint = "Full Name (e.g. Dada Ji / Aarav / Priya)"
        }
        layout.addView(inputName)

        val inputPhone = EditText(this).apply {
            hint = "Phone Number (e.g. +919810020005)"
        }
        layout.addView(inputPhone)

        val linkHeader = TextView(this).apply {
            text = "Link with Family Members (Many-to-Many):"
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 16, 0, 8)
        }
        layout.addView(linkHeader)

        val checkCaretakers = mutableListOf<Pair<CaretakerProfile, CheckBox>>()
        for (ct in familyManager.listCaretakers()) {
            val cb = CheckBox(this).apply {
                text = "Caretaker: ${ct.name} (${ct.phoneNumber})"
                isChecked = true
            }
            checkCaretakers.add(ct to cb)
            layout.addView(cb)
        }

        val checkDependents = mutableListOf<Pair<DependentProfile, CheckBox>>()
        for (dep in familyManager.listDependents()) {
            val cb = CheckBox(this).apply {
                text = "Dependent: ${dep.name} (${dep.role.displayLabel})"
                isChecked = true
            }
            checkDependents.add(dep to cb)
            layout.addView(cb)
        }

        val enrollThisHandsetCb = CheckBox(this).apply {
            text = "Set as this phone's active Dependent profile"
            isChecked = false
        }
        layout.addView(enrollThisHandsetCb)

        AlertDialog.Builder(this)
            .setView(scroll)
            .setPositiveButton("Save & Link") { _, _ ->
                val name = inputName.text.toString().trim()
                val phone = inputPhone.text.toString().trim()
                if (name.isBlank() || phone.isBlank()) {
                    Toast.makeText(this, "Name and phone number are required", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                val selIdx = typeSpinner.selectedItemPosition
                if (selIdx == 3) {
                    val newCt = familyManager.addCaretaker(name = name, phone = phone, role = CaretakerRole.PARENT)
                    for ((dep, cb) in checkDependents) {
                        if (cb.isChecked) {
                            familyManager.linkCaretakerToDependent(newCt.caretakerId, dep.dependentId)
                        }
                    }
                    activeCaretakerId = newCt.caretakerId
                } else {
                    val role = when (selIdx) {
                        0 -> DependentRole.GRANDPARENT
                        1 -> DependentRole.CHILD
                        else -> DependentRole.PARENT
                    }
                    val newDep = familyManager.addDependent(name = name, phone = phone, role = role)
                    for ((ct, cb) in checkCaretakers) {
                        if (cb.isChecked) {
                            familyManager.linkCaretakerToDependent(ct.caretakerId, newDep.dependentId)
                        }
                    }
                    if (enrollThisHandsetCb.isChecked) {
                        getSharedPreferences("guardian_family_prefs", Context.MODE_PRIVATE)
                            .edit()
                            .putString("this_device_dependent_id", newDep.dependentId)
                            .apply()
                    }
                }
                updateDependentEnrollmentSummary()
                refreshCaretakerDashboard()
                Toast.makeText(this, "Family Protection Circle updated!", Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showServerSyncDialog() {
        val prefs = getSharedPreferences("guardian_family_prefs", Context.MODE_PRIVATE)
        val savedUrl = prefs.getString("server_base_url", "http://127.0.0.1:8000") ?: "http://127.0.0.1:8000"
        val savedToken = prefs.getString(
            "dashboard_token",
            "x5CwYTEzbGHJfSVnftTN9VHkgbpOvwXRLQvPV9rgzr4"
        ) ?: ""

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 32, 40, 16)
        }
        val urlInput = EditText(this).apply {
            hint = "Backend URL (e.g. http://192.168.1.10:8000)"
            setText(savedUrl)
        }
        val tokenInput = EditText(this).apply {
            hint = "Dashboard Token (Bearer)"
            setText(savedToken)
        }
        layout.addView(urlInput)
        layout.addView(tokenInput)

        AlertDialog.Builder(this)
            .setTitle("Sync with GuardianLine Server")
            .setView(layout)
            .setPositiveButton("Sync Now") { _, _ ->
                val baseUrl = urlInput.text.toString().trim().trimEnd('/')
                val token = tokenInput.text.toString().trim()
                prefs.edit()
                    .putString("server_base_url", baseUrl)
                    .putString("dashboard_token", token)
                    .apply()
                syncFromBackend(baseUrl, token)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun syncFromBackend(baseUrl: String, token: String) {
        Toast.makeText(this, "Syncing family circle & calls from $baseUrl...", Toast.LENGTH_SHORT).show()
        thread {
            try {
                // 1. Fetch family topology
                val famConn = (URL("$baseUrl/dashboard/api/family").openConnection() as HttpURLConnection).apply {
                    requestMethod = "GET"
                    setRequestProperty("Authorization", "Bearer $token")
                    connectTimeout = 5000
                    readTimeout = 5000
                }
                if (famConn.responseCode == 200) {
                    val body = BufferedReader(InputStreamReader(famConn.inputStream)).use { it.readText() }
                    val root = JSONObject(body)
                    val depsArr = root.optJSONArray("dependents") ?: JSONArray()
                    for (i in 0 until depsArr.length()) {
                        val d = depsArr.getJSONObject(i)
                        familyManager.addDependent(
                            name = d.optString("name", "Dependent"),
                            phone = d.optString("phone_number", ""),
                            role = DependentRole.fromWire(d.optString("role", "grandparent")),
                            dependentId = d.optString("dependent_id", null)
                        )
                    }
                    val ctsArr = root.optJSONArray("caretakers") ?: JSONArray()
                    for (i in 0 until ctsArr.length()) {
                        val c = ctsArr.getJSONObject(i)
                        val ct = familyManager.addCaretaker(
                            name = c.optString("name", "Caretaker"),
                            phone = c.optString("phone_number", ""),
                            role = CaretakerRole.fromWire(c.optString("role", "parent")),
                            caretakerId = c.optString("caretaker_id", null)
                        )
                        val depIds = c.optJSONArray("dependent_ids") ?: JSONArray()
                        for (j in 0 until depIds.length()) {
                            familyManager.linkCaretakerToDependent(ct.caretakerId, depIds.getString(j))
                        }
                    }
                }

                // 2. Fetch screened calls
                val callsConn = (URL("$baseUrl/dashboard/api/calls?limit=50").openConnection() as HttpURLConnection).apply {
                    requestMethod = "GET"
                    setRequestProperty("Authorization", "Bearer $token")
                    connectTimeout = 5000
                    readTimeout = 5000
                }
                if (callsConn.responseCode == 200) {
                    val body = BufferedReader(InputStreamReader(callsConn.inputStream)).use { it.readText() }
                    val root = JSONObject(body)
                    val items = root.optJSONArray("items") ?: JSONArray()
                    for (i in 0 until items.length()) {
                        val item = items.getJSONObject(i)
                        val intelObj = item.optJSONObject("extracted_intel") ?: JSONObject()
                        val transArr = item.optJSONArray("transcript") ?: JSONArray()
                        val turns = mutableListOf<TranscriptTurn>()
                        for (t in 0 until transArr.length()) {
                            val to = transArr.getJSONObject(t)
                            turns.add(TranscriptTurn(to.optString("role", "caller"), to.optString("content", "")))
                        }
                        familyManager.upsertCall(
                            ScreenedCallDossier(
                                callId = item.optString("call_id", "call-$i"),
                                callerNumber = item.optString("caller_number", "Unknown"),
                                verdict = item.optString("verdict", "unsure"),
                                durationSeconds = item.optDouble("duration", 0.0).toInt(),
                                summary = item.optString("summary", ""),
                                dependentId = item.optString("dependent_id", "").ifBlank { "dep-grandpa" },
                                dependentName = item.optString("dependent_name", "").ifBlank { "Ramesh Sharma (Grandfather)" },
                                dependentRole = DependentRole.fromWire(item.optString("dependent_role", "grandparent")),
                                transcript = turns,
                                extractedIntel = ExtractedIntel(
                                    upiIds = jsonArrayToList(intelObj.optJSONArray("upi_ids")),
                                    bankAccounts = jsonArrayToList(intelObj.optJSONArray("bank_accounts")),
                                    ifscCodes = jsonArrayToList(intelObj.optJSONArray("ifsc_codes")),
                                    phoneNumbers = jsonArrayToList(intelObj.optJSONArray("phone_numbers")),
                                    phishingLinks = jsonArrayToList(intelObj.optJSONArray("links"))
                                ),
                                callRecordingUrl = item.optString("call_recording_url", null),
                                evidenceStatus = item.optString("evidence_status", "draft"),
                                confirmedAt = item.optString("confirmed_at", null)
                            )
                        )
                    }
                }
                runOnUiThread {
                    refreshCaretakerDashboard()
                    updateDependentEnrollmentSummary()
                    Toast.makeText(this, "Synced live calls & family circle from server!", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    Toast.makeText(this, "Offline / Local mode active (${e.message})", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun jsonArrayToList(arr: JSONArray?): List<String> {
        if (arr == null) return emptyList()
        val list = mutableListOf<String>()
        for (i in 0 until arr.length()) {
            val v = arr.optString(i, "").trim()
            if (v.isNotEmpty()) list.add(v)
        }
        return list
    }

    private fun copyToClipboard(label: String, text: String) {
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText(label, text))
        Toast.makeText(this, "Copied $label to clipboard", Toast.LENGTH_SHORT).show()
    }

    private fun openUrl(url: String) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (_: Exception) {
            Toast.makeText(this, "Cannot open URL: $url", Toast.LENGTH_SHORT).show()
        }
    }

    private fun roundedBg(fillHex: String, radiusPx: Float, strokeColor: String? = null): GradientDrawable {
        return GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = radiusPx
            setColor(Color.parseColor(fillHex))
            if (strokeColor != null) {
                setStroke(3, Color.parseColor(strokeColor))
            }
        }
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
                ProtectionStatusWorker.clearWarning(this)
                statusText.text = getString(R.string.status_active)
                statusText.setTextColor(Color.parseColor("#4ADE80"))
            } else {
                statusText.text = getString(R.string.status_warning_revoked)
                statusText.setTextColor(Color.parseColor("#F87171"))
            }
        } else {
            statusText.text = getString(R.string.status_unsupported)
            statusText.setTextColor(Color.parseColor("#FB923C"))
        }
    }

    private fun checkPermissionsStatus() {
        val hasContacts = ContextCompat.checkSelfPermission(
            this, Manifest.permission.READ_CONTACTS
        ) == PackageManager.PERMISSION_GRANTED

        if (hasContacts) {
            permText.text = getString(R.string.perm_contacts_granted)
            permText.setTextColor(Color.parseColor("#4ADE80"))
        } else {
            permText.text = getString(R.string.perm_contacts_missing)
            permText.setTextColor(Color.parseColor("#F87171"))
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

    /** Shares the last 200 soak-log lines (masked numbers only) for the T-AND 24-hour soak. */
    private fun shareSoakLog() {
        val lines = LocalCallLogger.readLogContent(this).lines().filter { it.isNotBlank() }
        if (lines.isEmpty()) {
            Toast.makeText(this, getString(R.string.toast_log_empty), Toast.LENGTH_LONG).show()
            return
        }
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_SUBJECT, "GuardianLine screening log")
            putExtra(Intent.EXTRA_TEXT, lines.takeLast(200).joinToString(separator = "\n"))
        }
        startActivity(Intent.createChooser(send, getString(R.string.btn_share_log)))
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
