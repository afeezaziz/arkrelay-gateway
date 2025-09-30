# ArkRelay Solver Integration Guide

This document defines the minimal contract between an external DeFi "solver" service and the ArkRelay Gateway. It describes the boundary, event/HTTP interfaces, recommended message shapes, and end-to-end sequences for common flows (lending borrow; AMM swap).

Gateway design principle: keep the gateway thin. The gateway manages signing sessions, challenge/response over Nostr DMs, VTXO management, transaction finalization, health, and admin. All DeFi protocol logic (quotes, risk, reserves, markets, pools, positions, keepers, and UIs) must live in your solver service, not in the gateway.

---

## 1. Responsibilities and Boundary

- Gateway (this repo)
  - Sessions and challenges: 31510 → 31511/31512 → 31340/31341
  - VTXO lifecycle and transaction finalization (incl. optional LN on/off-ramp helpers)
  - Health/metrics/admin endpoints
  - No DeFi tables or protocol endpoints

- Solver (your service)
  - Protocol APIs (e.g., `lend/*`, `amm/*`)
  - Market math and risk checks (rates, HF, AMM, slippage)
  - Datastore for protocol state (markets, positions, pools)
  - Keepers and schedulers (interest accrual, liquidations, TWAP)
  - Orchestrate Nostr flows and call gateway helper endpoints as needed

---

## Building a Solver

### Architecture (recommended)

- Ingestor
  - Subscribe to multiple Nostr relays; filter for kind 31510 tagged to the gateway `npub`.
  - Deduplicate by `(pubkey, action_id)`; persist raw events for audit.

- API (optional)
  - Provide your own HTTP/WebSocket API for dApps and internal tools (`/lend/*`, `/amm/*`).
  - Clients interact with your API or publish 31510; the solver orchestrates calls to the gateway.

- Core services
  - Quote/risk engines (rates, HF, AMM math, slippage guards, oracles/TWAP).
  - State management (markets, positions, pools, swaps log, idempotency keys).
  - Job runner and scheduler (interest accrual, liquidation watcher, TWAP updater).

- Integration layer
  - Gateway client using minimal HTTP endpoints (sessions, challenges, settlement, LN rails).
  - Nostr publisher for operational notices and correlation events.

### Bootstrapping checklist

1) Obtain the gateway `npub` and relay list; configure solver relays.
2) Subscribe for 31510 intents that `p`-tag the gateway `npub`.
3) Validate intents: signature, `expires_at`, schema version, `action_id` uniqueness.
4) Compute decision (quote, HF, limits) against solver DB; reject early if unsafe.
5) If signatures are required:
   - POST /sessions/create with `intent_data`.
   - POST /sessions/{session_id}/challenge including `payload_to_sign` and UX context.
   - POST /signing/ceremony/start and poll GET /signing/ceremony/{session_id}/status or listen for 31512 DMs.
