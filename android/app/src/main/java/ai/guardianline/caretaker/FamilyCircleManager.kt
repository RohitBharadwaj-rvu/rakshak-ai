package ai.guardianline.caretaker

import ai.guardianline.screening.PhoneNumberNormalizer
import java.time.Instant

enum class DependentRole(val wireValue: String, val displayLabel: String) {
    GRANDPARENT("grandparent", "Grandparent"),
    PARENT("parent", "Parent"),
    CHILD("child", "Kid / Child"),
    OTHER("other", "Family Member");

    companion object {
        fun fromWire(value: String?): DependentRole {
            val normalized = value?.trim()?.lowercase() ?: return GRANDPARENT
            return entries.firstOrNull { it.wireValue == normalized } ?: GRANDPARENT
        }
    }
}

enum class CaretakerRole(val wireValue: String, val displayLabel: String) {
    PARENT("parent", "Parent / Guardian"),
    CARETAKER("caretaker", "Caretaker"),
    OTHER("other", "Family Guardian");

    companion object {
        fun fromWire(value: String?): CaretakerRole {
            val normalized = value?.trim()?.lowercase() ?: return PARENT
            return entries.firstOrNull { it.wireValue == normalized } ?: PARENT
        }
    }
}

data class DependentProfile(
    val dependentId: String,
    val name: String,
    val phoneNumber: String,
    val role: DependentRole = DependentRole.GRANDPARENT,
    val deviceId: String? = null
)

data class CaretakerProfile(
    val caretakerId: String,
    val name: String,
    val phoneNumber: String,
    val role: CaretakerRole = CaretakerRole.PARENT,
    val telegramChatId: String? = null
)

data class TranscriptTurn(
    val role: String,
    val content: String
)

data class ExtractedIntel(
    val upiIds: List<String> = emptyList(),
    val bankAccounts: List<String> = emptyList(),
    val ifscCodes: List<String> = emptyList(),
    val phoneNumbers: List<String> = emptyList(),
    val phishingLinks: List<String> = emptyList()
) {
    fun isEmpty(): Boolean =
        upiIds.isEmpty() && bankAccounts.isEmpty() && ifscCodes.isEmpty() && phoneNumbers.isEmpty() && phishingLinks.isEmpty()
}

data class ScreenedCallDossier(
    val callId: String,
    val callerNumber: String,
    val verdict: String,
    val durationSeconds: Int,
    val summary: String,
    val dependentId: String? = null,
    val dependentName: String? = null,
    val dependentRole: DependentRole = DependentRole.GRANDPARENT,
    val transcript: List<TranscriptTurn> = emptyList(),
    val extractedIntel: ExtractedIntel = ExtractedIntel(),
    val callRecordingUrl: String? = null,
    val evidenceStatus: String = "draft",
    val confirmedAt: String? = null
)

data class ScamIntelCluster(
    val kind: String,
    val identifier: String,
    val callIds: List<String>,
    val targetedDependents: List<String>
) {
    val callCount: Int get() = callIds.size
}

data class MaterialCallCardPalette(
    val cardSurfaceHex: String,
    val inkHex: String
)

/**
 * Material You 3 Expressive palette shared by the Android screens and mirrored by the web dashboard
 * (app/core/gui_theme.py). Quiet by design: sage surfaces, one salmon alert card, a dark forest primary.
 */
object MaterialYouFamilyTheme {
    const val surfaceBackgroundHex = "#E4EFE3"
    const val cardSurfaceHex = "#F6FAF5"
    const val primaryForestHex = "#2B4A32"
    const val mutedTextHex = "#5B6B5E"
    const val inkHex = "#1C1B1F"
    const val caretakerLavenderHex = "#E1D5F5"
    const val caretakerLavenderInkHex = "#2E1F66"
    const val scamSalmonHex = "#FBCBBD"
    const val alertRedHex = "#B3261E"
    const val squircleCornerRadiusDp = 28f

    fun initialsFor(name: String): String {
        val clean = name.substringBefore("(").trim()
        val parts = clean.split(Regex("\\s+")).filter { it.isNotBlank() }
        if (parts.isEmpty()) return "G"
        if (parts.size == 1) return parts[0].take(2).uppercase()
        return "${parts[0].first()}${parts[1].first()}".uppercase()
    }

