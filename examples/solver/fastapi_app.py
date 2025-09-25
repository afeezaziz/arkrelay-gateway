from __future__ import annotations

import json
import os
import hashlib
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Ensure we can import the SDK from the repo when running this example standalone
REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_PY_ROOT = REPO_ROOT / "sdk-py"
if str(SDK_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_PY_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.gateway_client import GatewayClient, GatewayClientError  # noqa: E402


class SimulatedIntent(BaseModel):
    user_pubkey: str = Field(..., description="User npub (nostr pubkey)")
    action_id: str = Field(..., description="Idempotency key (UUID v4 recommended)")
    type: str = Field(..., description="Action type, e.g., amm:swap, lend:borrow")
    params: Dict[str, Any] = Field(default_factory=dict)
    expires_at: int = Field(..., description="Unix seconds when the intent expires")


class CeremonyRequest(BaseModel):
    session_id: str


app = FastAPI(title="ArkRelay Solver Example (FastAPI)", version="0.1.0")

GATEWAY_BASE_URL = os.getenv("GATEWAY_BASE_URL", "http://localhost:8000").rstrip("/")
client = GatewayClient(GATEWAY_BASE_URL)


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "gateway": GATEWAY_BASE_URL}


@app.post("/simulate/intent")
async def simulate_intent(intent: SimulatedIntent) -> Dict[str, Any]:
    """
    Development helper to simulate receiving a 31510 intent and asking the gateway
    to issue a 31511 challenge. In production, subscribe to relays and process
    actual events instead of calling this endpoint.
    """
    # 1) Create a signing session at the gateway with the provided intent data
    intent_data = {
        "action_id": intent.action_id,
        "type": intent.type,
        "params": intent.params,
        "expires_at": intent.expires_at,
    }

    try:
        session_resp = client.create_session(
            user_pubkey=intent.user_pubkey,
            session_type="protocol_op",
            intent_data=intent_data,
        )
    except GatewayClientError as e:
        raise HTTPException(status_code=502, detail=f"Failed to create session: {e}")

    session_id = session_resp.get("session_id") or session_resp.get("id")
    if not session_id:
        raise HTTPException(status_code=502, detail="Gateway did not return session_id")

    # 2) Compute a deterministic digest from logical payload to anchor the challenge
    canonical = json.dumps({
        "action_id": intent.action_id,
        "type": intent.type,
        "params": intent.params,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()

    challenge_data = {
        "payload_to_sign": f"0x{digest}",
        "payload_ref": f"sha256:{digest}",
        "type": "sign_payload",
    }
    context = {
        "human": f"Authorize {intent.type} (action {intent.action_id})",
    }

    try:
        ch_resp = client.create_challenge(session_id=session_id, challenge_data=challenge_data, context=context)
    except GatewayClientError as e:
        raise HTTPException(status_code=502, detail=f"Failed to create challenge: {e}")

    return {
        "session_id": session_id,
        "challenge": ch_resp,
        "next_steps": [
            "Have the wallet respond to 31511 via DM (31512)",
            "Then start/monitor the signing ceremony using /signing/ceremony endpoints on the gateway",
        ],
    }


@app.post("/simulate/ceremony/start")
async def simulate_ceremony_start(body: CeremonyRequest) -> Dict[str, Any]:
    try:
        start_resp = client.start_ceremony(session_id=body.session_id)
    except GatewayClientError as e:
        raise HTTPException(status_code=502, detail=f"Failed to start ceremony: {e}")
    return start_resp


@app.get("/simulate/ceremony/{session_id}/status")
async def simulate_ceremony_status(session_id: str) -> Dict[str, Any]:
    try:
        status = client.get_ceremony_status(session_id=session_id)
    except GatewayClientError as e:
        raise HTTPException(status_code=502, detail=f"Failed to get ceremony status: {e}")
    return status
