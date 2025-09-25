from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from flask import Flask, jsonify, request
import ecdsa
from bech32 import bech32_encode, convertbits
from coincurve import PrivateKey as CCPrivateKey
from coincurve.schnorr import schnorr_sign, schnorr_verify
try:
    from pynostr.key import PrivateKey as PNPrivateKey  # type: ignore
    from pynostr.event import Event as PNEvent  # type: ignore
    HAVE_PYNOSTR = True
except Exception:
    HAVE_PYNOSTR = False

# Ensure we can import the SDK from the repo when running this example standalone
REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_PY_ROOT = REPO_ROOT / "sdk-py"
if str(SDK_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_PY_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.gateway_client import GatewayClient, GatewayClientError  # noqa: E402


# ---- Signing utilities (ECDSA over secp256k1; demo only, not Nostr Schnorr) ----

def _canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_or_generate_key() -> Tuple[ecdsa.SigningKey, str, str]:
    """
    Returns (signing_key, pubkey_hex, note)
    """
    key_hex = os.getenv("SOLVER_ECDSA_PRIVKEY_HEX")
    note = "env"
    if key_hex:
        sk = ecdsa.SigningKey.from_string(bytes.fromhex(key_hex), curve=ecdsa.SECP256k1, hashfunc=hashlib.sha256)
    else:
        note = "ephemeral"
        sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1, hashfunc=hashlib.sha256)
    vk = sk.get_verifying_key()
    try:
        pubkey_hex = vk.to_string("compressed").hex()
    except TypeError:
        pubkey_hex = vk.to_string().hex()
    return sk, pubkey_hex, note


SK, PUBKEY_HEX, KEY_NOTE = _load_or_generate_key()

app = Flask(__name__)
GATEWAY_BASE_URL = os.getenv("GATEWAY_BASE_URL", "http://localhost:8000").rstrip("/")
GC = GatewayClient(GATEWAY_BASE_URL)

# --- Nostr (BIP340) key for Schnorr signatures ---
def _load_or_generate_nostr_key() -> tuple[bytes, str, str]:
    sk_hex = os.getenv("NOSTR_PRIVATE_KEY")
    note = "env"
    if sk_hex:
        sk_bytes = bytes.fromhex(sk_hex)
    else:
        note = "ephemeral"
        sk_bytes = os.urandom(32)
    ccsk = CCPrivateKey(sk_bytes)
    # Get x-only public key (first 32 bytes of uncompressed without 0x04 prefix)
    uncompressed = ccsk.public_key.format(compressed=False)
    xonly = uncompressed[1:33]
    # npub bech32
    npub_words = convertbits(xonly, 8, 5, True)
    npub = bech32_encode("npub", npub_words)
    return sk_bytes, xonly.hex(), npub

NOSTR_SK_BYTES, NOSTR_PUBKEY_XONLY_HEX, NOSTR_NPUB = _load_or_generate_nostr_key()


@app.route("/health", methods=["GET"]) 
def health() -> Any:
    return jsonify({
        "status": "ok",
        "gateway": GATEWAY_BASE_URL,
        "pubkey": PUBKEY_HEX,
        "key_source": KEY_NOTE,
    })


@app.route("/simulate/public-key", methods=["GET"]) 
def public_key() -> Any:
    return jsonify({"pubkey": PUBKEY_HEX, "algo": "ECDSA_secp256k1_SHA256", "note": KEY_NOTE})


@app.route("/simulate/nostr/public-key", methods=["GET"]) 
def nostr_public_key() -> Any:
    return jsonify({
        "pubkey_xonly": NOSTR_PUBKEY_XONLY_HEX,
        "npub": NOSTR_NPUB,
        "algo": "BIP340_Schnorr",
    })