    /** `Rajesh Sharma (Dad)` -> `Dad`; `Priya` -> `Priya`. */
    fun shortLabel(name: String): String {
        val open = name.indexOf('(')
        val close = name.lastIndexOf(')')
        if (open >= 0 && close > open) {
            val inner = name.substring(open + 1, close).trim()
            if (inner.isNotEmpty()) return inner
        }
        return name.trim().split(Regex("\\s+")).firstOrNull().orEmpty().ifEmpty { "Family" }
    }

    fun avatarColorFor(role: DependentRole): String = when (role) {
        DependentRole.GRANDPARENT -> "#C8E6C9"
        DependentRole.CHILD -> "#FFD9C2"
        DependentRole.PARENT, DependentRole.OTHER -> "#CFE3F5"
    }

    fun callCardPalette(verdict: String): MaterialCallCardPalette {
        return when (verdict.trim().lowercase()) {
            "scam" -> MaterialCallCardPalette(cardSurfaceHex = "#FBCBBD", inkHex = "#3E1A12")
            "genuine", "safe_delivery", "legitimate_verified" ->
                MaterialCallCardPalette(cardSurfaceHex = "#D8EBD6", inkHex = "#14301A")
            else -> MaterialCallCardPalette(cardSurfaceHex = "#E9ECE8", inkHex = "#26302A")
        }
    }

    /** Stable pseudo-waveform (0.15..1.0) so a call always draws the same bars. */
    fun waveformBars(seed: String, count: Int): List<Float> {
        var h = seed.fold(1125899906842597L) { acc, c -> 31 * acc + c.code }
        return List(count) {
            h = h * 6364136223846793005L + 1442695040888963407L
            val unit = ((h ushr 33) % 1000).toFloat() / 1000f
            0.15f + unit * 0.85f
        }
    }
}

/**
 * Pure Kotlin domain manager for the Multi-Caretaker <-> Multi-Dependent Family Protection Circle
 * and Caretaker Evidence Dossier. Supports a household with Grandparents, Parents, and Kids where
 * both Parents monitor all Grandparents' and Kids' devices.
 */
class FamilyCircleManager {

    private val caretakers = linkedMapOf<String, CaretakerProfile>()
    private val dependents = linkedMapOf<String, DependentProfile>()
    // caretakerId -> mutableSetOf(dependentId)
    private val caretakerToDependents = linkedMapOf<String, MutableSet<String>>()
    private val calls = linkedMapOf<String, ScreenedCallDossier>()

    fun addCaretaker(
        name: String,
        phone: String,
        role: CaretakerRole = CaretakerRole.PARENT,
        caretakerId: String? = null,
        telegramChatId: String? = null
    ): CaretakerProfile {
        val normPhone = PhoneNumberNormalizer.normalize(phone)?.takeIf { it.isNotBlank() } ?: phone.trim()
        val existing = caretakers.values.firstOrNull { it.phoneNumber == normPhone }
        val id = caretakerId ?: existing?.caretakerId ?: "ct-${normPhone.takeLast(10)}"
        val profile = CaretakerProfile(
            caretakerId = id,
            name = name.trim(),
            phoneNumber = normPhone,
            role = role,
            telegramChatId = telegramChatId
        )
        caretakers[id] = profile
        caretakerToDependents.putIfAbsent(id, linkedSetOf())
        return profile
    }

    fun addDependent(
        name: String,
        phone: String,
        role: DependentRole = DependentRole.GRANDPARENT,
        dependentId: String? = null,
        deviceId: String? = null
    ): DependentProfile {
        val normPhone = PhoneNumberNormalizer.normalize(phone)?.takeIf { it.isNotBlank() } ?: phone.trim()
        val existing = dependents.values.firstOrNull { it.phoneNumber == normPhone }
        val id = dependentId ?: existing?.dependentId ?: "dep-${normPhone.takeLast(10)}"
        val profile = DependentProfile(
            dependentId = id,
            name = name.trim(),
            phoneNumber = normPhone,
            role = role,
            deviceId = deviceId
        )
        dependents[id] = profile
        return profile
    }

    fun linkCaretakerToDependent(caretakerId: String, dependentId: String) {
        if (!caretakers.containsKey(caretakerId) || !dependents.containsKey(dependentId)) return
        caretakerToDependents.getOrPut(caretakerId) { linkedSetOf() }.add(dependentId)
    }

