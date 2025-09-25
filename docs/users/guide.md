# ArkRelay Gateway — User & Developer Guide

This guide explains what the ArkRelay Gateway does, how it is structured, and how operators, dApp developers, and wallet builders can take advantage of its capabilities. It consolidates information from the codebase to provide practical, copy/pasteable examples.

- Repo root: `arkrelay/gateway/`
- App entrypoint: `app.py` (Flask HTTP API)
- Core modules: `core/`
- gRPC clients: `grpc_clients/`
- Nostr integration: `nostr_clients/`
- Background tasks: `core/tasks.py`

---

## Quick Start

- Prereqs
  - Python 3.12+
  - Redis
  - MariaDB
- Install dependencies
  ```bash
  # Recommended
  uv sync

  # Or
  pip install -r requirements.txt
  ```
- Configure environment
  - Copy `.env.example` to `.env` and set values
  - Minimum: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`
- Initialize DB
  ```bash
  # Option A: Alembic
  alembic upgrade head

  # Option B: Create tables directly
  python -c "from core.models import create_tables; create_tables()"
  ```
- Run the app
  ```bash
  python app.py  # dev
  # or
  gunicorn app:app -b 0.0.0.0:8000  # prod-like
  ```
- Optional: Docker Compose (dev)
  ```bash
  docker compose -f docker-compose.dev.yml up --build
  ```

---

## Architecture Overview

- Web/API: Flask app in `app.py` exposes read-only ops, admin insights, helper endpoints, and dev-friendly flows for sessions/signing, assets, Lightning, and VTXOs
- Task Queue: Redis Queue (RQ) for asynchronous work (`core/tasks.py`)
- Scheduler: Periodic jobs (e.g., cleanup, metrics)
- Database: MariaDB via SQLAlchemy models (`core/models.py`)
- Monitoring: `core/monitoring.py` with Prometheus metrics and alerting
- Performance: Redis-backed caching and DB pooling (`core/cache_manager.py`)
- External Services via gRPC: `grpc_clients/` (ARKD, TAPD, LND)
- Nostr Integration: `nostr_clients/` provides connectivity, workers, and encrypted DM support

```mermaid
flowchart LR
  subgraph Clients
    U[User Wallet / dApp]
    Ops[Operator Tools]
  end

  U -->|HTTP/Nostr| API[Flask API (app.py)]
  Ops -->|/admin| API

  API --> RQ[Redis Queue]
  API --> DB[(MariaDB/SQLAlchemy)]
  API --> MON[Monitoring]
  API --> CACH[Cache/Pool]

  API --> GRPCMGR[gRPC Manager]
  GRPCMGR --> ARKD[arkd]
  GRPCMGR --> TAPD[tapd]
  GRPCMGR --> LND[lnd]

  API --> NOSTR[Nostr Client]
```

---

## Data Model Reference (core/models.py)

- `JobLog`: job_id, job_type, status, message, result_data, duration
- `SystemMetrics`: CPU, memory, disk, timestamp
- `Heartbeat`: service_name, is_alive, message, timestamp
- `Asset`: asset_id, name, ticker, type, decimal_places, total_supply, is_active
- `AssetBalance`: user_pubkey, asset_id, balance, reserved_balance
- `Vtxo`: vtxo_id, txid, vout, amount_sats, script_pubkey, asset_id, user_pubkey, status, expires_at, spending_txid
- `SigningSession`: session_id, user_pubkey, session_type, status, intent_data, context, expires_at, result_data, signed_tx
- `SigningChallenge`: challenge_id, session_id, challenge_data, context, expires_at, is_used, signature
- `Transaction`: txid, session_id, tx_type, raw_tx, status, amount_sats, fee_sats
- `LightningInvoice`: payment_hash, bolt11_invoice, session_id, amount_sats, asset_id, status, invoice_type

---

## Configuration (core/config.py, .env.example)

Key environment variables:

- Database & Redis
  - `DATABASE_URL` (e.g., `mysql+pymysql://user:password@mariadb:3306/arkrelay`)
  - `REDIS_URL` (e.g., `redis://redis:6379/0`)
- Flask
  - `FLASK_ENV`, `FLASK_DEBUG`, `SECRET_KEY`
- Bitcoin Network
  - `BITCOIN_NETWORK` (testnet|regtest|mainnet)
