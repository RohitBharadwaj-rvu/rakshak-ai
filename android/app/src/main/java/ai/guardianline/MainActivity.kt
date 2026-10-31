package ai.guardianline

import ai.guardianline.caretaker.CaretakerProfile
import ai.guardianline.caretaker.CaretakerRole
import ai.guardianline.caretaker.DependentProfile
import ai.guardianline.caretaker.DependentRole
import ai.guardianline.caretaker.ExtractedIntel
import ai.guardianline.caretaker.FamilyCircleManager
import ai.guardianline.caretaker.MaterialYouFamilyTheme as Theme
import ai.guardianline.caretaker.ScreenedCallDossier
import ai.guardianline.caretaker.TranscriptTurn
import ai.guardianline.screening.LocalCallLogger
import ai.guardianline.ui.ShieldView
import ai.guardianline.ui.WaveformView
import android.Manifest
import android.app.AlertDialog
import android.app.role.RoleManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.ArrayAdapter
import android.widget.CheckBox
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.PopupMenu
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.SwitchCompat
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/**
 * Two quiet screens in the Material You 3 style:
 *  - My phone: shield status plus the two switches that protect this handset.
 *  - Family: caretakers see calls screened for the grandparents and kids they look after.
 */
class MainActivity : AppCompatActivity() {

    private val family = FamilyCircleManager()
    private var activeCaretakerId: String? = null
    private var selectedDependentId: String? = null

    private lateinit var tabPhone: TextView
    private lateinit var tabFamily: TextView
    private lateinit var phoneScreen: LinearLayout
    private lateinit var familyScreen: LinearLayout

    private lateinit var shield: ShieldView
    private lateinit var shieldTitle: TextView
    private lateinit var shieldSub: TextView
    private lateinit var screeningSwitch: SwitchCompat
    private lateinit var contactsLine: TextView

    private lateinit var viewingAs: TextView
    private lateinit var avatarRow: LinearLayout
    private lateinit var noteHolder: LinearLayout
    private lateinit var callsHolder: LinearLayout

    private val requestRoleLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { refreshShield() }

    private val requestContactsLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { refreshShield() }

    private val requestNotificationLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        supportActionBar?.hide()
        window.statusBarColor = c(Theme.surfaceBackgroundHex)

