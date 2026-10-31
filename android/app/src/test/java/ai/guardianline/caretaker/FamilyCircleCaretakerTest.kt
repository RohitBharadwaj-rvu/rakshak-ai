package ai.guardianline.caretaker

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test

class FamilyCircleCaretakerTest {

    private lateinit var manager: FamilyCircleManager

    @BeforeEach
    fun setUp() {
        manager = FamilyCircleManager()
    }

    @Test
    fun `test many-to-many family graph links multiple parents to grandparents and kids`() {
        val dad = manager.addCaretaker(name = "Rajesh (Father)", phone = "+919820010001", role = CaretakerRole.PARENT)
        val mom = manager.addCaretaker(name = "Priya (Mother)", phone = "+919820010002", role = CaretakerRole.PARENT)

        val grandpa = manager.addDependent(name = "Ramesh (Grandfather)", phone = "+919810020001", role = DependentRole.GRANDPARENT)
        val grandma = manager.addDependent(name = "Kamla (Grandmother)", phone = "+919810020002", role = DependentRole.GRANDPARENT)
        val kid = manager.addDependent(name = "Aarav (Kid)", phone = "+919810020003", role = DependentRole.CHILD)

        manager.linkAll(
            caretakerIds = listOf(dad.caretakerId, mom.caretakerId),
            dependentIds = listOf(grandpa.dependentId, grandma.dependentId, kid.dependentId)
        )

        val dadDependents = manager.getDependentsForCaretaker(dad.caretakerId)
        val momDependents = manager.getDependentsForCaretaker(mom.caretakerId)
        assertEquals(3, dadDependents.size)
        assertEquals(3, momDependents.size)

        val grandpaCaretakers = manager.getCaretakersForDependent(grandpa.dependentId)
        val kidCaretakers = manager.getCaretakersForDependent(kid.dependentId)
        assertEquals(setOf(dad.caretakerId, mom.caretakerId), grandpaCaretakers.map { it.caretakerId }.toSet())
        assertEquals(setOf(dad.caretakerId, mom.caretakerId), kidCaretakers.map { it.caretakerId }.toSet())
    }

    @Test
    fun `test call filtering by caretaker and dependent isolates family views`() {
        val dad = manager.addCaretaker(name = "Rajesh (Father)", phone = "+919820010001", role = CaretakerRole.PARENT)
        val mom = manager.addCaretaker(name = "Priya (Mother)", phone = "+919820010002", role = CaretakerRole.PARENT)
        val aunt = manager.addCaretaker(name = "Sunita (Aunt)", phone = "+919820010099", role = CaretakerRole.CARETAKER)

        val grandpa = manager.addDependent(name = "Ramesh (Grandfather)", phone = "+919810020001", role = DependentRole.GRANDPARENT)
        val kid = manager.addDependent(name = "Aarav (Kid)", phone = "+919810020003", role = DependentRole.CHILD)

        // Both parents monitor both Grandpa and Kid; Aunt only monitors Grandpa
        manager.linkAll(listOf(dad.caretakerId, mom.caretakerId), listOf(grandpa.dependentId, kid.dependentId))
        manager.linkCaretakerToDependent(aunt.caretakerId, grandpa.dependentId)

        manager.upsertCall(
            ScreenedCallDossier(
                callId = "call-grandpa-1",
                callerNumber = "+919999888877",
                verdict = "scam",
                durationSeconds = 95,
                summary = "Digital arrest CBI impersonation targeting Grandfather.",
                dependentId = grandpa.dependentId,
                dependentName = grandpa.name,
                dependentRole = grandpa.role,
                transcript = listOf(
                    TranscriptTurn("caller", "Main CBI headquarters se bol raha hoon, 50,000 bhejo."),
                    TranscriptTurn("agent", "Beta zara ruko, chashma dhoondh raha hoon.")
                ),
                extractedIntel = ExtractedIntel(
                    upiIds = listOf("cbi.fake@ybl"),
                    bankAccounts = listOf("918273645501"),
                    ifscCodes = listOf("SBIN0001234"),
                    phoneNumbers = listOf("9999888877")
                ),
                callRecordingUrl = "https://bolna.example/recordings/call-grandpa-1.mp3"
            )
        )
        manager.upsertCall(
            ScreenedCallDossier(
                callId = "call-kid-1",
                callerNumber = "+918888777766",
                verdict = "scam",
                durationSeconds = 64,
                summary = "Free gaming skin UPI collect scam targeting Kid.",
                dependentId = kid.dependentId,
                dependentName = kid.name,
                dependentRole = kid.role,
                transcript = listOf(
                    TranscriptTurn("caller", "Approve the UPI request on cbi.fake@ybl to unlock reward."),
                    TranscriptTurn("agent", "Main abhi papa se pooch ke batata hoon.")
                ),
                extractedIntel = ExtractedIntel(
                    upiIds = listOf("cbi.fake@ybl"),
                    phoneNumbers = listOf("8888777766")
                )
            )
        )

        // Dad and Mom see both Grandpa and Kid calls
        assertEquals(2, manager.getCalls(caretakerId = dad.caretakerId).size)
        assertEquals(2, manager.getCalls(caretakerId = mom.caretakerId).size)

        // Aunt only sees Grandpa's call
        val auntCalls = manager.getCalls(caretakerId = aunt.caretakerId)
        assertEquals(1, auntCalls.size)
        assertEquals("call-grandpa-1", auntCalls.first().callId)

        // Filtering by specific dependent returns only that dependent's call
        val kidCalls = manager.getCalls(caretakerId = dad.caretakerId, dependentId = kid.dependentId)
        assertEquals(1, kidCalls.size)
        assertEquals("call-kid-1", kidCalls.first().callId)
    }