- gRPC Daemons
  - `ARKD_HOST`, `ARKD_PORT`, `ARKD_TLS_CERT`, `ARKD_MACAROON`
  - `TAPD_HOST`, `TAPD_PORT`, `TAPD_TLS_CERT`, `TAPD_MACAROON`
  - `LND_HOST`, `LND_PORT`, `LND_TLS_CERT`, `LND_MACAROON`
- Nostr
  - `NOSTR_RELAYS` (comma-separated)
  - `NOSTR_PRIVATE_KEY` (hex)
- Session/Challenge
  - `SESSION_TIMEOUT_MINUTES` (default 30)
  - `CHALLENGE_TIMEOUT_MINUTES` (default 5)
- VTXO
  - `VTXO_EXPIRATION_HOURS` (default 24), `VTXO_MIN_AMOUNT_SATS`
- Monitoring & Admin
  - `ENABLE_METRICS`, `METRICS_PORT`, `ADMIN_API_KEY`

---

## HTTP API Surface (app.py)

Base URL: `http://localhost:8000`

### Solver Integration Contract (Minimal Gateway API)

This gateway is intentionally thin. It should not host DeFi protocol endpoints or tables. Solvers (external services) implement protocol logic and use the gateway only for:

- Nostr-based authorization and signing
  - 31510 Intent (client → gateway)
  - 31511 Challenge (gateway → wallet via encrypted DM)
  - 31512 Response (wallet → gateway via encrypted DM)
  - 31340 Confirmation (gateway → public)
  - 31341 Failure (gateway → wallet DM)

- Minimal helper HTTP endpoints
  - Sessions/signing: `POST /sessions/create`, `POST /sessions/<session_id>/challenge`, `POST /sessions/<session_id>/respond`, `POST /signing/ceremony/start`, `GET /signing/ceremony/<session_id>/status`
  - VTXO/settlement: `POST /vtxos/batch/create`, `POST /vtxos/assign`, `POST /vtxos/mark-spent`, `POST /vtxos/settlement/process`, `GET /vtxos/settlement/status`
  - Optional rails: `POST /lightning/lift`, `POST /lightning/land`, `POST /lightning/pay/<payment_hash>`

All DeFi-specific APIs (e.g., `lend/*`, `amm/*`) and data models (markets, positions, pools) must live in the solver service. See `../developers/defi-guide.md` and `../developers/solver-integration.md`.

### Health and Status
- `GET /` — Gateway information
- `GET /health` — Basic health
- `GET /ready` — Readiness
- `GET /queue-status` — Queue stats (RQ)
- `GET /stats` — Aggregated service stats
- `GET /metrics` — Latest system metrics (DB)
- `GET /heartbeats` — Recent service heartbeats

### gRPC Service Helpers
- `GET /grpc/arkd/info` — ARKD info
- `GET /grpc/tapd/balances` — TAPD balances
- `GET /grpc/lnd/balances` — LND balances
- `GET /grpc/reconnect/<arkd|tapd|lnd>` — Reconnect client

### Nostr Service
- `POST /nostr/start` — Start Nostr client and workers
- `POST /nostr/stop` — Stop Nostr
- `GET /nostr/status` — Status
- `POST /nostr/send-dm` — Send encrypted DM
- `POST /nostr/publish-test` — Publish test event
- `GET /nostr/relays` — Relay connectivity
- `POST /nostr/test-encryption` — Encrypt/decrypt test

### Session Management (core/session_manager.py)
- `POST /sessions/create` — Create session
  - body: `{"user_pubkey":"...","session_type":"p2p_transfer|lightning_lift|lightning_land","intent_data":{...}}`
- `GET /sessions/<session_id>` — Session info
- `POST /sessions/<session_id>/challenge` — Create challenge (requires session in `initiated`)
- `POST /sessions/<session_id>/respond` — Submit signature
- `POST /sessions/<session_id>/complete` — Mark completed (optional payload)
- `POST /sessions/<session_id>/fail` — Mark failed
- `GET /sessions` — List sessions (with `?user_pubkey=...&status=...`)
- `POST /sessions/cleanup` — Cleanup expired sessions/challenges
- `GET /sessions/stats` — Aggregated counts

