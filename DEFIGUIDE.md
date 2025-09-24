# ArkRelay DeFi Developers Guide

This guide shows how to build DeFi protocols on top of ArkRelay’s financial primitives. It maps ArkRelay components to common DeFi building blocks and provides two concrete scenarios:

- Aave-like lending/borrowing market
- Uniswap-like AMM with liquidity pools and swaps

Use this together with:
- `USERGUIDE.md` for HTTP endpoints and module references
- `NOSTRGUIDE.md` for the Nostr intent + challenge/response flow

---

## 1) ArkRelay Financial Primitives (What you build on)

- **Assets & Balances** (`core/models.py`, `core/asset_manager.py`)
  - `Asset` is a fungible token entry (e.g., BTC, gBTC, LP-FOO-BAR).
  - `AssetBalance` tracks a user’s asset balance and reserved amounts.
  - HTTP endpoints under “Asset Management” in `USERGUIDE.md` cover CRUD, minting, transfers, stats.

- **VTXO Lifecycle** (`core/vtxo_manager.py`)
  - Inventory, assignment, expiration, and L1 settlement of virtual UTXOs.
  - Useful as a settlement and accounting substrate for protocol actions.

- **Sessions & Signing** (`core/session_manager.py`, `core/challenge_manager.py`, `core/signing_orchestrator.py`)
  - Protocol actions should be authorized via Nostr events:
    - Intent (kind 31510) → Relay Challenge (31511) → Client Response (31512).
  - The signing orchestrator coordinates multi-step transactions and status.

- **Lightning On/Off Ramp** (`core/lightning_manager.py`, `core/lightning_monitor.py`)
  - “Lift” (on-ramp) and “Land” (off-ramp) between L2 and Lightning.
  - Use to fund positions (deposits/liquidity) and withdraw to LN.

- **Async & Scheduling** (`core/tasks.py`, `core/scheduler.py`)
  - Redis Queue (RQ) for async jobs, and a scheduler for periodic tasks (interest accrual, TWAP, fee sweep, cleanup).

- **Monitoring & Admin** (`core/monitoring.py`, `core/admin_api.py`)
  - Prometheus metrics, alerts, health, and admin endpoints.

---

## 2) Development Pattern: Nostr is the API

- Users approve a single high-level action via a Nostr Intent (kind 31510) tagged to the gateway `npub`.
- The gateway conducts low-level signing via encrypted DMs (31511 challenges, 31512 responses).
- In production, treat Nostr as the primary API surface. Helper HTTP endpoints in `app.py` assist during development/testing.

Where to add your protocol logic:
- External Solver Service (separate microservice): expose your own API (e.g., `lend/*`, `amm/*`) and maintain protocol state and economics entirely outside the gateway.
- Nostr: have the solver subscribe/route `31510` intents by `type` (`lend:*`, `amm:*`). The gateway remains agnostic.
- Jobs: run interest accrual, liquidation keepers, TWAP, fee sweeping inside the solver (its own queue/scheduler).
- Gateway boundary: use the gateway only for signing sessions/challenges (31511/31512) and VTXO/transaction finalization. Avoid adding protocol endpoints or tables to the gateway.

---

## 3) Aave-like Lending & Borrowing

### 3.1 Suggested Data Model

Define these tables in your solver service database (not in the gateway). The gateway stores only sessions/challenges/VTXOs:

- `markets`
  - `asset_id`, `collateral_factor_bps`, `reserve_factor_bps`, `base_rate_bps`, `slope1_bps`, `slope2_bps`, `kink_utilization_bps`
- `positions`
  - `user_pubkey`, `asset_id`, `deposited`, `borrowed`, `last_accrual_ts`
- `liquidations`
  - `liquidator_pubkey`, `user_pubkey`, `asset_id`, `repaid`, `collateral_seized`, `timestamp`

Optional “tokenized accounting” with `Asset` entries:
- aToken (deposit receipt): `Asset(asset_id="aBTC", ticker="aBTC")`
- debtToken (optional): `Asset(asset_id="dBTC", ticker="dBTC")`

### 3.2 Rates, Health, and Oracles

- Utilization: `U = total_borrowed / total_deposits`.
- Borrow rate `r_borrow(U)`: piecewise-linear with `base`, `slope1` below `kink`, `slope2` above.
- Supply rate: `r_supply = r_borrow * U * (1 - reserve_factor)`.
- Health factor: `HF = (Σ deposit_i * price_i * collateral_factor_i) / (Σ borrow_j * price_j)`.
  - Liquidation threshold when `HF < 1` (tunable per market).
- Price oracle: feed prices into DB (periodic RQ job, or cached HTTP) with backoff and sanity checks.

### 3.3 Core Flows (Nostr + HTTP)

