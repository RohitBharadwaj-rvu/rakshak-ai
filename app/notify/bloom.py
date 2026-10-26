"""
app/notify/bloom.py - Community Blocklist Bloom Filter & Android Push Payload (Rakshak v2).

Provides a deterministic, space-efficient Bloom filter over confirmed/suspected scam
identifiers (UPI IDs, phone numbers, bank accounts, IFSC codes) for low-bandwidth
syncing to the GuardianLine Android client.
"""

import base64
import hashlib
import logging
import math
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("guardianline.notify.bloom")


def _normalize_key(identifier: str, kind: Optional[str] = None) -> str:
    val = str(identifier or "").strip().lower()
    if kind:
        return f"{kind.strip().lower()}:{val}"
    return val


class CommunityBloomFilter:
    """
    Space-efficient Bloom filter using SHA-256 double hashing (Kirsch-Mitzenmacher).
    Bit-array backed for compact hex/base64 serialization to Android devices.
    """

    def __init__(self, size_bits: int = 8192, num_hashes: int = 5):
        if size_bits <= 0 or size_bits % 8 != 0:
            raise ValueError("size_bits must be a positive multiple of 8")
        if num_hashes <= 0:
            raise ValueError("num_hashes must be positive")
        self.size_bits = size_bits
        self.num_hashes = num_hashes
        self._bytes = bytearray(size_bits // 8)
        self._count = 0
        self._lock = threading.RLock()

    def _positions(self, item: str) -> List[int]:
        digest = hashlib.sha256(item.encode("utf-8")).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:16], "big") or 1
        return [(h1 + i * h2) % self.size_bits for i in range(self.num_hashes)]

    def add(self, identifier: str, kind: Optional[str] = None) -> None:
        """Add an identifier (and its raw form if `kind` is given) into the Bloom filter."""
        if not identifier or not str(identifier).strip():
            return
        raw_norm = _normalize_key(identifier)
        keys = [raw_norm]
        if kind:
            keys.append(_normalize_key(identifier, kind))
        with self._lock:
            for key in keys:
                for bit_idx in self._positions(key):
                    self._bytes[bit_idx // 8] |= 1 << (bit_idx % 8)
            self._count += 1

    def add_many(self, identifiers: Iterable[str], kind: Optional[str] = None) -> int:
        added = 0
        for ident in identifiers:
            if ident and str(ident).strip():
                self.add(ident, kind=kind)
                added += 1
        return added

    def contains(self, identifier: str, kind: Optional[str] = None) -> bool:
        """Check if an identifier is present in the community blocklist Bloom filter."""
        if not identifier or not str(identifier).strip():
            return False
        key = _normalize_key(identifier, kind)
        with self._lock:
            return all(
                bool(self._bytes[bit_idx // 8] & (1 << (bit_idx % 8)))
                for bit_idx in self._positions(key)
            )

    def __contains__(self, identifier: str) -> bool:
        return self.contains(identifier)

    @property
    def count(self) -> int:
        return self._count

    def estimated_false_positive_rate(self) -> float:
        if self._count == 0:
            return 0.0
        exp_term = math.exp(-self.num_hashes * self._count / float(self.size_bits))
        return round((1.0 - exp_term) ** self.num_hashes, 6)

    def to_bytes(self) -> bytes:
        with self._lock:
            return bytes(self._bytes)

    def to_hex(self) -> str:
        return self.to_bytes().hex()

    def to_base64(self) -> str:
        return base64.b64encode(self.to_bytes()).decode("ascii")

    @classmethod
    def from_hex(cls, hex_str: str, num_hashes: int = 5, count: int = 0) -> "CommunityBloomFilter":
        raw = bytes.fromhex(hex_str)
        bf = cls(size_bits=len(raw) * 8, num_hashes=num_hashes)
        bf._bytes[:] = raw
        bf._count = count
        return bf

    def export_android_push_payload(self, cluster_id: Optional[str] = None) -> Dict[str, Any]:
        """Build a compact JSON payload suitable for FCM / Android call-screening blocklist push."""
        return {
            "type": "community_blocklist_bloom_v2",
            "size_bits": self.size_bits,
            "num_hashes": self.num_hashes,
            "entries_count": self._count,
            "false_positive_rate": self.estimated_false_positive_rate(),
            "cluster_id": cluster_id,
            "filter_base64": self.to_base64(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


_GLOBAL_BLOOM = CommunityBloomFilter(size_bits=8192, num_hashes=5)


def get_community_bloom_filter() -> CommunityBloomFilter:
    """Return the singleton community blocklist Bloom filter."""
    return _GLOBAL_BLOOM


def reset_community_bloom_filter() -> CommunityBloomFilter:
    """Reset the singleton community blocklist Bloom filter (used in tests)."""
    global _GLOBAL_BLOOM
    _GLOBAL_BLOOM = CommunityBloomFilter(size_bits=8192, num_hashes=5)
    return _GLOBAL_BLOOM