Session states (enum `SessionState` in `core/session_manager.py`):
- `initiated` (alias: `pending`)
- `challenge_sent`
- `awaiting_signature` (alias: `response_received`)
- `signing`
- `completed` | `failed` | `expired`

### Signing Ceremony (core/signing_orchestrator.py)
- `POST /signing/ceremony/start` — Start ceremony (requires session in `awaiting_signature`)
- `GET /signing/ceremony/<session_id>/status` — Ceremony status
- `POST /signing/ceremony/<session_id>/step/<1..6>` — Execute specific step
- `POST /signing/ceremony/<session_id>/cancel` — Cancel

Step order (`SigningStep`):
1. `intent_verification`
2. `ark_transaction_prep`
3. `checkpoint_transaction_prep`
4. `signature_collection`
5. `ark_protocol_execution`
6. `finalization`

### Transactions (core/transaction_processor.py)
Note: These are development/ops helpers for low-level transaction control and debugging. In production, protocol solvers should manage state and call the gateway only for signing/settlement.
- `POST /transactions/p2p-transfer` — Prepare P2P transfer transaction
  - body: `{ "session_id": "..." }`
- `GET /transactions/<txid>/status` — Get status
- `POST /transactions/<txid>/broadcast` — Broadcast
- `GET /transactions/user/<user_pubkey>` — User transactions
- `POST /transactions/user/confirm/<txid>` — Confirm transaction

### Asset Management (core/asset_manager.py)
Note: Dev/ops helpers for simple balances/transfers and VTXO utilities. Do not build DeFi protocol surfaces here; implement them in a separate solver service.
- `POST /assets` — Create asset
- `GET /assets` — List assets (`?active_only=true|false`)
- `GET /assets/<asset_id>` — Asset info
- `POST /assets/<asset_id>/mint` — Mint to user
- `POST /assets/transfer` — Transfer between users
- `GET /balances/<user_pubkey>` — All balances for user
- `GET /balances/<user_pubkey>/<asset_id>` — Specific balance
- `GET /vtxos/<user_pubkey>` — Manage VTXOs (query param `action=list|create|assign|spend`)
- `GET /assets/stats` — Aggregated stats
- `POST /assets/cleanup-vtxos` — Mark expired VTXOs
- `GET /assets/<asset_id>/reserve` — Reserve requirements

### VTXO Management (core/vtxo_manager.py)
- `GET /vtxos/inventory/<asset_id>` — Inventory status
- `POST /vtxos/batch/create` — Create VTXO batch
- `POST /vtxos/assign` — Assign VTXO to user
- `GET /vtxos/user/<user_pubkey>` — User VTXOs
- `POST /vtxos/mark-spent` — Mark spent
- `POST /vtxos/cleanup` — Cleanup expired
- `POST /vtxos/settlement/process` — Trigger L1 settlement
- `GET /vtxos/settlement/status` — Settlement overview
- `POST /vtxos/monitor/start|stop` — Toggle monitors
- `GET /vtxos/monitor/status` — Monitor status
- `GET /vtxos/stats` — Detailed stats

### Lightning (core/lightning_manager.py, core/lightning_monitor.py)
- `POST /lightning/lift` — Generate invoice to lift into L2
- `POST /lightning/land` — Prepare land (off-ramp)
- `GET /lightning/invoices/<payment_hash>` — Invoice status
- `POST /lightning/pay/<payment_hash>` — Pay invoice (used for land)
- `GET /lightning/balances` — Lightning + on-chain balances
- `GET /lightning/channels` — List channels
- `GET /lightning/fees/estimate/<amount_sats>` — Fee estimate
- `GET /lightning/activity/<user_pubkey>` — User activity
- `GET /lightning/statistics` — Aggregate stats
- `GET /lightning/monitor/health` — Monitor health
- `GET /lightning/invoices` — List invoices
- `GET /lightning/payments` — List payments

### Monitoring and Cache (core/monitoring.py, core/cache_manager.py)
- `GET /monitoring/stats` — Cache/DB/memory stats
- `GET /monitoring/alerts` — Active alerts
- `GET /monitoring/cache/stats` — Cache stats
- `GET /health/comprehensive` — Comprehensive health (if monitoring started)