- Deposit
  - Intent 31510:
    ```json
    {
      "action_id": "...",
      "type": "lend:deposit",
      "asset_id": "gBTC",
      "amount": 250000,
      "expires_at": 1735689600
    }
    ```
  - Gateway creates a session, validates market, credits `AssetBalance` for user, optionally mints aToken (as an `Asset` transfer), emits 31340 on success.
  - If using Lightning on-ramp: call `POST /lightning/lift` first and finalize deposit upon invoice settlement.

- Borrow
  - Intent 31510:
    ```json
    {
      "action_id": "...",
      "type": "lend:borrow",
      "asset_id": "gBTC",
      "amount": 100000,
      "expires_at": 1735689600
    }
    ```
  - Accrue interest for the position (up to now), recompute HF, ensure sufficient collateral, increase `borrowed`, credit user balance.

- Repay
  - Intent 31510: `{ "type": "lend:repay", "asset_id": "gBTC", "amount": 100000, ... }`.
  - Debit user balance, reduce `borrowed` (after accruing), recompute HF.

- Withdraw
  - Intent 31510: `{ "type": "lend:withdraw", "asset_id": "gBTC", "amount": 50000, ... }`.
  - Simulate post-withdraw HF; allow only if `HF >= 1`.

- Liquidation
  - Keeper watches for `HF < 1` and submits `{ "type": "lend:liquidate", "user_pubkey": "<at-risk>", ... }`.
  - Repay portion of debt (plus incentive) and seize collateral per market rules.

### 3.4 Scheduling & Jobs

- `accrue_interest` (every minute/hour): update `positions` based on `delta_t` and current rates.
- `refresh_prices` (15–60s): update oracle prices and derived metrics.
- `liquidation_watcher` (5–10s): enqueue liquidations for undercollateralized positions.

### 3.5 External Solver Service Endpoints (dev/ops)

Expose endpoints in your solver service (not in the gateway) and back them with service-layer functions/jobs:
- `POST /defi/lend/deposit`
- `POST /defi/lend/withdraw`
- `POST /defi/lend/borrow`
- `POST /defi/lend/repay`
- `POST /defi/lend/liquidate`
- `GET  /defi/lend/markets`
- `GET  /defi/lend/positions/<user_pubkey>`

When signatures or VTXO settlement are required, use the gateway's signing sessions/orchestrator and finalization APIs; compute all protocol logic in the solver.

---

## 4) Uniswap-like AMM (x*y=k)

### 4.1 Suggested Data Model

Note: Define AMM/pool tables in your external solver service database (not in the gateway).

- `amm_pools`
  - `pool_id`, `asset_a`, `asset_b`, `reserve_a`, `reserve_b`, `fee_bps` (e.g., 30 = 0.3%), `last_twap_ts`
- `LP token` as `Asset`
  - `Asset(asset_id="LP-gBTC-gUSD", ticker="LP-gBTC-gUSD")`
  - LP balances tracked in `AssetBalance`.
- `swaps` (optional log)
  - `txid`, `pool_id`, `trader_pubkey`, `in_asset`, `in_amount`, `out_asset`, `out_amount`, `fee_amount`, `timestamp`

### 4.2 Math & Invariants

- Constant product: `(reserve_a + Δa) * (reserve_b - Δb) = k`.
- Fee-on-input: `amount_in_after_fee = amount_in * (1 - fee_bps/10000)`.
- Solve for output:
  - Given `Δa_in_after_fee`, `Δb_out = (reserve_b * Δa_in_after_fee) / (reserve_a + Δa_in_after_fee)`.
- Invariants:
  - `k` must not decrease due to swaps (accounting for fees).
  - Reserves must remain non-negative; enforce min liquidity.

### 4.3 Core Flows

- Add Liquidity
  - Intent 31510:
    ```json
    {
      "action_id": "...",
      "type": "amm:add_liquidity",
      "pool_id": "LP-gBTC-gUSD",
      "amount_a": 250000,
      "amount_b": 100000000,
      "expires_at": 1735689600
    }
    ```
  - Validate proportional deposit vs current reserves (or initialize pool if first LP).
  - Mint LP tokens pro-rata to contribution.

- Remove Liquidity
  - Intent 31510: `{ "type": "amm:remove_liquidity", "pool_id": "LP-gBTC-gUSD", "lp_amount": 1000, ... }`.
  - Burn LP tokens, return underlying `asset_a` and `asset_b` pro-rata.

- Swap
  - Intent 31510:
    ```json
    {
      "action_id": "...",
      "type": "amm:swap",
      "pool_id": "LP-gBTC-gUSD",
      "in_asset": "gBTC",
      "in_amount": 50000,
      "min_out_amount": 9800000,
      "expires_at": 1735689600
    }
    ```
  - Quote using current reserves, apply fee, validate slippage via `min_out_amount`, update reserves atomically, emit 31340 on success.

