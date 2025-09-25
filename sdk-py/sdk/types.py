"""
Typed models for solver <-> gateway interactions and Nostr payloads.

These are light-weight typing helpers using TypedDict so they do not add runtime
requirements. They are intended for IDE assistance and type checking.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict
try:  # Python 3.11+
    from typing import NotRequired  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - fallback for Python <3.11
    try:
        from typing_extensions import NotRequired  # type: ignore
    except Exception:
        # Last-resort no-op to avoid import errors at runtime; type checkers will still flag.
        class _NR:  # type: ignore
            pass
        NotRequired = _NR  # type: ignore


# ---- Nostr 31510 / 31511 / 31512 ----


class Intent31510(TypedDict):
    action_id: str
    type: str
    params: Dict[str, Any]
    expires_at: int
    # optional
    protocol_version: NotRequired[str]
    network: NotRequired[Literal["regtest", "testnet", "mainnet"]]
    solver_id: NotRequired[str]
    deadline: NotRequired[int]
    min_out_amount: NotRequired[int]
    recipient_pubkey: NotRequired[str]


class Challenge31511(TypedDict):
    session_id: str
    type: Literal["sign_tx", "sign_payload"]
    payload_to_sign: str
    # optional
    payload_ref: NotRequired[str]
    algo: NotRequired[Literal["BIP340", "ECDSA", "OTHER"]]
    domain: NotRequired[str]
    context: NotRequired[Dict[str, Any]]
    step_index: NotRequired[int]
    step_total: NotRequired[int]
    expires_at: NotRequired[int]


class Response31512(TypedDict):
    session_id: str
    signature: str
    # optional
    type: NotRequired[Literal["sign_tx", "sign_payload"]]
    payload_ref: NotRequired[str]
    pubkey: NotRequired[str]
    algo: NotRequired[Literal["BIP340", "ECDSA", "OTHER"]]


# ---- Ceremony status ----


class CeremonyStatus(TypedDict, total=False):
    session_id: str
    state: str
    status: str
    progress: float
    error: str
    txid: str
    details: Dict[str, Any]


# ---- Asset helpers ----


class AssetInfo(TypedDict, total=False):
    asset_id: str
    name: str
    ticker: str
    total_supply: int
    circulating: int


class TransferResult(TypedDict, total=False):
    asset_id: str
    amount: int
    sender_pubkey: str
    recipient_pubkey: str
    txid: str
    status: str


class Balances(TypedDict):
    user_pubkey: str
    balances: Dict[str, int]


__all__ = [
    "Intent31510",
    "Challenge31511",
    "Response31512",
    "CeremonyStatus",
    "AssetInfo",
    "TransferResult",
    "Balances",
]
