"""Signed audit entries: canonical form, single-entry and whole-chain verification."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from zurixai.provenance import (
    SIGNED_FIELDS,
    canonical_json,
    key_id_for,
    sha256_hex,
    verify_chain,
    verify_entry,
)

FIXTURE = Path(__file__).parent / "fixtures" / "prod_entry.json"


def pubkey_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def sign(key: Ed25519PrivateKey, payload: dict[str, Any]) -> dict[str, Any]:
    canonical = canonical_json(payload)
    return {**payload, "entry_hash": sha256_hex(canonical),
            "signature": base64.b64encode(key.sign(canonical.encode())).decode()}


def make_chain(key: Ed25519PrivateKey, n: int, repo: str = "o/r") -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    prev = ""
    for i in range(n):
        payload = {
            "key_id": key_id_for(pubkey_hex(key)), "chain_index": i, "prev_hash": prev,
            "timestamp": f"2026-10-01T00:00:0{i}+00:00", "tool_version": "0.4.0", "repo": repo,
            "pr": i + 1, "head_commit_sha": f"{i:040d}", "rules_hash": sha256_hex(""),
            "source": "server-run",
            "checks": [{"check_id": "imports", "check_version": "1.0.0", "status": "pass",
                        "findings_hash": sha256_hex(canonical_json([]))}],
            "conclusion": "pass",
        }
        entry = sign(key, payload)
        entries.append(entry)
        prev = entry["entry_hash"]
    return entries


def test_production_entry_still_verifies() -> None:
    data = json.loads(FIXTURE.read_text())
    result = verify_entry(data["entry"], data["pubkey_hex"])
    assert result.ok and result.key_id_matches


def test_raw_database_row_with_extra_columns_verifies() -> None:
    data = json.loads(FIXTURE.read_text())
    row = {**data["entry"], "id": "1230e182-d3f7-4f3b-82bc-4c19cf12bdd0",
           "created_at": "2026-09-30 14:51:05.649212+00"}
    assert verify_entry(row, data["pubkey_hex"]).ok


def test_canonical_json_is_sorted_compact_and_keeps_utf8() -> None:
    assert canonical_json({"b": 1, "a": "é"}) == '{"a":"é","b":1}'


def test_tampered_field_fails_hash_and_signature() -> None:
    key = Ed25519PrivateKey.generate()
    entry = make_chain(key, 1)[0]
    entry["conclusion"] = "fail"
    result = verify_entry(entry, pubkey_hex(key))
    assert not result.hash_ok and not result.signature_ok and not result.ok


def test_other_key_fails_signature_and_key_id() -> None:
    entry = make_chain(Ed25519PrivateKey.generate(), 1)[0]
    result = verify_entry(entry, pubkey_hex(Ed25519PrivateKey.generate()))
    assert result.hash_ok and not result.signature_ok and not result.key_id_matches


def test_missing_field_is_reported() -> None:
    key = Ed25519PrivateKey.generate()
    entry = make_chain(key, 1)[0]
    del entry["rules_hash"]
    assert verify_entry(entry, pubkey_hex(key)).missing == ["rules_hash"]


def test_signed_fields_are_the_payload() -> None:
    entry = make_chain(Ed25519PrivateKey.generate(), 1)[0]
    assert set(entry) - set(SIGNED_FIELDS) == {"entry_hash", "signature"}


def test_intact_chain_verifies_in_any_order() -> None:
    key = Ed25519PrivateKey.generate()
    entries = make_chain(key, 4)
    result = verify_chain(list(reversed(entries)), pubkey_hex(key))
    assert result.ok and (result.first_index, result.last_index) == (0, 3) and not result.partial


def test_dropped_entry_breaks_the_chain() -> None:
    key = Ed25519PrivateKey.generate()
    entries = make_chain(key, 4)
    del entries[2]
    result = verify_chain(entries, pubkey_hex(key))
    assert not result.ok and "jumps from 1 to 3" in result.errors[0]


def test_resigned_entry_with_wrong_prev_hash_breaks_the_link() -> None:
    key = Ed25519PrivateKey.generate()
    entries = make_chain(key, 3)
    forged = {k: entries[1][k] for k in SIGNED_FIELDS}
    forged["prev_hash"] = "0" * 64
    entries[1] = sign(key, forged)
    result = verify_chain(entries, pubkey_hex(key))
    assert all(e.ok for e in result.entries)
    assert any("does not link to entry 0" in e for e in result.errors)


def test_partial_range_is_allowed_but_flagged() -> None:
    key = Ed25519PrivateKey.generate()
    result = verify_chain(make_chain(key, 5)[2:], pubkey_hex(key))
    assert result.ok and result.partial and result.first_index == 2


def test_entries_from_two_repos_are_rejected() -> None:
    key = Ed25519PrivateKey.generate()
    a, b = make_chain(key, 1, "o/a")[0], make_chain(key, 2, "o/b")[1]
    assert not verify_chain([a, b], pubkey_hex(key)).ok