    fun unlinkCaretakerFromDependent(caretakerId: String, dependentId: String) {
        caretakerToDependents[caretakerId]?.remove(dependentId)
    }

    fun linkAll(caretakerIds: List<String>, dependentIds: List<String>) {
        for (cid in caretakerIds) {
            for (did in dependentIds) {
                linkCaretakerToDependent(cid, did)
            }
        }
    }

    fun listCaretakers(): List<CaretakerProfile> = caretakers.values.toList()

    fun clear() {
        caretakers.clear()
        dependents.clear()
        caretakerToDependents.clear()
        calls.clear()
    }

    fun listDependents(): List<DependentProfile> = dependents.values.toList()

    fun getDependentsForCaretaker(caretakerId: String): List<DependentProfile> {
        val depIds = caretakerToDependents[caretakerId].orEmpty()
        return depIds.mapNotNull { dependents[it] }
    }

    fun getCaretakersForDependent(dependentId: String): List<CaretakerProfile> {
        return caretakers.values.filter { ct ->
            caretakerToDependents[ct.caretakerId]?.contains(dependentId) == true
        }
    }

    fun upsertCall(dossier: ScreenedCallDossier) {
        calls[dossier.callId] = dossier
    }

    fun getCall(callId: String): ScreenedCallDossier? = calls[callId]

    fun getCalls(
        caretakerId: String? = null,
        dependentId: String? = null,
        roleFilter: DependentRole? = null
    ): List<ScreenedCallDossier> {
        val allowedDependents: Set<String>? = if (!caretakerId.isNullOrBlank()) {
            caretakerToDependents[caretakerId]?.toSet() ?: emptySet()
        } else {
            null
        }

        return calls.values.filter { call ->
            val matchesCaretaker = if (allowedDependents != null) {
                call.dependentId == null || allowedDependents.contains(call.dependentId)
            } else {
                true
            }
            val matchesDependent = if (!dependentId.isNullOrBlank()) {
                call.dependentId == dependentId
            } else {
                true
            }
            val matchesRole = if (roleFilter != null) {
                call.dependentRole == roleFilter
            } else {
                true
            }
            matchesCaretaker && matchesDependent && matchesRole
        }
    }

    fun confirmEvidence(callId: String, timestampIso: String = Instant.now().toString()): ScreenedCallDossier? {
        val existing = calls[callId] ?: return null
        val updated = existing.copy(
            evidenceStatus = "confirmed_by_family",
            confirmedAt = timestampIso
        )
        calls[callId] = updated
        return updated
    }

    fun formatChakshuPacket(callId: String): String {
        val call = calls[callId] ?: return ""
        val upiStr = call.extractedIntel.upiIds.joinToString(", ").ifBlank { "None" }
        val accStr = call.extractedIntel.bankAccounts.joinToString(", ").ifBlank { "None" }
        val depLabel = call.dependentName ?: "Family Member"
        return buildString {
            appendLine("=== CHAKSHU (DoT Sanchar Saathi) REPORT PACKET ===")
            appendLine("Portal: https://sancharsaathi.gov.in/sfc/")
            appendLine("Protected Dependent: $depLabel (${call.dependentRole.displayLabel})")
            appendLine("Suspect Caller Number: ${call.callerNumber}")
            appendLine("Medium: Voice Call (Screened by GuardianLine AI)")
            appendLine("Verdict: ${call.verdict.uppercase()} (${call.durationSeconds}s)")
            appendLine("Extracted UPI IDs: $upiStr")
            appendLine("Extracted Bank Accounts: $accStr")
            appendLine("Incident Summary: ${call.summary}")
            appendLine("Evidence Status: ${call.evidenceStatus}")
        }.trim()
    }

