"""
Wallet-oriented helpers for Nostr (BIP340) signing and event construction.

These are convenience utilities for wallet developers building against the
ArkRelay Gateway contract. They do not send HTTP traffic; they only handle
signing and formatting.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, Tuple, Optional

from coincurve import PrivateKey as CCPrivateKey  # type: ignore
from coincurve.schnorr import schnorr_sign, schnorr_verify  # type: ignore

from .nostr_utils import compute_event_id, verify_event, hex_to_npub  # re-export convenience


def _xonly_from_sk(sk_hex: str) -> Tuple[bytes, str]:
    sk_bytes = bytes.fromhex(sk_hex)
    ccsk = CCPrivateKey(sk_bytes)
    uncompressed = ccsk.public_key.format(compressed=False)  # 0x04 | X(32) | Y(32)
    xonly = uncompressed[1:33]
    return xonly, xonly.hex()


def bip340_sign_digest(sk_hex: str, digest_hex: str) -> str:
    """Sign a 32-byte hex digest with BIP340 Schnorr and return signature hex."""
    digest = bytes.fromhex(digest_hex)
    if len(digest) != 32:
        raise ValueError("digest must be 32 bytes hex")
    sk_bytes = bytes.fromhex(sk_hex)
    sig = schnorr_sign(digest, sk_bytes)
    return sig.hex()


def sign_message(sk_hex: str, message: str) -> Tuple[str, str]:
    """Sign a plaintext message via SHA-256 then BIP340.
    Returns (signature_hex, digest_hex).
    """
    digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
    return bip340_sign_digest(sk_hex, digest), digest


def sign_data(sk_hex: str, data: Any) -> Tuple[str, str]:
    """Sign a JSON-serializable object canonically (sorted) via SHA-256 then BIP340.
    Returns (signature_hex, digest_hex).
    """
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return bip340_sign_digest(sk_hex, digest), digest


def sign_event(
    sk_hex: str,
    kind: int,
    content: str,
    tags: Any,
    created_at: Optional[int] = None,
) -> Dict[str, Any]:
    """Build and sign a Nostr event per NIP-01 using BIP340.
    Returns the full event object with id and sig.
    """
    if created_at is None:
        created_at = int(time.time())
    xonly_bytes, pubkey_hex = _xonly_from_sk(sk_hex)
    ser = json.dumps([0, pubkey_hex, created_at, kind, tags, content], separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    event_id = hashlib.sha256(ser).hexdigest()
    sig = schnorr_sign(bytes.fromhex(event_id), bytes.fromhex(sk_hex)).hex()
    return {
        "id": event_id,
        "pubkey": pubkey_hex,
        "created_at": created_at,
        "kind": kind,
        "tags": tags,
        "content": content,
        "sig": sig,
        "npub": hex_to_npub(pubkey_hex) if len(xonly_bytes) == 32 else None,
    }


__all__ = [
    "bip340_sign_digest",
    "sign_message",
    "sign_data",
    "sign_event",
    "compute_event_id",
    "verify_event",
    "hex_to_npub",
]
