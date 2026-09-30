"""Canonical form and verification for signed ZurixAI audit entries.

The server signs the canonical JSON of SIGNED_FIELDS with Ed25519; entry_hash is the SHA-256 of
the same bytes. Each entry's prev_hash is the previous entry's entry_hash for the same repo.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

SIGNED_FIELDS = (
    "key_id", "chain_index", "prev_hash", "timestamp", "tool_version", "repo", "pr",
    "head_commit_sha", "rules_hash", "source", "checks", "conclusion",
)
ENTRY_FIELDS = (*SIGNED_FIELDS, "entry_hash", "signature")


def canonical_json(obj: object) -> str:
    """Sorted keys, no whitespace, UTF-8 kept as is. Matches RFC 8785 for ASCII keys, strings and ints."""
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, ensure_ascii=False, default=str)


def sha256_hex(data: str | bytes) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def key_id_for(pubkey_hex: str) -> str:
    return sha256_hex(pubkey_hex.lower())[:16]


def signed_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: entry[k] for k in SIGNED_FIELDS}


def export_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields a verifier needs (drops DB columns such as id and created_at)."""
    return {k: entry[k] for k in ENTRY_FIELDS}


@dataclass
class EntryResult:
    chain_index: int | None
    missing: list[str] = field(default_factory=list)
    hash_ok: bool = False
    signature_ok: bool = False
    key_id_matches: bool = False

    @property
    def ok(self) -> bool:
        return not self.missing and self.hash_ok and self.signature_ok


@dataclass
class ChainResult:
    entries: list[EntryResult]
    errors: list[str] = field(default_factory=list)
    first_index: int | None = None
    last_index: int | None = None

    @property
    def partial(self) -> bool:
        return bool(self.first_index)

    @property
    def ok(self) -> bool:
        return not self.errors and all(e.ok for e in self.entries)


def _signature_valid(canonical: str, signature_b64: str, pubkey_hex: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
        public_key.verify(base64.b64decode(signature_b64, validate=True), canonical.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError, binascii.Error, TypeError):
        return False


def verify_entry(entry: dict[str, Any], pubkey_hex: str) -> EntryResult:
    index = entry.get("chain_index")
    result = EntryResult(chain_index=index if isinstance(index, int) else None)
    result.missing = [f for f in ENTRY_FIELDS if f not in entry]
    if result.missing:
        return result
    canonical = canonical_json(signed_payload(entry))
    result.hash_ok = sha256_hex(canonical) == entry["entry_hash"]
    result.signature_ok = _signature_valid(canonical, entry["signature"], pubkey_hex)
    result.key_id_matches = entry["key_id"] == key_id_for(pubkey_hex)
    return result


def verify_chain(entries: list[dict[str, Any]], pubkey_hex: str) -> ChainResult:
    """Verify every entry, then that indexes are contiguous and each prev_hash links to the entry before."""
    ordered = sorted(entries, key=lambda e: e.get("chain_index", -1))
    result = ChainResult(entries=[verify_entry(e, pubkey_hex) for e in ordered])
    if not ordered:
        result.errors.append("No entries.")
        return result

    repos = {e.get("repo") for e in ordered}
    if len(repos) > 1:
        result.errors.append(f"Entries from more than one repo: {', '.join(sorted(map(str, repos)))}.")

    result.first_index = ordered[0].get("chain_index")
    result.last_index = ordered[-1].get("chain_index")
    if result.first_index == 0 and ordered[0].get("prev_hash") != "":
        result.errors.append("Entry 0 has a prev_hash; the first entry of a chain must have none.")

    for prev, cur in pairwise(ordered):
        p, c = prev.get("chain_index"), cur.get("chain_index")
        if not isinstance(p, int) or not isinstance(c, int) or c != p + 1:
            result.errors.append(f"Chain index jumps from {p} to {c}: an entry is missing or duplicated.")
        elif cur.get("prev_hash") != prev.get("entry_hash"):
            result.errors.append(f"Entry {c} does not link to entry {p} (prev_hash mismatch).")
    return result