    fun format1930ReportPacket(callId: String): String {
        val call = calls[callId] ?: return ""
        val depLabel = call.dependentName ?: "Family Member"
        val upiStr = call.extractedIntel.upiIds.joinToString(", ").ifBlank { "None" }
        val accStr = call.extractedIntel.bankAccounts.joinToString(", ").ifBlank { "None" }
        val ifscStr = call.extractedIntel.ifscCodes.joinToString(", ").ifBlank { "None" }
        val phStr = call.extractedIntel.phoneNumbers.joinToString(", ").ifBlank { call.callerNumber }
        return buildString {
            appendLine("=== 1930 NATIONAL CYBERCRIME REPORTING PORTAL DOSSIER ===")
            appendLine("Helpline: Dial 1930 | Portal: https://cybercrime.gov.in")
            appendLine("Call ID: ${call.callId}")
            appendLine("Protected Dependent: $depLabel (${call.dependentRole.displayLabel})")
            appendLine("Suspect Caller CLI: ${call.callerNumber}")
            appendLine("Suspect Phone Numbers: $phStr")
            appendLine("Suspect UPI Handles: $upiStr")
            appendLine("Suspect Bank Accounts: $accStr")
            appendLine("Suspect IFSC Codes: $ifscStr")
            appendLine("Summary: ${call.summary}")
            appendLine("Evidence Verification: ${call.evidenceStatus}${call.confirmedAt?.let { " ($it)" } ?: ""}")
        }.trim()
    }

    fun buildScamIntelligenceClusters(): List<ScamIntelCluster> {
        val upiToCalls = linkedMapOf<String, MutableList<ScreenedCallDossier>>()
        val accToCalls = linkedMapOf<String, MutableList<ScreenedCallDossier>>()

        for (call in calls.values) {
            for (upi in call.extractedIntel.upiIds) {
                val norm = upi.trim().lowercase()
                if (norm.isNotEmpty()) {
                    upiToCalls.getOrPut(norm) { mutableListOf() }.add(call)
                }
            }
            for (acc in call.extractedIntel.bankAccounts) {
                val norm = acc.trim()
                if (norm.isNotEmpty()) {
                    accToCalls.getOrPut(norm) { mutableListOf() }.add(call)
                }
            }
        }

        val clusters = mutableListOf<ScamIntelCluster>()
        for ((upi, linkedCalls) in upiToCalls) {
            val distinctCallIds = linkedCalls.map { it.callId }.distinct()
            if (distinctCallIds.size >= 2) {
                val deps = linkedCalls.mapNotNull { it.dependentName }.distinct()
                clusters.add(
                    ScamIntelCluster(
                        kind = "upi",
                        identifier = upi,
                        callIds = distinctCallIds,
                        targetedDependents = deps
                    )
                )
            }
        }
        for ((acc, linkedCalls) in accToCalls) {
            val distinctCallIds = linkedCalls.map { it.callId }.distinct()
            if (distinctCallIds.size >= 2) {
                val deps = linkedCalls.mapNotNull { it.dependentName }.distinct()
                clusters.add(
                    ScamIntelCluster(
                        kind = "bank_account",
                        identifier = acc,
                        callIds = distinctCallIds,
                        targetedDependents = deps
                    )
                )
            }
        }
        return clusters
    }

