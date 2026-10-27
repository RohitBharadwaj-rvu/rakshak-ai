import json
import os
import tempfile
from pathlib import Path

from app.notify.bloom import CommunityBloomFilter, get_community_bloom_filter, reset_community_bloom_filter
from app.voice.syndicate import cluster_syndicates, ingest_scam_identifier, verify_penny_drop
from scripts.seed_honeypot import seed_honeypot_to_telegram

ROOT_DIR = Path(__file__).resolve().parents[2]


def test_rakshak_graph_json_has_four_states_with_own_tools_config():
    graph_path = ROOT_DIR / "bolna" / "rakshak-graph.json"
    assert graph_path.exists()
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    tasks = data["agent_config"]["tasks"]
    assert len(tasks) == 4
    task_ids = [t["task_id"] for t in tasks]
    assert task_ids == [
        "state_1_screening",
        "state_2_verification",
        "state_3_honeypot",
        "state_4_extraction",
    ]
    for task in tasks:
        assert "tools_config" in task
        assert task["tools_config"]["transcriber"]["model"] == "saaras:v3"
        assert task["tools_config"]["synthesizer"]["provider_config"]["model"] == "bulbul:v3"

    # State 1: qwen/qwen3.8-27b or qwen-2.5-32b
    assert tasks[0]["tools_config"]["llm_agent"]["llm_config"]["model"] in ["qwen/qwen3.8-27b", "qwen-2.5-32b"]
    assert tasks[0]["tools_config"]["llm_config"]["temperature"] if "llm_config" in tasks[0]["tools_config"] else tasks[0]["tools_config"]["llm_agent"]["llm_config"]["temperature"] == 0.3
    # State 3: qwen/qwen3.8-27b, qwen-2.5-32b, or gpt-4.1
    assert tasks[2]["tools_config"]["llm_agent"]["llm_config"]["model"] in ["qwen/qwen3.8-27b", "qwen-2.5-32b", "gpt-4.1"]


def test_syndicate_clustering_and_bloom_filter():
    reset_community_bloom_filter()
    fd, db_file = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        # Call 1 and Call 2 share the same scammer UPI ID; Call 2 and Call 3 share the same IFSC
        res1 = ingest_scam_identifier("call_syn_1", "upi", "mule.boss@okaxis", db_path=db_file)
        res2 = ingest_scam_identifier("call_syn_2", "upi", "mule.boss@okaxis", db_path=db_file)
        ingest_scam_identifier("call_syn_2", "ifsc", "SBIN0000125", db_path=db_file)
        res3 = ingest_scam_identifier("call_syn_3", "ifsc", "SBIN0000125", db_path=db_file)
        # Call 4 is an unrelated syndicate
        res4 = ingest_scam_identifier("call_syn_4", "phone", "9876543210", db_path=db_file)

        clusters = cluster_syndicates(db_path=db_file)
        assert len(clusters) == 2

        big_cluster = next(c for c in clusters if c["call_count"] == 3)
        assert big_cluster["call_ids"] == ["call_syn_1", "call_syn_2", "call_syn_3"]
        assert "mule.boss@okaxis" in big_cluster["upi_ids"]
        assert "SBIN0000125" in big_cluster["ifsc_codes"]
        assert big_cluster["auto_1930_ready"] is True
        assert res3["cluster_id"] == big_cluster["cluster_id"]
        assert res4["cluster_id"] != big_cluster["cluster_id"]

        # Penny-drop verification populated
        pd = verify_penny_drop("upi", "mule.boss@okaxis")
        assert pd["verified"] is True
        assert pd["bank_name"] == "Axis Bank"

        # Community Bloom filter contains ingested identifiers
        bloom = get_community_bloom_filter()
        assert "mule.boss@okaxis" in bloom
        assert bloom.contains("SBIN0000125", kind="ifsc")
        assert "innocent.user@oksbi" not in bloom

        # Hex round-trip
        restored = CommunityBloomFilter.from_hex(bloom.to_hex(), num_hashes=bloom.num_hashes, count=bloom.count)
        assert "mule.boss@okaxis" in restored
    finally:
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except OSError:
                pass


def test_seed_honeypot_mock():
    receipt = seed_honeypot_to_telegram(inbound_did="+918045681190", mock=True)
    assert receipt["mock_mode"] is True
    assert receipt["groups_seeded"] == 4
    assert all(p["status"] == "MOCK_POSTED" and "+918045681190" in p["message_text"] for p in receipt["posts"])
