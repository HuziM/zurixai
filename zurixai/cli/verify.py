"""zurix verify — validate a signed audit entry or a whole exported audit log."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from zurixai.provenance import EntryResult, key_id_for, verify_chain, verify_entry

PUBKEY_URL = "https://zurixai.com/.well-known/zurixai-pubkey"


# ANSI color codes
class _C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    DIM = "\033[2m"

    @classmethod
    def disable(cls):
        for attr in ("RESET", "BOLD", "RED", "GREEN", "YELLOW", "DIM"):
            setattr(cls, attr, "")


def _usage() -> None:
    print(f"{_C.BOLD}Usage:{_C.RESET} zurix verify <audit.json | log.jsonl> [--key <pubkey_hex>]")
    print()
    print("  One entry: checks its Ed25519 signature and its own hash, and prints")
    print("  the source field (server-run or client-submitted).")
    print("  Several entries (a JSON array or one entry per line): checks every entry,")
    print("  then that chain indexes are contiguous and each prev_hash links to the")
    print("  entry before it.")
    print()
    print("  If --key is omitted, the public key is fetched from")
    print(f"  {PUBKEY_URL}")


def _parse_args(args: list[str]) -> tuple[str | None, str | None]:
    path = key = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--key" and i + 1 < len(args):
            key = args[i + 1]
            i += 2
            continue
        if not a.startswith("--") and path is None:
            path = a
        i += 1
    return path, key


def _load_entries(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not all(isinstance(e, dict) for e in data):
        raise ValueError("expected a JSON object, a JSON array of objects, or one object per line")
    return data


def _mark(ok: bool) -> str:
    return f"{_C.GREEN}✓{_C.RESET}" if ok else f"{_C.RED}✗{_C.RESET}"


def _key_id_line(result: EntryResult, entry: dict[str, Any], pubkey_hex: str) -> str:
    if result.key_id_matches:
        return f"  {_C.DIM}Key ID:       {entry['key_id']} (matches the key){_C.RESET}"
    return (f"  {_C.YELLOW}!{_C.RESET} Key ID {entry['key_id']} is not the id of this key "
            f"({key_id_for(pubkey_hex)}). It is a label; the signature is what counts.")


def _print_single(entry: dict[str, Any], result: EntryResult, pubkey_hex: str) -> None:
    print(f"  {_mark(result.hash_ok)} Entry hash: "
          + (f"{_C.GREEN}valid{_C.RESET}" if result.hash_ok else f"{_C.RED}INVALID{_C.RESET}"))
    print(f"  {_mark(result.signature_ok)} Signature: "
          + (f"{_C.GREEN}valid{_C.RESET}" if result.signature_ok else f"{_C.RED}INVALID{_C.RESET}"))

    print()
    print(_key_id_line(result, entry, pubkey_hex))
    print(f"  {_C.DIM}Chain index:  {entry['chain_index']}{_C.RESET}")
    print(f"  {_C.DIM}Timestamp:    {entry['timestamp']}{_C.RESET}")
    print(f"  {_C.DIM}Tool version: {entry['tool_version']}{_C.RESET}")
    print(f"  {_C.DIM}Repo:         {entry['repo']}{_C.RESET}")
    print(f"  {_C.DIM}PR:           #{entry['pr']}{_C.RESET}")
    print(f"  {_C.DIM}Commit:       {str(entry['head_commit_sha'])[:12]}{_C.RESET}")
    print(f"  {_C.DIM}Source:       {entry['source']}{_C.RESET}")
    print(f"  {_C.DIM}Conclusion:   {entry['conclusion']}{_C.RESET}")

    checks = entry.get("checks") or []
    if checks:
        print()
        print(f"  {_C.BOLD}Checks ({len(checks)}):{_C.RESET}")
        for c in checks:
            status = c.get("status", "unknown")
            glyph = {"pass": f"{_C.GREEN}✓{_C.RESET}", "fail": f"{_C.RED}✗{_C.RESET}",
                     "warn": f"{_C.YELLOW}!{_C.RESET}"}.get(status, f"{_C.DIM}○{_C.RESET}")
            print(f"    {glyph} {c.get('check_id', '?')}: {status}")


def cmd_verify(args: list[str]) -> None:
    """Verify signed audit entries against a public key."""
    use_color = "--no-color" not in args and sys.stdout.isatty()
    if not use_color:
        _C.disable()

    path_arg, pubkey_hex = _parse_args(args)
    if path_arg is None:
        _usage()
        sys.exit(1)

    audit_path = Path(path_arg)
    if not audit_path.exists():
        print(f"{_C.RED}Error:{_C.RESET} File not found: {audit_path}")
        sys.exit(1)

    try:
        entries = _load_entries(audit_path.read_text())
    except (json.JSONDecodeError, ValueError) as e:
        print(f"{_C.RED}Error:{_C.RESET} Invalid audit file: {e}")
        sys.exit(1)
    if not entries:
        print(f"{_C.RED}Error:{_C.RESET} No entries in {audit_path}")
        sys.exit(1)

    if pubkey_hex is None:
        pubkey_hex = _fetch_public_key()
        if pubkey_hex is None:
            print(f"{_C.RED}Error:{_C.RESET} Could not fetch public key.")
            print("  Provide it with: --key <pubkey_hex>")
            sys.exit(1)

    print()
    print(f"{_C.BOLD}{'═' * 56}{_C.RESET}")
    print(f"{_C.BOLD}  ZurixAI Audit Verification{_C.RESET}")
    print(f"{_C.BOLD}{'═' * 56}{_C.RESET}")
    print()

    if len(entries) == 1:
        result = verify_entry(entries[0], pubkey_hex)
        if result.missing:
            print(f"{_C.RED}Error:{_C.RESET} Missing fields: {', '.join(result.missing)}")
            sys.exit(1)
        _print_single(entries[0], result, pubkey_hex)
        passed = result.ok
    else:
        chain = verify_chain(entries, pubkey_hex)
        for r in chain.entries:
            if r.missing:
                print(f"  {_mark(False)} Entry {r.chain_index}: missing {', '.join(r.missing)}")
                continue
            detail = "valid" if r.ok else (
                "hash INVALID" if not r.hash_ok else "signature INVALID")
            print(f"  {_mark(r.ok)} Entry {r.chain_index}: {detail}")
        print()
        if chain.errors:
            for err in chain.errors:
                print(f"  {_mark(False)} {err}")
        else:
            span = f"index {chain.first_index}..{chain.last_index}"
            print(f"  {_mark(True)} Chain: {_C.GREEN}linked{_C.RESET} ({len(chain.entries)} entries, {span})")
            if chain.partial:
                print(f"  {_C.YELLOW}!{_C.RESET} Partial range: entries before {chain.first_index} "
                      "are not in this file, so its start can't be checked.")
        mismatched = sum(1 for r in chain.entries if not r.missing and not r.key_id_matches)
        if mismatched:
            print(f"  {_C.YELLOW}!{_C.RESET} {mismatched} entries carry a key id other than "
                  f"{key_id_for(pubkey_hex)} (a label; the signatures are what count).")
        passed = chain.ok

    print()
    if passed:
        print(f"  {_C.GREEN}{_C.BOLD}Verification passed{_C.RESET}")
    else:
        print(f"  {_C.RED}{_C.BOLD}Verification FAILED{_C.RESET}")
    print(f"{'═' * 56}\n")

    if not passed:
        sys.exit(1)


def _fetch_public_key() -> str | None:
    """Fetch the public key from https://zurixai.com/.well-known/zurixai-pubkey."""
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.Request(PUBKEY_URL, headers={"User-Agent": "zurix-verify"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body: bytes = resp.read()
            return body.decode("utf-8").strip()
    except (urllib.error.URLError, OSError, ValueError):
        return None
