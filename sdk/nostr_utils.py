"""
Nostr utilities for NIP-01:
- compute_event_id: compute the event id per NIP-01 serialization
- verify_event: verify signature and id for an event
- optional npub <-> hex x-only conversions (requires bech32)

This module intentionally has minimal dependencies. coincurve is required for
BIP340 Schnorr verification. bech32 is optional for npub helpers.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping, Tuple

try:
    from coincurve.schnorr import schnorr_verify  # type: ignore
except Exception as e:  # pragma: no cover - surface friendly import error
    schnorr_verify = None  # type: ignore
    _COINCURVE_IMPORT_ERROR = e
else:
    _COINCURVE_IMPORT_ERROR = None

# Optional bech32 helpers
try:  # pragma: no cover - optional
    from bech32 import bech32_decode, bech32_encode, convertbits  # type: ignore
except Exception:  # pragma: no cover - optional
    bech32_decode = bech32_encode = convertbits = None  # type: ignore


def _serialize_event0(pubkey_hex: str, created_at: int, kind: int, tags: Any, content: str) -> bytes:
    """Serialize as JSON array [0, pubkey, created_at, kind, tags, content] per NIP-01."""
    return json.dumps([0, pubkey_hex, created_at, kind, tags, content], separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_event_id(pubkey_hex: str, created_at: int, kind: int, tags: Any, content: str) -> str:
    """Return the hex event id = sha256(serialize([0, pubkey, created_at, kind, tags, content]))."""
    ser = _serialize_event0(pubkey_hex, created_at, kind, tags, content)
    return hashlib.sha256(ser).hexdigest()


def verify_event(event: Mapping[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    Verify a NIP-01 event. Returns (ok, details).

    ok is True only if both id matches recomputed id AND the signature verifies
    against the event id using the x-only public key.

    Required event fields: id, pubkey, created_at, kind, tags, content, sig.
    """
    required = ["id", "pubkey", "created_at", "kind", "tags", "content", "sig"]
    missing = [k for k in required if k not in event]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")

    pubkey_hex = str(event["pubkey"]).lower()
    created_at = int(event["created_at"])  # type: ignore[arg-type]
    kind = int(event["kind"])  # type: ignore[arg-type]
    tags = event["tags"]
    content = str(event["content"])  # type: ignore[arg-type]

    expected_id = compute_event_id(pubkey_hex, created_at, kind, tags, content)
    id_matches = (expected_id == str(event["id"]).lower())

    if schnorr_verify is None:
        raise ImportError(f"coincurve is required for verification: {_COINCURVE_IMPORT_ERROR}")

    try:
        msg32 = bytes.fromhex(expected_id)
        sig_bytes = bytes.fromhex(str(event["sig"]))
        pubkey_xonly = bytes.fromhex(pubkey_hex)
        sig_valid = schnorr_verify(sig_bytes, msg32, pubkey_xonly)  # type: ignore[misc]
    except Exception as e:  # pragma: no cover - just surface as False
        return False, {
            "id_matches": id_matches,
            "signature_valid": False,
            "expected_id": expected_id,
            "error": str(e),
        }

    ok = id_matches and sig_valid
    return ok, {
        "id_matches": id_matches,
        "signature_valid": sig_valid,
        "expected_id": expected_id,
    }


def npub_to_hex(npub: str) -> str:
    """Convert an npub (bech32) to x-only pubkey hex. Requires bech32 package."""
    if bech32_decode is None or convertbits is None:
        raise ImportError("bech32 package is required for npub conversions")
    hrp, data = bech32_decode(npub)  # type: ignore[misc]
    if hrp != "npub" or not data:
        raise ValueError("invalid npub bech32 string")
    xonly = bytes(convertbits(data, 5, 8, False))  # type: ignore[misc]
    if len(xonly) != 32:
        raise ValueError("npub decoded length != 32 bytes")
    return xonly.hex()


def hex_to_npub(pubkey_hex: str) -> str:
    """Convert an x-only pubkey hex to npub (bech32). Requires bech32 package."""
    if bech32_encode is None or convertbits is None:
        raise ImportError("bech32 package is required for npub conversions")
    b = bytes.fromhex(pubkey_hex)
    if len(b) != 32:
        raise ValueError("x-only pubkey must be 32 bytes")
    data5 = convertbits(b, 8, 5, True)  # type: ignore[misc]
    return bech32_encode("npub", data5)  # type: ignore[misc]