6) On success, request VTXO/tx finalization (/vtxos/* or transaction helpers as needed).
   - Use `/vtxos/assign` for optimal VTXO selection (supports single and multi-VTXO transactions)
   - Use `/vtxos/split` to split large VTXOs when needed for specific denominations
   - Gateway automatically handles optimal change VTXO creation
7) Watch for 31340 (success) or 31341 (failure); update solver DB and notify clients.

### Minimal reference implementation

```mermaid
flowchart LR
  subgraph Solver
    IN[Nostr Ingestor] --> DEC[Decision Engine]
    API[Solver API] --> DEC
    DEC --> GW[Gateway Client]
    DEC --> DB[(Protocol DB)]
    JOB[Jobs/Scheduler] --> DEC
  end

  IN <--> RLY[(Relays)]
  GW --> GAPI[Gateway HTTP]
  GAPI --> GDM[Nostr DMs]
```

## 2. Nostr Event Contract

All interactive messages are Nostr events. Encrypted DMs follow NIP-04/44.

- 31510 — Intent (client → gateway)
  - User-approved, high-level action with `action_id` and `expires_at`.
  - Tags: MUST include `p` tag of the gateway `npub`.

- 31511 — Relay Signing Challenge (gateway → wallet, encrypted DM)
  - Sent when the gateway needs a signature to proceed. Includes `session_id`, `type`, and `payload_to_sign`.

- 31512 — Client Signing Response (wallet → gateway, encrypted DM)
  - Wallet returns a signature for the previously issued challenge.

- 31340 — Final Transaction Confirmation (gateway → public)
  - Public success message that correlates back to the 31510 intent. Use tags for correlation.

- 31341 — Transaction Failure Notice (gateway → wallet, encrypted DM)
  - Failure message with code and human-readable details.

- 31342 — L1 Commitment Notice (gateway → public)
  - Optional L1 settlement notice when applicable.

### 2.1 Minimal Payloads

Intent (31510):
```json
{
  "action_id": "<uuid>",
  "type": "amm:swap|lend:borrow|...",
  "params": { "...": "..." },
  "expires_at": 1735689600
}
```

Challenge (31511, DM):
```json
{
  "session_id": "<session_id>",
  "type": "sign_tx|sign_payload",
  "payload_to_sign": "<hex-or-serialized>",
  "context": { "human": "Step 2/3: authorize spend of ..." }
}
```

Response (31512, DM):
```json
{
  "session_id": "<session_id>",
  "type": "sign_tx|sign_payload",
  "signature": "<hex>",
  "payload_ref": "<hash-or-id>"
}
```

Confirmation (31340):
```json
{
  "status": "success",
  "ref_action_id": "<original-action-id>",
  "results": { "txid": "...", "outputs": ["..."] }
}
```

Failure (31341, DM):
```json
{
  "status": "failure",
  "code": 2001,
  "message": "Insufficient VTXO balance",
  "ref_action_id": "<original-action-id>"
}
```

### 2.2 31510 Intent: Schema, Validation, and Examples

Recommended fields:

- `action_id` (string, UUID v4): idempotency key, unique per user.
- `type` (string): namespaced verb, e.g., `lend:deposit`, `lend:borrow`, `amm:add_liquidity`, `amm:swap`.
- `params` (object): protocol-specific parameters.
- `expires_at` (unix seconds): authorization deadline.
- Optional: `protocol_version`, `network`, `solver_id`, `deadline`, `min_out_amount` (for swaps), `recipient_pubkey`.

Tags:
- MUST include `p` tag for the gateway `npub`.
- SHOULD include a `v` tag (schema version), and `e` tag to correlate threads.

Validation checklist (solver side):
- Verify Nostr signature, freshness (`expires_at`), and replay via `(pubkey, action_id)` uniqueness.
- Validate `type` and `params` schema; enforce bounds (amounts, slippage, deadlines).
- Compute a deterministic `payload_ref` (digest) over canonical JSON (sorted keys) for later challenge binding.

Examples:

Deposit (lending):
```json
{
  "action_id": "a8a2d7a3-5d6b-4a1a-9a44-4de6d070e3c1",
  "type": "lend:deposit",
  "params": { "asset_id": "gBTC", "amount": 250000 },
  "expires_at": 1735689600
}
```

Swap (AMM):
```json
{
  "action_id": "23c0e0d1-ac4d-4a6a-86b5-0f1f02a1d19e",
  "type": "amm:swap",
  "params": {
    "pool_id": "LP-gBTC-gUSD",
    "in_asset": "gBTC",
    "in_amount": 50000,
    "min_out_amount": 9800000,
    "deadline": 1735689600
  },
  "expires_at": 1735689600
}
```

### 2.3 31511 Challenge: Schema, Signing Domain, and UX Context

Recommended fields:

- `session_id` (string): gateway session identifier.
- `type` (string): `sign_tx` or `sign_payload`.
- `payload_to_sign` (hex): canonical bytes to sign; bind to `payload_ref`.
- `payload_ref` (string): digest/hash of the logical payload; wallet verifies match.
- `algo` (string): signature scheme hint (e.g., `BIP340`).
- `domain` (string): signing domain, e.g., `arkrelay/<protocol>/<version>`.
- `context` (object): human-readable UX hints (step number, description, amounts, recipients).
- Optional: `step_index`, `step_total`, `expires_at`.

Guidelines:
- Keep `payload_to_sign` deterministic and minimal; wallet should be able to recompute/verify using prior 31510 params.
- Include amounts, asset ids, recipient/pool identifiers in `context.human` for clarity.
- For multi-step ceremonies, send separate challenges with explicit `step_index/`