### Admin API (core/admin_api.py)
All endpoints require `X-Admin-Key: <ADMIN_API_KEY>` or `?admin_key=`
- `GET /admin/health/comprehensive`
- `GET /admin/metrics/system?hours=24`
- `GET /admin/alerts`
- `GET /admin/alerts/rules`
- `POST /admin/alerts/rules/<rule_name>/toggle` (body: `{ "enabled": true|false }`)
- `GET /admin/jobs/statistics?hours=24`
- `GET /admin/services/status`
- `GET /admin/database/stats`
- `GET /admin/system/info`
- `GET /admin/configuration`
- `GET /admin/logs/recent?limit=100&level=<status>`
- `POST /admin/maintenance/cleanup` (body: `{ "days": 30, "dry_run": true }`)
- `POST /admin/backup/create` (MySQL/MariaDB only)
- `POST /admin/performance/profile` (body: `{ "duration": 60 }`)
- `POST /admin/restart/service` (dev stub)
- `GET /admin/dashboard/summary`

---

## Core Modules and How to Use Them

### Session Manager — `core/session_manager.py`
Manages signing sessions and state transitions.

- Create a session: `SigningSessionManager.create_session(user_pubkey, session_type, intent_data)`
- Create challenge: `create_challenge(session_id, challenge_data, context)`
- Validate response: `validate_challenge_response(session_id, signature)`
- Update state: `update_session_status(session_id, new_status)`
- Cleanup: `cleanup_expired_sessions()`

State transition rules are enforced. Aliases are supported for backwards-compatibility (e.g., `pending` -> `initiated`, `response_received` -> `awaiting_signature`).

### Challenge Manager — `core/challenge_manager.py`
Creates challenge payloads, persists them, validates user signatures, and supplies human-readable context for wallet UX.

- `generate_challenge(session_id, context_data)`
- `create_and_store_challenge(session_id, context_data)`
- `validate_challenge_response(session_id, signature, user_pubkey)`
- `get_challenge_context(session_id)`
- `cleanup_expired_challenges()`

### Signing Orchestrator — `core/signing_orchestrator.py`
Coordinates the 6-step ceremony for Ark transactions and Lightning operations.

- Start: `start_signing_ceremony(session_id)`
- Step: `execute_signing_step(session_id, SigningStep, signature_data=None)`
- Status: `get_ceremony_status(session_id)`
- Cancel: `cancel_ceremony(session_id, reason="...")`

Internally depends on `core/transaction_processor.py` and the gRPC clients.

### Transaction Processor — `core/transaction_processor.py`
Implements P2P transfers end-to-end and utility operations.

- `process_p2p_transfer(session_id)`
- `broadcast_transaction(txid)`
- `get_transaction_status(txid)`
- `get_user_transactions(user_pubkey, ...)`
- `confirm_transaction(txid, confirmations=1)`

Raises precise exceptions (e.g., `InsufficientFundsError`, `InvalidTransactionError`) for actionable error handling.

### Asset Manager — `core/asset_manager.py`
CRUD for assets and balances, plus VTXO utilities.

- Assets: `create_asset`, `get_asset_info`, `list_assets`, `get_asset_stats`, `get_reserve_requirements`
- Balances: `get_user_balance`, `get_user_balances`, `mint_assets`, `transfer_assets`
- VTXOs: `manage_vtxos(action=list|create|assign|spend)`, `cleanup_expired_vtxos`

### VTXO Manager — `core/vtxo_manager.py`
Inventory monitoring, batch creation, assignment, settlement.

- Inventory monitor: `VtxoInventoryMonitor.start_monitoring()`
- Batch ops: `create_vtxo_batch(asset_id, count, amount_sats)`
- Assignment: `assign_vtxo_to_user(user_pubkey, asset_id, amount_needed)`
- Settlement: `process_hourly_settlement()`, `create_commitment_transaction(...)`, `broadcast_settlement_transaction(...)`

### Lightning — `core/lightning_manager.py` & `core/lightning_monitor.py`
High-level Lightning ops via LND client. Robust error handling in `core/lightning_errors.py`.

- Lift (on-ramp): `create_lightning_lift(LightningLiftRequest)` → returns BOLT11 invoice
- Land (off-ramp): `process_lightning_land(LightningLandRequest)` → registers invoice
- Pay: `pay_lightning_invoice(payment_hash)`
- Inspect: `get_lightning_balances()`, `get_user_lightning_activity(user_pubkey)`
- Monitor: `LightningMonitor.start_monitoring()`, stats and health checks