    @Test
    fun `test evidence confirmation transitions call from draft to confirmed_by_family and formats Chakshu and 1930 packets`() {
        val grandpa = manager.addDependent(name = "Ramesh (Grandfather)", phone = "+919810020001", role = DependentRole.GRANDPARENT)
        val call = ScreenedCallDossier(
            callId = "call-evidence-1",
            callerNumber = "+919999888877",
            verdict = "scam",
            durationSeconds = 110,
            summary = "KYC freeze threat demanding transfer to fraudster@okaxis.",
            dependentId = grandpa.dependentId,
            dependentName = grandpa.name,
            dependentRole = grandpa.role,
            transcript = listOf(
                TranscriptTurn("caller", "Turant fraudster@okaxis par 25000 bhejo warna account block."),
                TranscriptTurn("agent", "Beta passbook nahi mil rahi.")
            ),
            extractedIntel = ExtractedIntel(
                upiIds = listOf("fraudster@okaxis"),
                bankAccounts = listOf("112233445566"),
                ifscCodes = listOf("HDFC0000123"),
                phoneNumbers = listOf("9999888877")
            ),
            callRecordingUrl = "https://bolna.example/recordings/call-evidence-1.mp3"
        )
        manager.upsertCall(call)

        assertEquals("draft", manager.getCall("call-evidence-1")?.evidenceStatus)

        val confirmed = manager.confirmEvidence("call-evidence-1")
        assertNotNull(confirmed)
        assertEquals("confirmed_by_family", confirmed!!.evidenceStatus)
        assertNotNull(confirmed.confirmedAt)

        val chakshuPacket = manager.formatChakshuPacket("call-evidence-1")
        assertTrue(chakshuPacket.contains("sancharsaathi.gov.in"))
        assertTrue(chakshuPacket.contains("fraudster@okaxis"))
        assertTrue(chakshuPacket.contains("+919999888877"))

        val cyber1930Packet = manager.format1930ReportPacket("call-evidence-1")
        assertTrue(cyber1930Packet.contains("1930"))
        assertTrue(cyber1930Packet.contains("cybercrime.gov.in"))
        assertTrue(cyber1930Packet.contains("Ramesh (Grandfather)"))
        assertTrue(cyber1930Packet.contains("fraudster@okaxis"))
        assertTrue(cyber1930Packet.contains("112233445566"))
    }

    @Test
    fun `test scam intelligence correlates shared UPI and bank accounts across multiple family dependents`() {
        val grandpa = manager.addDependent(name = "Ramesh (Grandfather)", phone = "+919810020001", role = DependentRole.GRANDPARENT)
        val kid = manager.addDependent(name = "Aarav (Kid)", phone = "+919810020003", role = DependentRole.CHILD)

        manager.upsertCall(
            ScreenedCallDossier(
                callId = "call-1",
                callerNumber = "+919999888877",
                verdict = "scam",
                durationSeconds = 80,
                summary = "CBI scam on Grandpa",
                dependentId = grandpa.dependentId,
                dependentName = grandpa.name,
                dependentRole = grandpa.role,
                extractedIntel = ExtractedIntel(upiIds = listOf("syndicate.boss@ybl"))
            )
        )
        manager.upsertCall(
            ScreenedCallDossier(
                callId = "call-2",
                callerNumber = "+917777666655",
                verdict = "scam",
                durationSeconds = 45,
                summary = "Lottery scam on Kid",
                dependentId = kid.dependentId,
                dependentName = kid.name,
                dependentRole = kid.role,
                extractedIntel = ExtractedIntel(upiIds = listOf("syndicate.boss@ybl"))
            )
        )

        val clusters = manager.buildScamIntelligenceClusters()
        assertEquals(1, clusters.size)
        val cluster = clusters.first()
        assertEquals("upi", cluster.kind)
        assertEquals("syndicate.boss@ybl", cluster.identifier)
        assertEquals(2, cluster.callIds.size)
        assertEquals(setOf("Ramesh (Grandfather)", "Aarav (Kid)"), cluster.targetedDependents.toSet())
    }
}
