"""
Payload builders and validators for Nostr 31510/31511/31512 and helper utilities.

- canonical_json_dumps / sha256_hex
- build_intent_31510, build_challenge_31511, build_response_31512
- validate_31510, validate_31511, validate_31512 (uses jsonschema if available, otherwise basic checks)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Optional jsonschema validation
try:  # pragma: no cover - optional
    import jsonschema  # type: ignore
except Exception:  # pragma: no cover - optional
    jsonschema = None  # type: ignore

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "docs" / "schemas"


def canonical_json_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---- Builders ----

def build_intent_31510(action_id: str, type: str, params: Dict[str, Any], expires_at: int, **extra: Any) -> Dict[str, Any]:
    intent = {
        "action_id": action_id,
        "type": type,
        "params": params,
        "expires_at": expires_at,
    }
    intent.update(extra)
    return intent


def build_challenge_31511(session_id: str, type: str, payload_to_sign: str, **extra: Any) -> Dict[str, Any]:
    challenge = {
        "session_id": session_id,
        "type": type,  # e.g. "sign_tx" | "sign_payload"
        "payload_to_sign": payload_to_sign,
    }
    challenge.update(extra)
    return challenge


def build_response_31512(session_id: str, signature: str, algo: str, **extra: Any) -> Dict[str, Any]:
    response = {
        "session_id": session_id,
        "signature": signature,
        "algo": algo,  # e.g. "BIP340" | "ECDSA"
    }
    response.update(extra)
    return response


# ---- Validators ----

def _load_schema(name: str) -> Optional[Dict[str, Any]]:
    p = SCHEMAS_DIR / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _basic_required_check(obj: Dict[str, Any], required: Tuple[str, ...]) -> Tuple[bool, Optional[str]]:
    missing = [k for k in required if k not in obj]
    if missing:
        return False, f"missing fields: {', '.join(missing)}"
    return True, None


def validate_31510(obj: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if jsonschema:
        schema = _load_schema("31510_intent.schema.json")
        if schema:
            try:
                jsonschema.validate(obj, schema)  # type: ignore
                return True, None
            except Exception as e:  # pragma: no cover
                return False, str(e)
    # Fallback basic check
    return _basic_required_check(obj, ("action_id", "type", "params", "expires_at"))


def validate_31511(obj: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if jsonschema:
        schema = _load_schema("31511_challenge.schema.json")
        if schema:
            try:
                jsonschema.validate(obj, schema)  # type: ignore
                return True, None
            except Exception as e:  # pragma: no cover
                return False, str(e)
    return _basic_required_check(obj, ("session_id", "type", "payload_to_sign"))


def validate_31512(obj: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if jsonschema:
        schema = _load_schema("31512_response.schema.json")
        if schema:
            try:
                jsonschema.validate(obj, schema)  # type: ignore
                return True, None
            except Exception as e:  # pragma: no cover
                return False, str(e)
    return _basic_required_check(obj, ("session_id", "signature"))