    fun seedDefaultMultiGenerationHousehold() {
        if (caretakers.isNotEmpty() || dependents.isNotEmpty()) return

        val dad = addCaretaker(
            name = "Rajesh Sharma (Dad)",
            phone = "+919820010001",
            role = CaretakerRole.PARENT,
            caretakerId = "ct-dad"
        )
        val mom = addCaretaker(
            name = "Priya Sharma (Mom)",
            phone = "+919820010002",
            role = CaretakerRole.PARENT,
            caretakerId = "ct-mom"
        )

        val grandpa = addDependent(
            name = "Ramesh Sharma (Grandpa)",
            phone = "+919810020001",
            role = DependentRole.GRANDPARENT,
            dependentId = "dep-grandpa"
        )
        val grandma = addDependent(
            name = "Kamla Sharma (Grandma)",
            phone = "+919810020002",
            role = DependentRole.GRANDPARENT,
            dependentId = "dep-grandma"
        )
        val kidAarav = addDependent(
            name = "Aarav Sharma",
            phone = "+919810020003",
            role = DependentRole.CHILD,
            dependentId = "dep-kid-aarav"
        )
        val kidAnanya = addDependent(
            name = "Ananya Sharma",
            phone = "+919810020004",
            role = DependentRole.CHILD,
            dependentId = "dep-kid-ananya"
        )

        // Both parents monitor both grandparents and both kids
        linkAll(
            caretakerIds = listOf(dad.caretakerId, mom.caretakerId),
            dependentIds = listOf(grandpa.dependentId, grandma.dependentId, kidAarav.dependentId, kidAnanya.dependentId)
        )

        upsertCall(
            ScreenedCallDossier(
                callId = "59a2191a-1379-43f2-a341-66ecc5ab4dcb",
                callerNumber = "+919876543210",
                verdict = "scam",
                durationSeconds = 95,
                summary = "CBI Digital Arrest & SBI KYC block threat targeting Grandfather Ramesh. Extracted UPI & bank account.",
                dependentId = grandpa.dependentId,
                dependentName = grandpa.name,
                dependentRole = grandpa.role,
                transcript = listOf(
                    TranscriptTurn("caller", "Namaskar, main CBI cyber cell aur SBI headquarters se bol raha hoon. Aapka KYC block ho gaya hai, turant ramesh.scam@okaxis par 10,000 rupaye bhejo."),
                    TranscriptTurn("agent", "Arre beta, main Ramesh bol raha hoon, meri umar 72 saal hai. Mera chashma nahi mil raha, aap apna UPI ID aur bank account number dhire-dhire batao."),
                    TranscriptTurn("caller", "Jaldi note karo: UPI ID ramesh.scam@okaxis hai aur account number 918273645501, IFSC SBIN0001234. Abhi transfer karo warna digital arrest warrant niklega!"),
                    TranscriptTurn("agent", "Accha beta, main passbook dhoondh ke apne bete Rajesh se pooch ke abhi karta hoon.")
                ),
                extractedIntel = ExtractedIntel(
                    upiIds = listOf("ramesh.scam@okaxis"),
                    bankAccounts = listOf("918273645501"),
                    ifscCodes = listOf("SBIN0001234"),
                    phoneNumbers = listOf("9876543210")
                ),
                callRecordingUrl = "https://bolna.ai/recordings/59a2191a-1379-43f2-a341-66ecc5ab4dcb.mp3",
                evidenceStatus = "draft"
            )
        )

        upsertCall(
            ScreenedCallDossier(
                callId = "77c3102b-8421-49a1-b112-88fdd6bc9901",
                callerNumber = "+919123456780",
                verdict = "scam",
                durationSeconds = 72,
                summary = "Electricity disconnection scam targeting Grandmother Kamla using the same syndicate UPI handle.",
                dependentId = grandma.dependentId,
                dependentName = grandma.name,
                dependentRole = grandma.role,
                transcript = listOf(
                    TranscriptTurn("caller", "Bijli vibhag se bol raha hoon, aaj raat 9 baje bijli kat jayegi. Turant ramesh.scam@okaxis par 4,500 bhejo."),
                    TranscriptTurn("agent", "Beta bil toh pichle hafte hi bhara tha. Ruko main bahu Priya ko bulati hoon.")
                ),
                extractedIntel = ExtractedIntel(
                    upiIds = listOf("ramesh.scam@okaxis"),
                    bankAccounts = listOf("918273645501"),
                    phoneNumbers = listOf("9123456780")
                ),
                callRecordingUrl = "https://bolna.ai/recordings/77c3102b-8421-49a1-b112-88fdd6bc9901.mp3",
                evidenceStatus = "draft"
            )
        )

        upsertCall(
            ScreenedCallDossier(
                callId = "88d4203c-9532-40b2-c223-99aee7cd0012",
                callerNumber = "+918899776655",
                verdict = "scam",
                durationSeconds = 58,
                summary = "Gaming tournament prize / UPI PIN phishing attempt targeting Kid Aarav.",
                dependentId = kidAarav.dependentId,
                dependentName = kidAarav.name,
                dependentRole = kidAarav.role,
                transcript = listOf(
                    TranscriptTurn("caller", "Congratulations! You won a gaming pass worth Rs 5,000. Scan or send Rs 1 verification to ramesh.scam@okaxis."),
                    TranscriptTurn("agent", "Main abhi mummy-papa se poochta hoon, mere paas UPI PIN nahi hai.")
                ),
                extractedIntel = ExtractedIntel(
                    upiIds = listOf("ramesh.scam@okaxis"),
                    phoneNumbers = listOf("8899776655"),
                    phishingLinks = listOf("http://free-pass-claim.example.com")
                ),
                callRecordingUrl = "https://bolna.ai/recordings/88d4203c-9532-40b2-c223-99aee7cd0012.mp3",
                evidenceStatus = "draft"
            )
        )
    }
}

