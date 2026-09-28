"""zurix verify — Validate a signed audit report."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path


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


def cmd_verify(args: list[str]) -> None:
    """Verify a signed audit report against a public key."""
    use_color = "--no-color" not in args and sys.stdout.isatty()
    if not use_color:
        _C.disable()

    # Parse args
    positional = [a for a in args if not a.startswith("--")]

    if len(positional) < 1:
        print(f"{_C.BOLD}Usage:{_C.RESET} zurix verify <audit.json> [--key <pubkey_hex>]")
        print()
        print("  Validates the Ed25519 signature, checks the hash chain, and")
        print("  prints the source field (server-run or client-submitted).")
        print()
        print("  If --key is omitted, the public key is fetched from")
        print("  https://zurixai.com/.well-known/zurixai-pubkey")
        sys.exit(1)

    audit_path = Path(positional[0])
    if not audit_path.exists():
        print(f"{_C.RED}Error:{_C.RESET} File not found: {audit_path}")
        sys.exit(1)

    try:
        data = json.loads(audit_path.read_text())
    except json.JSONDecodeError as e:
        print(f"{_C.RED}Error:{_C.RESET} Invalid JSON: {e}")
        sys.exit(1)

    # Get public key
    pubkey_hex = None
    for i, a in enumerate(args):
        if a == "--key" and i + 1 < len(args):
            pubkey_hex = args[i + 1]
            break

    if pubkey_hex is None:
        # Fetch from well-known URL
        pubkey_hex = _fetch_public_key()
        if pubkey_hex is None:
            print(f"{_C.RED}Error:{_C.RESET} Could not fetch public key.")
            print("  Provide it with: --key <pubkey_hex>")
            sys.exit(1)

    # Validate required fields
    required = ["key_id", "chain_index", "prev_hash", "timestamp", "tool_version",
                 "repo", "pr", "head_commit_sha", "rules_hash", "source",
                 "checks", "conclusion", "entry_hash", "signature"]
    missing = [f for f in required if f not in data]
    if missing:
        print(f"{_C.RED}Error:{_C.RESET} Missing fields: {', '.join(missing)}")
        sys.exit(1)

    # Reconstruct canonical form for verification
    payload = {k: data[k] for k in data if k not in ("entry_hash", "signature")}
    # Convert checks to match schema format
    if "checks" in payload:
        payload["checks"] = [
            {k: v for k, v in c.items()} for c in payload["checks"]
        ]
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)

    # Verify hash
    expected_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    hash_ok = expected_hash == data["entry_hash"]

    # Verify signature
    sig_ok = _verify_signature(canonical, data["signature"], pubkey_hex)

    # Print results
    print()
    print(f"{_C.BOLD}{'═' * 56}{_C.RESET}")
    print(f"{_C.BOLD}  ZurixAI Audit Verification{_C.RESET}")
    print(f"{_C.BOLD}{'═' * 56}{_C.RESET}")
    print()

    # Hash check
    if hash_ok:
        print(f"  {_C.GREEN}✓{_C.RESET} Hash chain: {_C.GREEN}valid{_C.RESET}")
    else:
        print(f"  {_C.RED}✗{_C.RESET} Hash chain: {_C.RED}INVALID{_C.RESET}")

    # Signature check
    if sig_ok:
        print(f"  {_C.GREEN}✓{_C.RESET} Signature: {_C.GREEN}valid{_C.RESET}")
    else:
        print(f"  {_C.RED}✗{_C.RESET} Signature: {_C.RED}INVALID{_C.RESET}")

    # Entry details
    print()
    print(f"  {_C.DIM}Key ID:       {data['key_id']}{_C.RESET}")
    print(f"  {_C.DIM}Chain index:  {data['chain_index']}{_C.RESET}")
    print(f"  {_C.DIM}Timestamp:    {data['timestamp']}{_C.RESET}")
    print(f"  {_C.DIM}Tool version: {data['tool_version']}{_C.RESET}")
    print(f"  {_C.DIM}Repo:         {data['repo']}{_C.RESET}")
    print(f"  {_C.DIM}PR:           #{data['pr']}{_C.RESET}")
    print(f"  {_C.DIM}Commit:       {data['head_commit_sha'][:12]}{_C.RESET}")
    print(f"  {_C.DIM}Source:       {data['source']}{_C.RESET}")
    print(f"  {_C.DIM}Conclusion:   {data['conclusion']}{_C.RESET}")

    # Checks
    checks = data.get("checks", [])
    if checks:
        print()
        print(f"  {_C.BOLD}Checks ({len(checks)}):{_C.RESET}")
        for c in checks:
            status = c.get("status", "unknown")
            check_id = c.get("check_id", "?")
            if status == "pass":
                glyph = f"{_C.GREEN}✓{_C.RESET}"
            elif status == "fail":
                glyph = f"{_C.RED}✗{_C.RESET}"
            elif status == "warn":
                glyph = f"{_C.YELLOW}!{_C.RESET}"
            else:
                glyph = f"{_C.DIM}○{_C.RESET}"
            print(f"    {glyph} {check_id}: {status}")

    print()
    if hash_ok and sig_ok:
        print(f"  {_C.GREEN}{_C.BOLD}Verification passed{_C.RESET}")
    else:
        print(f"  {_C.RED}{_C.BOLD}Verification FAILED{_C.RESET}")

    print(f"{'═' * 56}\n")

    if not hash_ok or not sig_ok:
        sys.exit(1)


def _fetch_public_key() -> str | None:
    """Fetch the public key from https://zurixai.com/.well-known/zurixai-pubkey."""
    import urllib.error
    import urllib.request

    try:
        url = "https://zurixai.com/.well-known/zurixai-pubkey"
        req = urllib.request.Request(url, headers={"User-Agent": "zurix-verify/0.4.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body: bytes = resp.read()
            return body.decode("utf-8").strip()
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _verify_signature(canonical: str, signature_b64: str, pubkey_hex: str) -> bool:
    """Verify an Ed25519 signature against the canonical form and public key."""
    import binascii

    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
        public_key.verify(base64.b64decode(signature_b64), canonical.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError, binascii.Error):
        return False