### 4.4 Pricing & Oracles

- TWAP: run a periodic job to compute and store TWAP from pool observations.
- External feeds: stitch with off-chain prices for health checks and cross-venue routing.

### 4.5 External Solver Service Endpoints (dev/ops)

- `POST /defi/amm/pools` (create/init)
- `GET  /defi/amm/pools`
- `GET  /defi/amm/pools/<pool_id>`
- `POST /defi/amm/add-liquidity`
- `POST /defi/amm/remove-liquidity`
- `POST /defi/amm/quote`
- `POST /defi/amm/swap`

Back these with solver-side jobs for pool ops. Use the gateway only for signing/VTXO settlement; authorization goes through Nostr intents/challenges.

---

## 5) End-to-End Flow Anatomy (applies to both scenarios)

1. Client publishes Nostr Intent (31510) with `type` matching your protocol action.
2. Gateway creates a `SigningSession` and issues one or more 31511 challenges over encrypted DMs.
3. Client verifies context and responds with 31512 signed payload(s).
4. Solver executes business logic (quotes, balances, reserves, positions) and, when ready, asks the gateway to finalize VTXOs/transactions after collecting signatures.
5. On success, the gateway finalizes and emits a 31340 confirmation event; the solver updates its own state and returns API status.
6. On errors, gateway sends 31341 DM with actionable error codes (see `NOSTRGUIDE.md`).

Use `/signing/ceremony/*` endpoints from `USERGUIDE.md` during development to step through and debug ceremony stages.

---

## 6) Integration Tips & Patterns

- **On/Off Ramp**: Use `POST /lightning/lift` to fund accounts; `POST /lightning/land` or `POST /lightning/pay/<hash>` for off-ramp.
- **Accounting**: Keep protocol-level state in your own tables; use `AssetBalance` and VTXOs for transfer/settlement.
- **Idempotency**: Include `action_id` in intents; store and reject duplicates.
- **Slippage & Safety**: Always include `min_out_amount` (or max slippage) on swaps.
- **Health & Metrics**: Expose protocol metrics via `core/monitoring.py` counters/gauges; surface them in `/admin/*`.
- **Keepers**: Implement off-chain bots for liquidations, TWAP, rebalancing; schedule via `core/scheduler.py`.
- **Testing**: Use `tests/` patterns and `pytest` to simulate sessions, intents, and edge cases.

---

## 7) Minimal Nostr Payload Reference (kinds)

- Intent (31510): top-level action. Must `p`-tag the gateway’s `npub` and include `expires_at` and `action_id`.
- Challenge (31511): gateway → wallet (encrypted DM). Contains `session_id`, `type`, `payload_to_sign`.
- Response (31512): wallet → gateway (encrypted DM). Contains `session_id`, `type`, `signature`.
- Confirmation (31340): public success event. Tags original intent and participants.
- Failure (31341): encrypted DM with failure details and code.

See `NOSTRGUIDE.md` for detailed examples and the security checklist.

---

## 8) Security Checklist

- Validate that low-level challenge payloads match the high-level intent (amounts, asset, recipient/pool).
- Enforce time bounds using `expires_at` and session expiration.
- Enforce per-user and per-session rate limits, especially on `/admin/*` (already proxied+keyed).
- Do not log plaintext DM contents; scrub secrets and signatures.
- Use TLS (reverse proxy included in `docker-compose.yml`) and rotate `ADMIN_API_KEY`.

---

## 9) Where to Build (Separation of Concerns)

- Gateway (this repo): keep it minimal — sessions/challenges (31511/31512), VTXO/transaction finalization, health/ops. Do not add DeFi endpoints or protocol tables.
- Solver (your service): implement protocol APIs (`lend/*`, `amm/*`), Nostr 31510 routing, protocol data models (`markets`, `positions`, `amm_pools`, ...), jobs/schedulers, and metrics.
- Integration: solver talks to gateway via Nostr (authorization) and minimal helper endpoints to request signing/settlement; gateway remains protocol-agnostic.

---

## 10) Example: Putting It Together

- User adds liquidity:
  1) Client publishes 31510 `{ "type": "amm:add_liquidity", ... }`.
  2) Gateway challenges (31511) to authorize spending; client responds (31512).
  3) Solver updates pool reserves and LP accounting in its own DB. Gateway finalizes VTXOs and emits 31340.

- User borrows:
  1) Client publishes 31510 `{ "type": "lend:borrow", ... }`.
  2) Solver accrues interest, checks HF, then orchestrates signatures via gateway challenges if needed.
  3) Solver updates positions and transfers via gateway-settled VTXOs; gateway emits 31340 upon finalization.

---

If you’d like scaffold code for `defi_bp` (HTTP) and an example Nostr router for `31510` types, let us know and we’ll add them as templates to `core/`.