### gRPC Client Layer — `grpc_clients/`
Unified access to ARKD/TAPD/LND.

- Get manager: `from grpc_clients import get_grpc_manager, ServiceType`
- Get client: `client = get_grpc_manager().get_client(ServiceType.ARKD)`
- See method reference in `grpc_clients/README.md`

### Nostr — `nostr_clients/`
Provides Nostr connectivity, handlers, Redis pub/sub workers.

- Initialize: `initialize_nostr_client()`, `initialize_redis_manager()`, `initialize_event_handler()` (wrapped by `/nostr/start`)
- Workers: `nostr_workers.py` handle action intents and signing responses via Redis channels

### Monitoring & Performance — `core/monitoring.py`, `core/cache_manager.py`
- Start/Stop monitoring: `initialize_monitoring()`, `shutdown_monitoring()`
- Alerting rules, Prometheus metrics, health checks
- Redis cache and in-memory hot cache with decorators to cache function/database results

---

## Typical Workflows (HTTP Examples)

### 1) P2P Transfer (dev/HTTP path)

- Create session
  ```bash
  curl -s -X POST :8000/sessions/create -H 'Content-Type: application/json' -d '{
    "user_pubkey": "<sender_pubkey>",
    "session_type": "p2p_transfer",
    "intent_data": {"recipient_pubkey":"<recipient_pubkey>","amount":10000,"asset_id":"BTC"}
  }'
  ```
- Create challenge
  ```bash
  curl -s -X POST :8000/sessions/<SESSION_ID>/challenge
  ```
- Submit signature (hex)
  ```bash
  curl -s -X POST :8000/sessions/<SESSION_ID>/respond -H 'Content-Type: application/json' -d '{
    "signature": "<hex>",
    "user_pubkey": "<sender_pubkey>"
  }'
  ```
- Start signing ceremony (or use step-by-step API)
  ```bash
  curl -s -X POST :8000/signing/ceremony/start -H 'Content-Type: application/json' -d '{
    "session_id": "<SESSION_ID>"
  }'
  ```
- Poll ceremony status
  ```bash
  curl -s :8000/signing/ceremony/<SESSION_ID>/status
  ```
- (Optional) Prepare/broadcast via transaction endpoints
  ```bash
  curl -s -X POST :8000/transactions/p2p-transfer -H 'Content-Type: application/json' -d '{"session_id":"<SESSION_ID>"}'
  curl -s :8000/transactions/<TXID>/status
  curl -s -X POST :8000/transactions/<TXID>/broadcast
  ```

Notes
- The orchestrator path is primary. Transaction endpoints are available for lower-level/manual control.
- Session must be `awaiting_signature` to start the ceremony.

### 2) Lightning Lift (On-Ramp)

- Ensure Lightning services are running (auto-start via `LIGHTNING_AUTO_START=true` or call `initialize_lightning_services()` at startup).
- Request invoice
  ```bash
  curl -s -X POST :8000/lightning/lift -H 'Content-Type: application/json' -d '{
    "user_pubkey": "<npub>",
    "asset_id": "BTC",
    "amount_sats": 100000
  }'
  ```
- Pay the returned `bolt11_invoice` using your external Lightning wallet
- Track status
  ```bash
  curl -s :8000/lightning/invoices/<PAYMENT_HASH>
  ```
- On payment, `LightningMonitor` updates user balances accordingly

### 3) Lightning Land (Off-Ramp)

- Prepare land
  ```bash
  curl -s -X POST :8000/lightning/land -H 'Content-Type: application/json' -d '{
    "user_pubkey": "<npub>",
    "asset_id": "BTC",
    "amount_sats": 50000,
    "lightning_invoice": "lnbc..."
  }'
  ```
- When the underlying L2 transfer is authorized and executed, pay invoice
  ```bash
  curl -s -X POST :8000/lightning/pay/<PAYMENT_HASH>
  ```

### 4) Asset & Balance Ops

- Create asset
  ```bash
  curl -s -X POST :8000/assets -H 'Content-Type: application/json' -d '{
    "asset_id":"gBTC","name":"Gateway BTC","ticker":"gBTC","total_supply":0
  }'
  ```
- Mint to a user
  ```bash
  curl -s -X POST :8000/assets/gBTC/mint -H 'Content-Type: application/json' -d '{
    "user_pubkey": "<npub>", "amount": 250000
  }'
  ```
