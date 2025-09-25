# ArkRelay Solver Example (Flask)

This example shows a minimal solver service that integrates with the ArkRelay Gateway using the thin-gateway pattern:
- Solver computes protocol logic and orchestrates authorization.
- Gateway handles sessions/challenges (31511/31512), VTXO/transaction finalization, and optional Lightning rails.

The example exposes endpoints to:
- Accept a 31510-like intent and create a session + issue a gateway signing challenge
- Generate simulated JSON payloads and sign them (demo ECDSA over secp256k1)
- Run sample time-based logic (transfer vs note) and sign the result

## Prerequisites

- Python 3.11+
- Running ArkRelay Gateway at `http://localhost:8000` (or set `GATEWAY_BASE_URL`)

## Setup

```bash
actions() {
  cd examples/solver
  python -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
}
actions
```

Export environment variables (optional):

```bash
export GATEWAY_BASE_URL=http://localhost:8000
```

## Run

```bash
python app_flask.py
```

- Health: http://localhost:9000/health
- Public key (demo): http://localhost:9000/simulate/public-key
- Nostr public key (BIP340): http://localhost:9000/simulate/nostr/public-key
- Generate intent (time-based): http://localhost:9000/simulate/generate-intent
- Sign arbitrary or generated JSON: http://localhost:9000/simulate/sign
- Sample logic (time-based, auto-signed): http://localhost:9000/simulate/logic
- Accept intent and create challenge: http://localhost:9000/simulate/intent
- Verify signatures (ECDSA or Nostr): POST http://localhost:9000/simulate/verify
- Nostr sign (Schnorr/BIP340): POST http://localhost:9000/simulate/nostr/sign
- Nostr sign event (NIP-01): POST http://localhost:9000/simulate/nostr/sign-event
- Nostr verify event (NIP-01): POST http://localhost:9000/simulate/nostr/verify-event
- Nostr sign event (pynostr): POST http://localhost:9000/simulate/nostr/sign-event-pynostr

## Simulate a 31510 Intent

This is a development helper to emulate an incoming Nostr intent (31510). In production you would subscribe to relays and process actual events.

```bash
# 1) Accept intent and create a 31511 challenge at the gateway
curl -s -X POST :9000/simulate/intent -H 'Content-Type: application/json' -d '{
  "user_pubkey": "npub1example...",
  "action_id": "00000000-0000-0000-0000-000000000001",
  "type": "amm:swap",
  "params": {
    "pool_id": "LP-gBTC-gUSD",
    "in_asset": "gBTC",
    "in_amount": 50000,
    "min_out_amount": 9800000
  },
  "expires_at": 1735689600
}' | jq

# 2) Generate a simulated intent (even minute -> transfer, odd minute -> sign_note)
curl -s :9000/simulate/generate-intent | jq

# 3) Sign arbitrary or generated JSON (set generate=transfer|note)
curl -s -X POST :9000/simulate/sign -H 'Content-Type: application/json' -d '{"generate":"transfer"}' | jq
curl -s -X POST :9000/simulate/sign -H 'Content-Type: application/json' -d '{"generate":"note"}' | jq
curl -s -X POST :9000/simulate/sign -H 'Content-Type: application/json' -d '{"data": {"hello":"world"}}' | jq

# 4) Time-based sample logic (auto-signed)
curl -s :9000/simulate/logic | jq

# 5) Ceremony control (after wallet 31512 DM is processed by the gateway)
curl -s -X POST :9000/simulate/ceremony/start -H 'Content-Type: application/json' -d '{"session_id":"<SESSION_ID>"}' | jq
curl -s :9000/simulate/ceremony/<SESSION_ID>/status | jq
```

Example response:

```json
{
  "session_id": "sess_01HX...",
  "challenge": {"challenge_id": "chg_...", "status": "issued"},
  "next_steps": [
    "Respond to 31511 via wallet (31512 DM)",
    "Then start/monitor ceremony using /signing/ceremony endpoints"
  ]
}
```

## Notes

- This example imports the SDK helper from `sdk/gateway_client.py` in the repository root.
- Demo signing uses ECDSA secp256k1 with SHA-256 and is not a Nostr BIP340 Schnorr signature.
- Provide a stable key via `SOLVER_ECDSA_PRIVKEY_HEX=<64-hex>` or an ephemeral key is generated on startup.
- The example does not implement real Nostr subscription or finalization logic—see `docs/developers/solver-integration.md` for the full event flow and contract.
- Use the gateway’s dev endpoints (`/sessions/<id>/respond`) only for testing.

---

### Optional: FastAPI variant

If you prefer FastAPI, an alternative app is provided at `fastapi_app.py` and can be run with:

```bash
uvicorn fastapi_app:app --reload --port 9000
```

---

## CLI helper

A small CLI is provided to exercise the example endpoints.

Run with:

```bash
cd examples/solver
python cli.py --help
```

Examples:

```bash
# Generate a time-based intent
python cli.py gen-intent

# Accept an intent (creates session + 31511 challenge)
python cli.py accept-intent --intent-file intent.json  # or omit to auto-generate

# Start and check ceremony
python cli.py ceremony-start --session-id <SESSION_ID>
python cli.py ceremony-status --session-id <SESSION_ID>

# Sign & verify
python cli.py sign-ecdsa --generate transfer
python cli.py verify --algorithm ecdsa --data '{"hello":"world"}' --signature <SIG_HEX>

# Nostr Schnorr
python cli.py nostr-sign --message "hello nostr"
python cli.py nostr-sign-event --kind 1 --content "gm" --tags '[["p","<pubkey>"]]'
python cli.py nostr-verify-event --event '{"id":"...","pubkey":"...","kind":1,"content":"gm","tags":[],"created_at":1234567890,"sig":"..."}'
```

Notes:
- For Nostr signing, you can set `NOSTR_PRIVATE_KEY` (hex). Otherwise an ephemeral key is generated and exposed via `/simulate/nostr/public-key`.
