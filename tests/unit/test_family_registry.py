"""
Unit tests for Multi-Caretaker / Multi-Dependent FamilyRegistry (Seam 1).
Tests a multi-generation family topology:
  - Grandparents (Dada, Dadi) and Kids (Aarav, Ananya) as Dependents
  - Both Parents (Rajesh, Priya) as Caretakers monitoring all 4 dependents
"""

import pytest
from app.core.family import FamilyRegistry, DependentRole, CaretakerRole


@pytest.fixture
def registry(tmp_path):
    db_file = tmp_path / "test_family.db"
    return FamilyRegistry(db_path=str(db_file))


class TestMultiCaretakerMultiDependentGraph:
    def test_both_parents_monitor_grandparents_and_kids(self, registry):
        # 1. Register two parents as caretakers
        dad = registry.register_caretaker(
            name="Rajesh Sharma (Dad)",
            phone_number="9811111101",
            role=CaretakerRole.PARENT,
            channel="whatsapp",
        )
        mom = registry.register_caretaker(
            name="Priya Sharma (Mom)",
            phone_number="+91 98111-11102",
            role=CaretakerRole.PARENT,
            channel="whatsapp",
        )

        # 2. Register grandparents and kids as dependents
        grandpa = registry.register_dependent(
            name="Ramesh Sharma (Dada)",
            phone_number="9800000001",
            role=DependentRole.GRANDPARENT,
        )
        grandma = registry.register_dependent(
            name="Sunita Sharma (Dadi)",
            phone_number="9800000002",
            role=DependentRole.GRANDPARENT,
        )
        kid1 = registry.register_dependent(
            name="Aarav Sharma",
            phone_number="9800000003",
            role=DependentRole.CHILD,
        )
        kid2 = registry.register_dependent(
            name="Ananya Sharma",
            phone_number="9800000004",
            role=DependentRole.CHILD,
        )

        # 3. Link both parents to all 4 dependents (many-to-many)
        for dep in (grandpa, grandma, kid1, kid2):
            registry.link_caretaker_to_dependent(
                caretaker_id=dad["caretaker_id"],
                dependent_id=dep["dependent_id"],
                relationship_label="Father / Son",
            )
            registry.link_caretaker_to_dependent(
                caretaker_id=mom["caretaker_id"],
                dependent_id=dep["dependent_id"],
                relationship_label="Mother / Daughter-in-law",
            )

        # Verify phone normalization
        assert dad["phone_number"] == "+919811111101"
        assert mom["phone_number"] == "+919811111102"
        assert grandpa["phone_number"] == "+919800000001"
        assert kid1["phone_number"] == "+919800000003"

        # 4. Both Mom and Dad see all 4 dependents
        dad_dependents = registry.get_dependents_for_caretaker(dad["caretaker_id"])
        mom_dependents = registry.get_dependents_for_caretaker(mom["caretaker_id"])
        assert {d["dependent_id"] for d in dad_dependents} == {
            grandpa["dependent_id"],
            grandma["dependent_id"],
            kid1["dependent_id"],
            kid2["dependent_id"],
        }
        assert {d["dependent_id"] for d in mom_dependents} == {
            grandpa["dependent_id"],
            grandma["dependent_id"],
            kid1["dependent_id"],
            kid2["dependent_id"],
        }

        # 5. Querying by caretaker phone number also works
        mom_deps_by_phone = registry.get_dependents_for_caretaker("09811111102")
        assert len(mom_deps_by_phone) == 4

        # 6. Each dependent (e.g. Grandpa and Kid1) is monitored by BOTH parents
        grandpa_caretakers = registry.get_caretakers_for_dependent(grandpa["dependent_id"])
        kid1_caretakers = registry.get_caretakers_for_dependent(kid1["phone_number"])
        assert {c["phone_number"] for c in grandpa_caretakers} == {
            "+919811111101",
            "+919811111102",
        }
        assert {c["phone_number"] for c in kid1_caretakers} == {
            "+919811111101",
            "+919811111102",
        }

    def test_alert_recipient_resolution_targets_assigned_caretakers(self, registry):
        dad = registry.register_caretaker("Rajesh", "+919811111101")
        mom = registry.register_caretaker("Priya", "+919811111102")
        uncle = registry.register_caretaker("Vikram", "+919811111103")

        grandpa = registry.register_dependent("Ramesh", "+919800000001", role=DependentRole.GRANDPARENT)
        kid = registry.register_dependent("Aarav", "+919800000003", role=DependentRole.CHILD)

        # Grandpa is monitored by Dad, Mom, and Uncle
        registry.link_caretaker_to_dependent(dad["caretaker_id"], grandpa["dependent_id"])
        registry.link_caretaker_to_dependent(mom["caretaker_id"], grandpa["dependent_id"])
        registry.link_caretaker_to_dependent(uncle["caretaker_id"], grandpa["dependent_id"])

        # Kid is monitored only by Dad and Mom (not Uncle)
        registry.link_caretaker_to_dependent(dad["caretaker_id"], kid["dependent_id"])
        registry.link_caretaker_to_dependent(mom["caretaker_id"], kid["dependent_id"])

        kid_call = {"call_id": "call_kid_1", "dependent_id": kid["dependent_id"]}
        kid_recipients = registry.resolve_alert_recipients_for_call(kid_call)
        assert kid_recipients == ["+919811111101", "+919811111102"]

        grandpa_call = {"call_id": "call_gp_1", "dependent_phone": "09800000001"}
        gp_recipients = registry.resolve_alert_recipients_for_call(grandpa_call)
        assert gp_recipients == ["+919811111101", "+919811111102", "+919811111103"]

    def test_unlink_caretaker_from_dependent(self, registry):
        dad = registry.register_caretaker("Rajesh", "+919811111101")
        mom = registry.register_caretaker("Priya", "+919811111102")
        kid = registry.register_dependent("Aarav", "+919800000003", role=DependentRole.CHILD)

        registry.link_caretaker_to_dependent(dad["caretaker_id"], kid["dependent_id"])
        registry.link_caretaker_to_dependent(mom["caretaker_id"], kid["dependent_id"])
        assert len(registry.get_caretakers_for_dependent(kid["dependent_id"])) == 2

        removed = registry.unlink_caretaker_from_dependent(dad["caretaker_id"], kid["dependent_id"])
        assert removed is True
        remaining = registry.get_caretakers_for_dependent(kid["dependent_id"])
        assert len(remaining) == 1
        assert remaining[0]["caretaker_id"] == mom["caretaker_id"]


