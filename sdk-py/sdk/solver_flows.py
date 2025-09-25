"""
High-level solver flows for ArkRelay Gateway to reduce boilerplate.

- accept_intent_and_issue_challenge: create session, compute digest, and create 31511 challenge
- start_and_wait_ceremony: start ceremony and poll until terminal state
- make_intent_digest: canonical digest for an intent's logical payload
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Tuple, Optional

from .gateway_client import GatewayClient
from .ceremony import wait_for_ceremony


def make_intent_digest(action_id: str, type: str, params: Dict[str, Any]) -> str:
    canonical = json.dumps({
        "action_id": action_id,
        "type": type,
        "params": params,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def accept_intent_and_issue_challenge(
    client: GatewayClient,
    user_pubkey: str,
    intent: Dict[str, Any],
    challenge_type: str = "sign_payload",
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a session for a 31510-like intent, compute a deterministic digest
    for the logical payload, and issue a 31511 challenge bound to that digest.

    Returns a dict with session_id and challenge.
    """
    required = ["action_id", "type", "params", "expires_at"]
    missing = [k for k in required if k not in intent]
    if missing:
        raise ValueError(f"intent missing fields: {', '.join(missing)}")

    session_resp = client.create_session(user_pubkey=user_pubkey, session_type="protocol_op", intent_data=intent)
    session_id = session_resp.get("session_id") or session_resp.get("id")
    if not session_id:
        raise RuntimeError("gateway did not return session_id")

    digest = make_intent_digest(intent["action_id"], intent["type"], intent["params"])
    challenge_data = {
        "payload_to_sign": f"0x{digest}",
        "payload_ref": f"sha256:{digest}",
        "type": challenge_type,
    }
    ch_resp = client.create_challenge(session_id=session_id, challenge_data=challenge_data, context=context or {})
    return {"session_id": session_id, "challenge": ch_resp}


def start_and_wait_ceremony(
    client: GatewayClient,
    session_id: str,
    timeout: float = 120.0,
    interval: float = 1.0,
) -> Tuple[bool, Dict[str, Any]]:
    """Start the ceremony and block until it completes, fails, or times out."""
    client.start_ceremony(session_id=session_id)
    return wait_for_ceremony(client, session_id=session_id, timeout=timeout, interval=interval)