@app.route("/simulate/generate-intent", methods=["POST", "GET"]) 
def generate_intent() -> Any:
    """
    Generate a simulated 31510 intent based on current time.
    Even minute -> transfer; odd minute -> misc:sign_note.
    """
    user_pubkey = request.values.get("user_pubkey", "npub1example...")
    now = int(time.time())
    minute = (now // 60) % 60
    action_id = str(uuid.uuid4())

    if minute % 2 == 0:
        intent = {
            "action_id": action_id,
            "type": "transfer",
            "params": {
                "asset_id": "gBTC",
                "amount": 12345,
                "recipient_pubkey": "npub1recipient..."
            },
            "expires_at": now + 600,
        }
    else:
        intent = {
            "action_id": action_id,
            "type": "misc:sign_note",
            "params": {
                "note": f"Hello from solver at {now}",
                "created_at": now,
            },
            "expires_at": now + 600,
        }

    return jsonify({
        "user_pubkey": user_pubkey,
        "intent": intent,
    })


@app.route("/simulate/sign", methods=["POST"]) 
def simulate_sign() -> Any:
    """
    Sign an arbitrary JSON payload or generate one when {"generate": "transfer|note"} is provided.
    Body:
    - data: object (optional)
    - generate: "transfer"|"note" (optional)
    """
    body = request.get_json(silent=True) or {}
    generate = body.get("generate")
    data = body.get("data")

    now = int(time.time())
    if not data:
        if generate == "transfer":
            data = {"type": "transfer", "asset_id": "gBTC", "amount": 1000, "recipient_pubkey": "npub1recipient...", "ts": now}
        elif generate == "note":
            data = {"type": "note", "content": f"auto note @ {now}", "ts": now}
        else:
            return jsonify({"error": "Provide 'data' or set 'generate' to 'transfer'|'note'"}), 400

    b = _canonical_json_bytes(data)
    digest_hex = _sha256_hex(b)
    sig_bytes = SK.sign_digest(bytes.fromhex(digest_hex))
    sig_hex = sig_bytes.hex()

    return jsonify({
        "payload": data,
        "payload_to_sign": f"0x{digest_hex}",
        "payload_ref": f"sha256:{digest_hex}",
        "signature": sig_hex,
        "algo": "ECDSA_secp256k1_SHA256",
        "pubkey": PUBKEY_HEX,
        "note": "Demo signature; not Nostr Schnorr compatible",
    })


@app.route("/simulate/logic", methods=["GET"]) 
def simulate_logic() -> Any:
    """
    Sample logic: if current minute is even, produce and sign a transfer.
    Otherwise, sign a note-like structure.
    """
    now = int(time.time())
    minute = (now // 60) % 60

    if minute % 2 == 0:
        obj = {"type": "transfer", "asset_id": "gBTC", "amount": 7777, "recipient_pubkey": "npub1recipient...", "ts": now}
    else:
        obj = {"type": "note", "content": f"minute {minute} odd", "ts": now}

    b = _canonical_json_bytes(obj)
    digest_hex = _sha256_hex(b)
    sig_hex = SK.sign_digest(bytes.fromhex(digest_hex)).hex()

    return jsonify({
        "payload": obj,
        "payload_to_sign": f"0x{digest_hex}",
        "signature": sig_hex,
        "algo": "ECDSA_secp256k1_SHA256",
        "pubkey": PUBKEY_HEX,
    })


@app.route("/simulate/verify", methods=["POST"]) 
def simulate_verify() -> Any:
    """
    Verify a signature for a given payload. Body:
    - algorithm: "ecdsa" | "nostr"
    - data | message | digest
    - signature: hex
    """
    body = request.get_json(silent=True) or {}
    algo = (body.get("algorithm") or "ecdsa").lower()
    signature_hex = body.get("signature")
    if not signature_hex:
        return jsonify({"error": "signature is required"}), 400

    # Compute 32-byte digest
    if "digest" in body:
        dhex = str(body["digest"]).removeprefix("0x")
        try:
            digest_bytes = bytes.fromhex(dhex)
        except ValueError:
            return jsonify({"error": "invalid digest hex"}), 400
        if len(digest_bytes) != 32:
            return jsonify({"error": "digest must be 32 bytes"}), 400
    elif "data" in body:
        digest_bytes = hashlib.sha256(_canonical_json_bytes(body["data"])).digest()
    elif "message" in body:
        digest_bytes = hashlib.sha256(str(body["message"]).encode("utf-8")).digest()
    else:
        return jsonify({"error": "provide one of: digest | data | message"}), 400

    ok = False
    if algo == "ecdsa":
        try:
            vk = SK.get_verifying_key()
            ok = vk.verify_digest(bytes.fromhex(signature_hex), digest_bytes)
        except Exception:
            ok = False
    elif algo == "nostr":
        try:
            ok = schnorr_verify(bytes.fromhex(signature_hex), digest_bytes, bytes.fromhex(NOSTR_PUBKEY_XONLY_HEX))
        except Exception:
            ok = False
    else:
        return jsonify({"error": "unsupported algorithm"}), 400

    return jsonify({"valid": ok, "algorithm": algo})


@app.route("/simulate/nostr/sign", methods=["POST"]) 
def simulate_nostr_sign() -> Any:
    """
    Sign using BIP340 Schnorr with the Nostr key.
    Provide one of: digest (hex 32), data (object), message (string).
    """
    body = request.get_json(silent=True) or {}

    if "digest" in body:
        dhex = str(body["digest"]).removeprefix("0x")
        try:
            msg32 = bytes.fromhex(dhex)
        except ValueError:
            return jsonify({"error": "invalid digest hex"}), 400
        if len(msg32) != 32:
            return jsonify({"error": "digest must be 32 bytes"}), 400
    elif "data" in body:
        msg32 = hashlib.sha256(_canonical_json_bytes(body["data"])).digest()
    elif "message" in body:
        msg32 = hashlib.sha256(str(body["message"]).encode("utf-8")).digest()
    else:
        return jsonify({"error": "provide one of: digest | data | message"}), 400

    sig = schnorr_sign(msg32, NOSTR_SK_BYTES)
    return jsonify({
        "signature": sig.hex(),
        "pubkey_xonly": NOSTR_PUBKEY_XONLY_HEX,
        "npub": NOSTR_NPUB,
        "digest": msg32.hex(),
        "algo": "BIP340_Schnorr",
    })


@app.route("/simulate/nostr/sign-event", methods=["POST"]) 
def simulate_nostr_sign_event() -> Any:
    """
    Sign a Nostr event per NIP-01 using the BIP340 key.
    Body: { "kind": 1, "content": "...", "tags": [["p", "..."], ...], "created_at": optional }
    Returns: event object with id and sig.
    """
    body = request.get_json(silent=True) or {}
    kind = int(body.get("kind", 1))
    content = str(body.get("content", ""))
    tags = body.get("tags") or []
    created_at = int(body.get("created_at") or int(time.time()))

    # Per NIP-01: serialize as [0, pubkey, created_at, kind, tags, content]
    pubkey = NOSTR_PUBKEY_XONLY_HEX
    serialized = json.dumps([0, pubkey, created_at, kind, tags, content], separators=(",", ":"), ensure_ascii=False)
    msg32 = hashlib.sha256(serialized.encode("utf-8")).digest()
    sig = schnorr_sign(msg32, NOSTR_SK_BYTES)

    event = {
        "id": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "pubkey": pubkey,
        "created_at": created_at,
        "kind": kind,
        "tags": tags,
        "content": content,
        "sig": sig.hex(),
    }
    return jsonify(event)


@app.route("/simulate/nostr/verify-event", methods=["POST"]) 
def simulate_nostr_verify_event() -> Any:
    """
    Verify a Nostr event (NIP-01): recompute id from [0, pubkey, created_at, kind, tags, content]
    and verify Schnorr signature over the id using x-only pubkey.
    Body must include: id, pubkey, created_at, kind, tags, content, sig
    """
    body = request.get_json(silent=True) or {}
    required = ["id", "pubkey", "created_at", "kind", "tags", "content", "sig"]
    missing = [k for k in required if k not in body]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    try:
        created_at = int(body["created_at"])
        kind = int(body["kind"])
        tags = body["tags"]
        content = body["content"]
        pubkey = str(body["pubkey"]).lower()
        sig_hex = str(body["sig"]).lower()
    except Exception as e:
        return jsonify({"error": f"Invalid field types: {e}"}), 400

    serialized = json.dumps([0, pubkey, created_at, kind, tags, content], separators=(",", ":"), ensure_ascii=False)
    expected_id = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    id_matches = (expected_id == body["id"].lower())

    ok = False
    try:
        msg32 = bytes.fromhex(expected_id)
        ok = schnorr_verify(bytes.fromhex(sig_hex), msg32, bytes.fromhex(pubkey))
    except Exception:
        ok = False

    return jsonify({
        "id_matches": id_matches,
        "signature_valid": ok,
        "expected_id": expected_id,
    })


@app.route("/simulate/nostr/sign-event-pynostr", methods=["POST"]) 
def simulate_nostr_sign_event_pynostr() -> Any:
    """
    Attempt to sign a Nostr event using pynostr's Event/PrivateKey APIs.
    Body: { "kind": 1, "content": "...", "tags": [["p", "..."], ...], "created_at": optional }
    """
    if not HAVE_PYNOSTR:
        return jsonify({"error": "pynostr not available"}), 501

    body = request.get_json(silent=True) or {}
    kind = int(body.get("kind", 1))
    content = str(body.get("content", ""))
    tags = body.get("tags") or []
    created_at = int(body.get("created_at") or int(time.time()))

    try:
        sk = PNPrivateKey(NOSTR_SK_BYTES.hex())  # type: ignore[arg-type]
        pubkey = sk.public_key.hex()
        # pynostr Event signature API varies slightly across versions; try a common signature
        ev = PNEvent(public_key=pubkey, kind=kind, tags=tags, content=content, created_at=created_at)  # type: ignore[call-arg]
        sk.sign_event(ev)  # type: ignore[attr-defined]
        out = {
            "id": getattr(ev, "id", None),
            "pubkey": pubkey,
            "created_at": created_at,
            "kind": kind,
            "tags": tags,
            "content": content,
            "sig": getattr(ev, "sig", None),
        }
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": f"pynostr signing failed: {e}"}), 500


@app.route("/simulate/intent", methods=["POST"]) 
def simulate_intent() -> Any:
    """
    Accept an intent (31510-like) and ask the gateway to create a session & issue a challenge.
    Body must include: user_pubkey, action_id, type, params, expires_at
    """
    body = request.get_json(silent=True) or {}
    required = ["user_pubkey", "action_id", "type", "params", "expires_at"]
    missing = [k for k in required if k not in body]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    intent_data = {
        "action_id": body["action_id"],
        "type": body["type"],
        "params": body["params"],
        "expires_at": body["expires_at"],
    }

    try:
        session_resp = GC.create_session(
            user_pubkey=body["user_pubkey"],
            session_type="protocol_op",
            intent_data=intent_data,
        )
    except GatewayClientError as e:
        return jsonify({"error": f"Failed to create session: {e}"}), 502

    session_id = session_resp.get("session_id") or session_resp.get("id")
    if not session_id:
        return jsonify({"error": "Gateway did not return session_id"}), 502

    # Bind a deterministic challenge to the logical payload
    canonical = _canonical_json_bytes({
        "action_id": body["action_id"],
        "type": body["type"],
        "params": body["params"],
    })
    digest = _sha256_hex(canonical)

    challenge_data = {
        "payload_to_sign": f"0x{digest}",
        "payload_ref": f"sha256:{digest}",
        "type": "sign_payload",
    }
    context = {
        "human": f"Authorize {body['type']} (action {body['action_id']})",
    }

    try:
        ch_resp = GC.create_challenge(session_id=session_id, challenge_data=challenge_data, context=context)
    except GatewayClientError as e:
        return jsonify({"error": f"Failed to create challenge: {e}"}), 502

    return jsonify({
        "session_id": session_id,
        "challenge": ch_resp,
        "next_steps": [
            "Respond to 31511 via wallet (31512 DM)",
            "Then start/monitor ceremony using /signing/ceremony endpoints"
        ],
    })


@app.route("/simulate/ceremony/start", methods=["POST"]) 
def simulate_ceremony_start() -> Any:
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id")
    if not session_id:
        return jsonify({"error": "session_id required"}), 400
    try:
        start_resp = GC.start_ceremony(session_id=session_id)
    except GatewayClientError as e:
        return jsonify({"error": f"Failed to start ceremony: {e}"}), 502
    return jsonify(start_resp)


@app.route("/simulate/ceremony/<session_id>/status", methods=["GET"]) 
def simulate_ceremony_status(session_id: str) -> Any:
    try:
        status = GC.get_ceremony_status(session_id=session_id)
    except GatewayClientError as e:
        return jsonify({"error": f"Failed to get ceremony status: {e}"}), 502
    return jsonify(status)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "9000")), debug=True)