class TestMultiCaretakerAlertDispatchAndStore:
    def test_dispatcher_alerts_both_parents_for_grandparent_and_kid_calls(self, registry, monkeypatch):
        from app.core.family import set_family_registry
        from app.notify.alerts import (
            AlertChannel,
            AlertConfig,
            AlertStatus,
            FamilyAlertDispatcher,
            PersistentAlertStore,
            format_alert_message,
        )

        set_family_registry(registry)
        try:
            dad = registry.register_caretaker("Rajesh (Dad)", "+919811111101")
            mom = registry.register_caretaker("Priya (Mom)", "+919811111102")
            grandpa = registry.register_dependent("Ramesh (Dada)", "+919800000001", role=DependentRole.GRANDPARENT)
            kid = registry.register_dependent("Aarav (Son)", "+919800000003", role=DependentRole.CHILD)

            registry.link_caretaker_to_dependent(dad["caretaker_id"], grandpa["dependent_id"])
            registry.link_caretaker_to_dependent(mom["caretaker_id"], grandpa["dependent_id"])
            registry.link_caretaker_to_dependent(dad["caretaker_id"], kid["dependent_id"])
            registry.link_caretaker_to_dependent(mom["caretaker_id"], kid["dependent_id"])

            call_record = {
                "call_id": "call_grandpa_scam_01",
                "caller_number": "+919999988888",
                "verdict": "scam",
                "dependent_id": grandpa["dependent_id"],
                "dependent_name": grandpa["name"],
                "summary": "Fake CBI digital arrest threat targeting Dada.",
                "extracted_intel": {"upi_ids": ["scam@okaxis"]},
            }

            msg = format_alert_message(call_record, AlertChannel.WHATSAPP)
            assert "Ramesh (Dada)" in msg

            # Even if static config only has Dad or is empty, dispatcher resolves both linked parents
            cfg = AlertConfig(
                from_phone="+14155238886",
                to_phone=dad["phone_number"],
                channel=AlertChannel.WHATSAPP,
            )
            dispatcher = FamilyAlertDispatcher(
                config=cfg,
                twilio_client=None,
                store=PersistentAlertStore(":memory:"),
            )
            res = dispatcher.dispatch(call_record)
            assert res.status in (AlertStatus.MOCK, AlertStatus.SENT)
            assert len(res.sub_results) == 2
            dispatched_to = {sr["recipient"].replace("whatsapp:", "") for sr in res.sub_results}
            assert dispatched_to == {"+919811111101", "+919811111102"}
        finally:
            set_family_registry(None)