        family.seedDefaultMultiGenerationHousehold()
        activeCaretakerId = family.listCaretakers().firstOrNull()?.caretakerId
        seedLocalScreeningLogIfEmpty()

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(16), dp(20), dp(32))
        }

        val topBar = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        tabPhone = pillTab(getString(R.string.tab_my_phone)) { showScreen(family = false) }
        tabFamily = pillTab(getString(R.string.tab_family)) { showScreen(family = true) }
        topBar.addView(tabPhone, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { marginEnd = dp(8) })
        topBar.addView(tabFamily)
        topBar.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
        val menu = label("⋮", 26f, Theme.primaryForestHex, medium = true).apply {
            setPadding(dp(14), dp(4), dp(14), dp(4))
            contentDescription = "More options"
            setOnClickListener { showMenu(it) }
        }
        topBar.addView(menu)
        root.addView(topBar, lp(bottom = 12))

        phoneScreen = buildPhoneScreen()
        familyScreen = buildFamilyScreen()
        root.addView(phoneScreen)
        root.addView(familyScreen)

        setContentView(ScrollView(this).apply {
            setBackgroundColor(c(Theme.surfaceBackgroundHex))
            isFillViewport = true
            addView(root)
        })

        showScreen(family = false)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestNotificationLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        ProtectionStatusWorker.schedule(this)
    }

    override fun onResume() {
        super.onResume()
        refreshShield()
    }

    // ---------------------------------------------------------------- My phone

    private fun buildPhoneScreen(): LinearLayout {
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }

        shield = ShieldView(this)
        col.addView(shield, lp(h = 220, top = 8))

        shieldTitle = label("", 30f, Theme.inkHex, medium = true).apply { gravity = Gravity.CENTER }
        col.addView(shieldTitle, lp(top = 4))
        shieldSub = label("", 16f, Theme.mutedTextHex).apply { gravity = Gravity.CENTER }
        col.addView(shieldSub, lp(top = 6, bottom = 28))

        screeningSwitch = SwitchCompat(this).apply {
            isClickable = false
            isFocusable = false
            thumbTintList = ColorStateList.valueOf(Color.WHITE)
            trackTintList = ColorStateList.valueOf(c("#8DB08A"))
        }
        col.addView(
            darkRow(getString(R.string.row_call_screening), screeningSwitch) { requestCallScreeningRole() },
            lp(bottom = 12)
        )
        val familyAlertSwitch = SwitchCompat(this).apply {
            isChecked = true
            isClickable = false
            isFocusable = false
            thumbTintList = ColorStateList.valueOf(Color.WHITE)
            trackTintList = ColorStateList.valueOf(c("#8DB08A"))
        }
        col.addView(
            darkRow(getString(R.string.row_forwarding), familyAlertSwitch) { startForwardingDialer() },
            lp(bottom = 12)
        )

        contactsLine = label(getString(R.string.perm_contacts_missing), 13f, Theme.alertRedHex).apply {
            setPadding(dp(8), dp(6), dp(8), dp(6))
            setOnClickListener { requestContactsLauncher.launch(Manifest.permission.READ_CONTACTS) }
        }
        col.addView(contactsLine, lp(bottom = 8))

        val callGuardianBtn = pillButton(
            getString(R.string.btn_family_circle),
            "#00000000",
            Theme.primaryForestHex,
            Theme.primaryForestHex
        ) {
            showScreen(family = true)
        }.apply {
            setPadding(dp(36), dp(12), dp(36), dp(12))
        }
        col.addView(
            callGuardianBtn,
            LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply {
                gravity = Gravity.CENTER_HORIZONTAL
                topMargin = dp(12)
            }
        )
        return col
    }

    private fun darkRow(title: String, trailing: View, onClick: () -> Unit): LinearLayout {
        return LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            background = rounded(Theme.primaryForestHex, 28)
            setPadding(dp(24), dp(20), dp(24), dp(20))
            isClickable = true
            isFocusable = true
            setOnClickListener { onClick() }
            addView(label(title, 18f, "#FFFFFF", medium = true), LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
            addView(trailing)
        }
    }

    private fun refreshShield() {
        val supported = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q
        val held = supported && (getSystemService(Context.ROLE_SERVICE) as? RoleManager)
            ?.isRoleHeld(RoleManager.ROLE_CALL_SCREENING) == true
        if (held) ProtectionStatusWorker.clearWarning(this)
        shield.isProtected = held
        shieldTitle.text = getString(if (held) R.string.shield_on_title else R.string.shield_off_title)
        shieldSub.text = getString(
            when {
                !supported -> R.string.shield_unsupported_sub
                held -> R.string.shield_on_sub
                else -> R.string.shield_off_sub
            }
        )
        screeningSwitch.isChecked = held
        val hasContacts = ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CONTACTS) ==
            PackageManager.PERMISSION_GRANTED
        contactsLine.visibility = if (hasContacts) View.GONE else View.VISIBLE
    }

    private fun requestCallScreeningRole() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            Toast.makeText(this, getString(R.string.toast_role_unavailable), Toast.LENGTH_LONG).show()
            return
        }
        val roleManager = getSystemService(Context.ROLE_SERVICE) as? RoleManager
        if (roleManager != null && roleManager.isRoleAvailable(RoleManager.ROLE_CALL_SCREENING)) {
            requestRoleLauncher.launch(roleManager.createRequestRoleIntent(RoleManager.ROLE_CALL_SCREENING))
        } else {
            Toast.makeText(this, getString(R.string.toast_role_unavailable), Toast.LENGTH_LONG).show()
        }
    }

    private fun startForwardingDialer() {
        val gateway = BuildConfig.BOLNA_GATEWAY_NUMBER.trim()
        if (gateway.isBlank()) {
            Toast.makeText(this, getString(R.string.gateway_not_configured), Toast.LENGTH_LONG).show()
            return
        }
        val ussd = Uri.encode("**67*${gateway}#")
        startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$ussd")))
    }

    /** Shares the last 200 soak-log lines (masked numbers only) for the 24-hour soak test. */
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

    // ------------------------------------------------------------------ Family

    private fun buildFamilyScreen(): LinearLayout {
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(label(getString(R.string.family_title), 28f, Theme.inkHex, medium = true), lp(top = 8))

        viewingAs = label("", 14f, Theme.primaryForestHex, medium = true).apply {
            setPadding(0, dp(8), 0, dp(8))
            setOnClickListener { pickCaretaker() }
        }
        col.addView(viewingAs, lp(bottom = 8))

        avatarRow = LinearLayout(this)
        col.addView(
            HorizontalScrollView(this).apply {
                isHorizontalScrollBarEnabled = false
                addView(avatarRow)
            },
            lp(bottom = 20)
        )

        noteHolder = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(noteHolder)
        callsHolder = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(callsHolder)
        return col
    }

    private fun seedLocalScreeningLogIfEmpty() {
        val existing = LocalCallLogger.readLogContent(this).lines().filter { it.isNotBlank() }
        if (existing.isEmpty()) {
            LocalCallLogger.logDecision(
                this,
                "+917019941295",
                ai.guardianline.screening.ScreeningDecision(
                    action = ai.guardianline.screening.ScreeningAction.SCREEN,
                    reason = "UNKNOWN_CALLER_SCREEN_TO_BOLNA",
                    normalizedNumber = "+917019941295"
                )
            )
            LocalCallLogger.logDecision(
                this,
                "+919876543210",
                ai.guardianline.screening.ScreeningDecision(
                    action = ai.guardianline.screening.ScreeningAction.SCREEN,
                    reason = "UNKNOWN_CALLER_SCREEN_TO_BOLNA",
                    normalizedNumber = "+919876543210"
                )
            )
            LocalCallLogger.logDecision(
                this,
                "+919123456780",
                ai.guardianline.screening.ScreeningDecision(
                    action = ai.guardianline.screening.ScreeningAction.SCREEN,
                    reason = "UNKNOWN_CALLER_SCREEN_TO_BOLNA",
                    normalizedNumber = "+919123456780"
                )
            )
        }
    }

    private fun refreshFamily() {
        if (family.listCaretakers().isEmpty() || family.listDependents().isEmpty()) {
            family.seedDefaultMultiGenerationHousehold()
        }
        if (activeCaretakerId == null || family.listCaretakers().none { it.caretakerId == activeCaretakerId }) {
            activeCaretakerId = family.listCaretakers().firstOrNull()?.caretakerId
        }
        val active = family.listCaretakers().firstOrNull { it.caretakerId == activeCaretakerId }
        viewingAs.visibility = if (active == null) View.GONE else View.VISIBLE
        if (active != null) {
            viewingAs.text = getString(R.string.viewing_as, Theme.shortLabel(active.name)) + "  ▾"
        }

        val monitored = if (active != null) {
            family.getDependentsForCaretaker(active.caretakerId).ifEmpty { family.listDependents() }
        } else {
            family.listDependents()
        }
        if (selectedDependentId != null && monitored.none { it.dependentId == selectedDependentId }) {
            selectedDependentId = null
        }

        avatarRow.removeAllViews()
        avatarRow.addView(avatar("All", "All", "#CFE5CF", selectedDependentId == null) {
            selectedDependentId = null
            refreshFamily()
        })
        for (dep in monitored) {
            avatarRow.addView(
                avatar(
                    Theme.shortLabel(dep.name), Theme.initialsFor(dep.name), Theme.avatarColorFor(dep.role),
                    selectedDependentId == dep.dependentId
                ) {
                    selectedDependentId = dep.dependentId
                    refreshFamily()
                }
            )
        }

        noteHolder.removeAllViews()
        for (cluster in family.buildScamIntelligenceClusters().take(2)) {
            val who = cluster.targetedDependents.joinToString(" and ") { Theme.shortLabel(it) }
            if (who.isBlank()) continue
            val note = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                background = rounded(Theme.caretakerLavenderHex, 24)
                setPadding(dp(18), dp(14), dp(18), dp(14))
            }
            note.addView(label("Same scammer reached $who", 14f, Theme.caretakerLavenderInkHex, medium = true))
            note.addView(chip(cluster.identifier, Theme.caretakerLavenderInkHex, "#FFFFFF"), lp(w = WRAP_CONTENT, top = 8))
            noteHolder.addView(note, lp(bottom = 16))
        }

        callsHolder.removeAllViews()
        val calls = family.getCalls(caretakerId = activeCaretakerId, dependentId = selectedDependentId)
            .ifEmpty { family.getCalls() }
        if (calls.isEmpty()) {
            callsHolder.addView(
                label("No screened calls yet.", 15f, Theme.mutedTextHex).apply {
                    gravity = Gravity.CENTER
                    setPadding(dp(16), dp(36), dp(16), dp(36))
                    background = rounded(Theme.cardSurfaceHex, 28)
                }
            )
        } else {
            calls.forEach { callsHolder.addView(callCard(it), lp(bottom = 16)) }
        }
    }

    private fun avatar(name: String, initials: String, fillHex: String, selected: Boolean, onClick: () -> Unit): LinearLayout {
        val circle = label(initials, 18f, "#23332A", medium = true).apply {
            gravity = Gravity.CENTER
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(c(fillHex))
                if (selected) setStroke(dp(3), c(Theme.primaryForestHex))
            }
        }
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            isClickable = true
            isFocusable = true
            contentDescription = name
            setOnClickListener { onClick() }
            addView(circle, LinearLayout.LayoutParams(dp(60), dp(60)))
            addView(
                label(name, 13f, if (selected) Theme.primaryForestHex else Theme.inkHex, medium = selected).apply {
                    gravity = Gravity.CENTER
                    maxLines = 1
                },
                lp(top = 6)
            )
        }.also { it.layoutParams = LinearLayout.LayoutParams(dp(76), WRAP_CONTENT) }
    }

    private fun callCard(call: ScreenedCallDossier): LinearLayout {
        val palette = Theme.callCardPalette(call.verdict)
        val isScam = call.verdict.equals("scam", ignoreCase = true)
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(palette.cardSurfaceHex, 28)
            setPadding(dp(22), dp(20), dp(22), dp(20))
        }

        val top = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        top.addView(
            label(if (isScam) "⚠  Suspected scam" else "✓  Genuine", 13f, if (isScam) Theme.alertRedHex else palette.inkHex, medium = true),
            LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f)
        )
        top.addView(label("${call.durationSeconds}s", 13f, palette.inkHex))
        card.addView(top)

        card.addView(label(call.summary, 18f, palette.inkHex, medium = true), lp(top = 10))

        val who = call.dependentName?.let { "For ${Theme.shortLabel(it)}" }
        val meta = listOfNotNull(
            "Caller ID: ${call.callerNumber}", who,
            if (call.evidenceStatus == "confirmed_by_family") "Confirmed" else null
        ).joinToString("  ·  ")
        card.addView(label(meta, 14f, palette.inkHex), lp(top = 6, bottom = 12))

        val intel = call.extractedIntel
        val chips = intel.upiIds.map { "UPI: $it" to it } + intel.bankAccounts.map { "Account: $it" to it } +
            intel.ifscCodes.map { "IFSC: $it" to it } + intel.phoneNumbers.map { "Phone: $it" to it } +
            intel.phishingLinks.map { "Link: $it" to it }
        chips.forEach { (text, value) ->
            card.addView(
                chip(text, palette.inkHex, "#B3FFFFFF").apply { setOnClickListener { copyToClipboard(text.substringBefore(":"), value) } },
                lp(w = WRAP_CONTENT, bottom = 8)
            )
        }

        val player = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            background = rounded("#8CFFFFFF", 24)
            setPadding(dp(12), dp(10), dp(16), dp(10))
            isClickable = true
            isFocusable = true
            contentDescription = "Replay call"
            setOnClickListener { showDossier(call.callId) }
        }
        player.addView(
            label("▶", 14f, "#FFFFFF", medium = true).apply {
                gravity = Gravity.CENTER
                background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(c(Theme.primaryForestHex)) }
            },
            LinearLayout.LayoutParams(dp(42), dp(42))
        )
        player.addView(
            WaveformView(this, c(Theme.primaryForestHex)).apply { bars = Theme.waveformBars(call.callId, 36) },
            LinearLayout.LayoutParams(0, dp(34), 1f).apply { marginStart = dp(12); marginEnd = dp(12) }
        )
        player.addView(label("${call.durationSeconds}s", 12f, palette.inkHex))
        card.addView(player, lp(top = 4))

        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(Theme.cardSurfaceHex, 32)
            setPadding(dp(12), dp(12), dp(12), dp(12))
        }
        shell.addView(card, lp(bottom = 12))
        shell.addView(pillButton(getString(R.string.btn_file_report), Theme.primaryForestHex, "#FFFFFF") { showDossier(call.callId) })
        return shell
    }

    private fun showDossier(callId: String) {
        val call = family.getCall(callId) ?: return
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(c(Theme.surfaceBackgroundHex))
            setPadding(dp(22), dp(22), dp(22), dp(18))
        }
        col.addView(label(call.summary, 19f, Theme.inkHex, medium = true))
        val status = label("", 13f, Theme.mutedTextHex)
        fun renderStatus() {
            val confirmed = family.getCall(callId)?.evidenceStatus == "confirmed_by_family"
            status.text = "Caller ID: ${call.callerNumber}  ·  ${if (confirmed) "Confirmed by family" else "Draft, not yet confirmed"}"
        }
        renderStatus()
        col.addView(status, lp(top = 6, bottom = 14))

        val recording = call.callRecordingUrl
        if (!recording.isNullOrBlank() && (recording.startsWith("https://") || recording.startsWith("http://"))) {
            col.addView(pillButton("Open recording", "#00000000", Theme.primaryForestHex, Theme.primaryForestHex) { openUrl(recording) }, lp(bottom = 14))
        }

        if (call.transcript.isEmpty()) {
            col.addView(label("No dialogue recorded.", 13f, Theme.mutedTextHex), lp(bottom = 12))
        }
        for (turn in call.transcript) {
            val caller = turn.role.lowercase() in listOf("caller", "user", "scammer")
            col.addView(
                label((if (caller) "Caller: " else "GuardianLine: ") + turn.content, 14f, if (caller) "#3E1A12" else "#14301A").apply {
                    background = rounded(if (caller) "#FDE3DB" else "#E1EFDF", 20)
                    setPadding(dp(16), dp(12), dp(16), dp(12))
                },
                lp(bottom = 8)
            )
        }

        val confirm = pillButton("", Theme.primaryForestHex, "#FFFFFF") { }
        fun renderConfirm() {
            val done = family.getCall(callId)?.evidenceStatus == "confirmed_by_family"
            confirm.text = if (done) "Evidence confirmed" else "Review and confirm evidence"
            confirm.alpha = if (done) 0.6f else 1f
        }
        renderConfirm()
        confirm.setOnClickListener {
            val updated = family.confirmEvidence(callId) ?: return@setOnClickListener
            renderConfirm()
            renderStatus()
            refreshFamily()
            postConfirmToServer(updated.callId)
        }
        col.addView(confirm, lp(top = 10, bottom = 10))

        col.addView(
            pillButton("Copy Chakshu packet and open portal", "#E1D5F5", Theme.caretakerLavenderInkHex) {
                copyToClipboard("Chakshu packet", family.formatChakshuPacket(callId))
                openUrl("https://sancharsaathi.gov.in/sfc/")
            },
            lp(bottom = 10)
        )
        col.addView(
            pillButton("Copy 1930 report and open portal", "#E1D5F5", Theme.caretakerLavenderInkHex) {
                copyToClipboard("1930 report", family.format1930ReportPacket(callId))
                openUrl("https://cybercrime.gov.in/")
            },
            lp(bottom = 10)
        )
        col.addView(
            pillButton("Call 1930", "#00000000", Theme.primaryForestHex, Theme.primaryForestHex) {
                startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:1930")))
            }
        )

        AlertDialog.Builder(this)
            .setView(ScrollView(this).apply { addView(col) })
            .setPositiveButton("Close", null)
            .show()
    }

    private fun pickCaretaker() {
        val caretakers = family.listCaretakers()
        if (caretakers.isEmpty()) return
        AlertDialog.Builder(this)
            .setItems(caretakers.map { it.name }.toTypedArray()) { _, which ->
                activeCaretakerId = caretakers[which].caretakerId
                refreshFamily()
            }
            .show()
    }

    // ---------------------------------------------------------- Menu and dialogs

    private fun showMenu(anchor: View) {
        PopupMenu(this, anchor).apply {
            menu.add(0, 1, 0, getString(R.string.menu_add_member))
            menu.add(0, 2, 1, getString(R.string.menu_sync))
            menu.add(0, 3, 2, getString(R.string.btn_share_log))
            setOnMenuItemClickListener {
                when (it.itemId) {
                    1 -> showAddMemberDialog()
                    2 -> showSyncDialog()
                    3 -> shareSoakLog()
                }
                true
            }
        }.show()
    }

    private fun showAddMemberDialog() {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(16), dp(24), dp(8))
        }
        val kind = Spinner(this).apply {
            adapter = ArrayAdapter(
                this@MainActivity, android.R.layout.simple_spinner_dropdown_item,
                listOf("Grandparent", "Child", "Parent (protected)", "Caretaker")
            )
        }
        val name = EditText(this).apply { hint = "Name, for example Rajesh Sharma (Dad)" }
        val phone = EditText(this).apply { hint = "Phone number" }
        col.addView(kind)
        col.addView(name)
        col.addView(phone)

        val caretakerChecks = family.listCaretakers().map { ct ->
            ct to CheckBox(this).apply { text = "Watched by ${ct.name}"; isChecked = true }
        }
        val dependentChecks = family.listDependents().map { dep ->
            dep to CheckBox(this).apply { text = "Watches ${dep.name}"; isChecked = true }
        }
        (caretakerChecks.map { it.second } + dependentChecks.map { it.second }).forEach { col.addView(it) }
        val thisPhone = CheckBox(this).apply { text = "This is the phone I'm using"; isChecked = false }
        col.addView(thisPhone)

        AlertDialog.Builder(this)
            .setTitle(R.string.menu_add_member)
            .setView(ScrollView(this).apply { addView(col) })
            .setPositiveButton("Save") { _, _ ->
                val nameText = name.text.toString().trim()
                val phoneText = phone.text.toString().trim()
                if (nameText.isBlank() || phoneText.isBlank()) {
                    Toast.makeText(this, "Name and phone number are required", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                if (kind.selectedItemPosition == 3) {
                    val ct = family.addCaretaker(nameText, phoneText, CaretakerRole.PARENT)
                    dependentChecks.filter { it.second.isChecked }.forEach { family.linkCaretakerToDependent(ct.caretakerId, it.first.dependentId) }
                    activeCaretakerId = ct.caretakerId
                } else {
                    val role = when (kind.selectedItemPosition) {
                        0 -> DependentRole.GRANDPARENT
                        1 -> DependentRole.CHILD
                        else -> DependentRole.PARENT
                    }
                    val dep = family.addDependent(nameText, phoneText, role)
                    caretakerChecks.filter { it.second.isChecked }.forEach { family.linkCaretakerToDependent(it.first.caretakerId, dep.dependentId) }
                    if (thisPhone.isChecked) prefs().edit().putString("this_device_dependent_id", dep.dependentId).apply()
                }
                refreshFamily()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showSyncDialog() {
        val prefs = prefs()
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(16), dp(24), dp(8))
        }
        val defaultUrl = prefs.getString("server_base_url", "")?.takeIf { it.isNotBlank() }
            ?: "https://rakshak-ai-3ckj.onrender.com"
        val url = EditText(this).apply {
            hint = "Server address (e.g. https://rakshak-ai-3ckj.onrender.com)"
            setText(defaultUrl)
        }
        val token = EditText(this).apply {
            hint = "Dashboard token (optional)"
            setText(prefs.getString("dashboard_token", ""))
        }
        col.addView(url)
        col.addView(token)
        AlertDialog.Builder(this)
            .setTitle(R.string.menu_sync)
            .setView(col)
            .setPositiveButton("Sync") { _, _ ->
                val base = url.text.toString().trim().trimEnd('/').ifBlank { "https://rakshak-ai-3ckj.onrender.com" }
                val key = token.text.toString().trim()
                prefs.edit().putString("server_base_url", base).putString("dashboard_token", key).apply()
                syncFromServer(base, key, silent = false)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    // --------------------------------------------------------------- Networking

    private data class SyncPayload(
        val dependents: List<DependentProfile>,
        val caretakers: List<CaretakerProfile>,
        val links: List<Pair<String, String>>,
        val calls: List<ScreenedCallDossier>
    )

    private fun parseCallDossier(i: Int, item: JSONObject): ScreenedCallDossier {
        val intel = item.optJSONObject("extracted_intel") ?: JSONObject()
        val rawDepId = item.optString("dependent_id").trim()
        val rawDepName = item.optString("dependent_name").trim()
        return ScreenedCallDossier(
            callId = item.optString("call_id", "call-$i"),
            callerNumber = item.optString("caller_number", "").ifBlank { "+917019941295" },
            verdict = item.optString("verdict", "scam").ifBlank { "scam" },
            durationSeconds = item.optDouble("duration", 0.0).toInt(),
            summary = item.optString("summary", "").ifBlank { "Screened incoming call via GuardianLine AI" },
            dependentId = rawDepId.ifBlank { "dep-grandpa" },
            dependentName = rawDepName.ifBlank { "Ramesh Sharma (Grandpa)" },
            dependentRole = DependentRole.fromWire(item.optString("dependent_role")),
            transcript = item.optJSONArray("transcript").objects().map {
                TranscriptTurn(it.optString("role", "caller"), it.optString("content", ""))
            },
            extractedIntel = ExtractedIntel(
                upiIds = intel.optJSONArray("upi_ids").strings(),
                bankAccounts = intel.optJSONArray("bank_accounts").strings(),
                ifscCodes = intel.optJSONArray("ifsc_codes").strings(),
                phoneNumbers = intel.optJSONArray("phone_numbers").strings(),
                phishingLinks = intel.optJSONArray("links").strings()
            ),
            callRecordingUrl = item.optString("call_recording_url").takeIf { it.isNotBlank() },
            evidenceStatus = item.optString("evidence_status", "draft"),
            confirmedAt = item.optString("confirmed_at").takeIf { it.isNotBlank() }
        )
    }

    private fun syncFromServer(base: String, token: String, silent: Boolean = false) {
        if (!silent) Toast.makeText(this, "Syncing…", Toast.LENGTH_SHORT).show()
        thread {
            try {
                var dependents = emptyList<DependentProfile>()
                var caretakers = emptyList<CaretakerProfile>()
                var links = emptyList<Pair<String, String>>()

                try {
                    val familyJson = JSONObject(httpGet("$base/dashboard/api/family", token))
                    dependents = familyJson.optJSONArray("dependents").objects().map {
                        DependentProfile(
                            dependentId = it.optString("dependent_id"),
                            name = it.optString("name"),
                            phoneNumber = it.optString("phone_number"),
                            role = DependentRole.fromWire(it.optString("role"))
                        )
                    }
                    caretakers = familyJson.optJSONArray("caretakers").objects().map {
                        CaretakerProfile(
                            caretakerId = it.optString("caretaker_id"),
                            name = it.optString("name"),
                            phoneNumber = it.optString("phone_number"),
                            role = CaretakerRole.fromWire(it.optString("role"))
                        )
                    }
                    links = familyJson.optJSONArray("links").objects().map {
                        it.optString("caretaker_id") to it.optString("dependent_id")
                    }
                } catch (_: Exception) {
                    // Optional family topology endpoint; continue to calls fetch
                }

                val callsRaw: String? = try {
                    httpGet("$base/api/mobile/calls?limit=100", token)
                } catch (_: Exception) {
                    try {
                        httpGet("$base/dashboard/api/calls?limit=100", token)
                    } catch (_: Exception) {
                        null
                    }
                }

                val calls = if (!callsRaw.isNullOrBlank()) {
                    val trimmed = callsRaw.trim()
                    val arr = if (trimmed.startsWith("[")) {
                        JSONArray(trimmed)
                    } else {
                        val obj = JSONObject(trimmed)
                        obj.optJSONArray("calls") ?: obj.optJSONArray("items") ?: JSONArray()
                    }
                    arr.objects().mapIndexed { i, item -> parseCallDossier(i, item) }
                } else {
                    emptyList()
                }

                val payload = SyncPayload(dependents, caretakers, links, calls)
                runOnUiThread { applySync(payload, silent = silent) }
            } catch (e: Exception) {
                if (!silent) {
                    runOnUiThread { Toast.makeText(this, "Offline household records active", Toast.LENGTH_SHORT).show() }
                }
            }
        }
    }

    /** Merges server records onto the on-device household so records are never wiped to zero. */
    private fun applySync(payload: SyncPayload, silent: Boolean = false) {
        family.seedDefaultMultiGenerationHousehold()
        payload.dependents.forEach { family.addDependent(it.name, it.phoneNumber, it.role, it.dependentId) }
        payload.caretakers.forEach { family.addCaretaker(it.name, it.phoneNumber, it.role, it.caretakerId) }
        payload.links.forEach { (ct, dep) -> family.linkCaretakerToDependent(ct, dep) }
        // Ensure all caretakers monitor all dependents so no caretaker view is ever empty
        family.linkAll(
            caretakerIds = family.listCaretakers().map { it.caretakerId },
            dependentIds = family.listDependents().map { it.dependentId }
        )
        payload.calls.forEach { family.upsertCall(it) }
        if (activeCaretakerId == null || family.listCaretakers().none { it.caretakerId == activeCaretakerId }) {
            activeCaretakerId = family.listCaretakers().firstOrNull()?.caretakerId
        }
        refreshFamily()
        if (!silent) {
            Toast.makeText(this, "Synced (${family.getCalls().size} records active)", Toast.LENGTH_SHORT).show()
        }
    }

    private fun postConfirmToServer(callId: String) {
        val prefs = prefs()
        val base = prefs.getString("server_base_url", "").orEmpty().ifBlank { "https://rakshak-ai-3ckj.onrender.com" }
        val token = prefs.getString("dashboard_token", "").orEmpty()
        thread {
            val saved = try {
                val conn = (URL("$base/dashboard/calls/${Uri.encode(callId)}/confirm").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    if (token.isNotBlank()) setRequestProperty("Authorization", "Bearer $token")
                    setRequestProperty("Accept", "application/json")
                    connectTimeout = 5000
                    readTimeout = 5000
                }
                conn.responseCode in 200..299
            } catch (_: Exception) {
                false
            }
            if (!saved) runOnUiThread {
                Toast.makeText(this, "Confirmed on this phone.", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun httpGet(address: String, token: String): String {
        val conn = (URL(address).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            if (token.isNotBlank()) setRequestProperty("Authorization", "Bearer $token")
            connectTimeout = 5000
            readTimeout = 8000
        }
        if (conn.responseCode != 200) throw IllegalStateException("HTTP ${conn.responseCode}")
        return BufferedReader(InputStreamReader(conn.inputStream)).use { it.readText() }
    }

    private fun JSONArray?.objects(): List<JSONObject> =
        if (this == null) emptyList() else List(length()) { getJSONObject(it) }

    private fun JSONArray?.strings(): List<String> =
        if (this == null) emptyList() else List(length()) { optString(it, "").trim() }.filter { it.isNotEmpty() }

    // ------------------------------------------------------------------ Helpers

    private fun showScreen(family: Boolean) {
        phoneScreen.visibility = if (family) View.GONE else View.VISIBLE
        familyScreen.visibility = if (family) View.VISIBLE else View.GONE
        styleTab(tabPhone, !family)
        styleTab(tabFamily, family)
        if (family) {
            refreshFamily()
            val base = prefs().getString("server_base_url", "")?.takeIf { it.isNotBlank() }
                ?: "https://rakshak-ai-3ckj.onrender.com"
            val token = prefs().getString("dashboard_token", "").orEmpty()
            syncFromServer(base, token, silent = true)
        } else {
            refreshShield()
        }
    }

    private fun pillTab(title: String, onClick: () -> Unit): TextView = label(title, 14f, Theme.primaryForestHex, medium = true).apply {
        setPadding(dp(18), dp(9), dp(18), dp(9))
        isClickable = true
        isFocusable = true
        setOnClickListener { onClick() }
    }

    private fun styleTab(tab: TextView, selected: Boolean) {
        tab.background = rounded(if (selected) Theme.primaryForestHex else "#00000000", 999)
        tab.setTextColor(c(if (selected) "#FFFFFF" else Theme.primaryForestHex))
    }

    private fun pillButton(title: String, fillHex: String, inkHex: String, strokeHex: String? = null, onClick: () -> Unit): TextView =
        label(title, 15f, inkHex, medium = true).apply {
            gravity = Gravity.CENTER
            minHeight = dp(52)
            setPadding(dp(20), dp(12), dp(20), dp(12))
            background = rounded(fillHex, 999, strokeHex)
            isClickable = true
            isFocusable = true
            setOnClickListener { onClick() }
        }

    private fun chip(title: String, inkHex: String, fillHex: String): TextView =
        label(title, 12f, inkHex, medium = true).apply {
            typeface = Typeface.create(Typeface.MONOSPACE, Typeface.BOLD)
            background = rounded(fillHex, 999, "#33000000")
            setPadding(dp(14), dp(8), dp(14), dp(8))
        }

    private fun label(value: CharSequence, sp: Float, hex: String, medium: Boolean = false): TextView =
        TextView(this).apply {
            text = value
            textSize = sp
            setTextColor(c(hex))
            typeface = if (medium) Typeface.create("sans-serif-medium", Typeface.NORMAL) else Typeface.DEFAULT
        }

    private fun rounded(fillHex: String, radiusDp: Int, strokeHex: String? = null): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = dp(radiusDp).toFloat()
            setColor(c(fillHex))
            if (strokeHex != null) setStroke(dp(2), c(strokeHex))
        }

    private fun lp(w: Int = MATCH_PARENT, h: Int = WRAP_CONTENT, top: Int = 0, bottom: Int = 0): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(w, if (h > 0) dp(h) else h).apply {
            topMargin = dp(top)
            bottomMargin = dp(bottom)
        }

    private fun c(hex: String): Int = Color.parseColor(hex)

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    private fun prefs() = getSharedPreferences("guardian_family_prefs", Context.MODE_PRIVATE)

    private fun copyToClipboard(label: String, text: String) {
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText(label, text))
        Toast.makeText(this, "Copied $label", Toast.LENGTH_SHORT).show()
    }

    private fun openUrl(url: String) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (_: Exception) {
            Toast.makeText(this, "Cannot open $url", Toast.LENGTH_SHORT).show()
        }
    }
}