- Transfer between users
  ```bash
  curl -s -X POST :8000/assets/transfer -H 'Content-Type: application/json' -d '{
    "sender_pubkey":"<A>","recipient_pubkey":"<B>","asset_id":"gBTC","amount":10000
  }'
  ```
- Balances
  ```bash
  curl -s :8000/balances/<npub>
  curl -s :8000/balances/<npub>/gBTC
  ```

### 5) VTXO Lifecycle

- Create batch of VTXOs
  ```bash
  curl -s -X POST :8000/vtxos/batch/create -H 'Content-Type: application/json' -d '{
    "asset_id":"gBTC","count":100,"amount_sats":100000
  }'
  ```
- Assign to user
  ```bash
  curl -s -X POST :8000/vtxos/assign -H 'Content-Type: application/json' -d '{
    "user_pubkey":"<npub>","asset_id":"gBTC","amount_needed":100000
  }'
  ```
- Cleanup expired
  ```bash
  curl -s -X POST :8000/vtxos/cleanup
  ```

---

## Background Tasks (core/tasks.py)

- Enqueue demo
  ```bash
  curl -s :8000/enqueue-demo
  ```
- Enqueue user process
  ```bash
  curl -s -X POST :8000/enqueue-user-process -H 'Content-Type: application/json' -d '{
    "user_id":"12345","action_type":"process","data":{"key":"value"}
  }'
  ```
- Periodic maintenance jobs run via the scheduler and can be monitored with `/queue-status` and `/stats`.

---

## gRPC Clients (grpc_clients/)

Use `get_grpc_manager()` to retrieve clients for ARKD, TAPD, and LND. See full method list in `grpc_clients/README.md`.

```python
from grpc_clients import get_grpc_manager, ServiceType

mgr = get_grpc_manager()
lnd = mgr.get_client(ServiceType.LND)
balances = lnd.get_total_balance()
```

---

## Monitoring, Metrics, and Admin

- Start monitoring automatically via `MONITORING_AUTO_START=true` (default) or programmatically using `initialize_monitoring()` in `app.py` (`initialize_services()` bootstraps it by default).
- Prometheus exporter runs on `METRICS_PORT` (default 8080). See counters/gauges in `core/monitoring.py`.
- Use `/admin/*` endpoints with `X-Admin-Key` to access deep operational insights, alerts, backups, and profiles.

---

## Security Notes

- Never commit real credentials or Nostr private keys.
- Configure `ADMIN_API_KEY` and protect `/admin/*` behind network policies and auth proxies in production.
- TLS and macaroon paths for daemons are provided via env vars; ensure proper file permissions.

---

## Troubleshooting

- Basic checks
  - `GET /ready` and `GET /health`
  - `GET /grpc/arkd/info`, `/grpc/tapd/balances`, `/grpc/lnd/balances`
  - `GET /nostr/status`
  - `GET /queue-status`
- Logs
  - App logs under `logs/` (structured JSON via `core/monitoring.py`)
  - Database status via `/admin/database/stats`
- Common errors
  - Session state errors: ensure session is in `awaiting_signature` before starting ceremony
  - Insufficient balance: verify `AssetBalance` and reserved amounts
  - gRPC unavailability: use `/grpc/reconnect/<service>` and verify env paths

---

## Development

- Run tests
  ```bash
  uv run pytest -q
  ```
- Lint/type-check (if configured)
  ```bash
  flake8 .
  mypy .
  ```

---

## Appendix: Where Things Live

- HTTP API: `app.py`
- Admin API: `core/admin_api.py`
- Assets & VTXOs: `core/asset_manager.py`, `core/vtxo_manager.py`
- Signing: `core/session_manager.py`, `core/challenge_manager.py`, `core/signing_orchestrator.py`
- Transactions: `core/transaction_processor.py`
- Monitoring & Cache: `core/monitoring.py`, `core/cache_manager.py`
- Lightning: `core/lightning_manager.py`, `core/lightning_monitor.py`
- Tasks: `core/tasks.py`
- Models: `core/models.py`
- gRPC clients: `grpc_clients/`
- Nostr clients: `nostr_clients/`

If you’d like SDK-style wrappers or Postman collections for this API, open an issue and we’ll add them.
