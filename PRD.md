# Product Requirement Document: Ark Relay V1

**Version:** 1.0
**Date:** October 27, 2023
**Status:** Final for V1 Development

## 1. Introduction

### 1.1. Vision
To create the foundational infrastructure for a new DeFi ecosystem on Bitcoin. The Ark Relay will be a high-performance, non-custodial L2 settlement layer that enables cheap, fast, and safe programmable finance. It will be the "plumbing" that allows developers to build advanced financial applications that are accessible to any user with a standard Bitcoin Lightning wallet and a Nostr client.

### 1.2. Product Objective (V1)
The primary objective for V1 is to launch a production-scale L2 relay that is technically sound, reliable, and capable of demonstrating the core value proposition of the Ark protocol with Taproot Assets. Success for V1 is defined as a fully functioning system that can process atomic L2 state changes according to this specification, with a clear path for developers to build on top of it.

### 1.3. Target Audience
- **Primary:** DeFi developers and projects (DEXs, lending protocols, etc.) seeking a scalable, low-cost, self-custodial infrastructure for their applications.
- **Secondary:** End-users of those DeFi projects, who will interact with the gateway indirectly via their wallets and dApps. Our goal is to provide an infrastructure so seamless that these users are unaware of its complexity.

### 1.4. Unique Value Proposition
Ark Relay is an L2 service that is **fast** (sub-second soft finality), **cheap** (near-zero fees), and **self-custodial** (user funds are secured by the Bitcoin L1). It works out-of-the-box with the existing Bitcoin, Lightning, and Nostr ecosystems, requiring no new base-layer changes.

## 2. Core Principles

This PRD and all development work shall adhere to the following core principles:

- **The Relay is a "Smart Orchestrator" with a Simple Interface:** The relay's core responsibility is to abstract away the complexity of the underlying `arkd` protocol. It will manage the entire interactive, multi-step signing ceremony on behalf of clients, presenting a simple, high-level, intent-based interface to the ecosystem. Its internal logic is complex, but its external API is simple.
- **Nostr is the API:** All state-changing actions are initiated via signed Nostr events. The gateway is a service that listens and responds on the open Nostr network. There are no proprietary, state-changing HTTP endpoints.
- **Self-Custody is Paramount:** The system is built on the Ark protocol's guarantee of a unilateral exit. The user is always in control of their assets. The gateway is a trusted *facilitator* for liveness, not a *custodian*.
- **The Client is the Source of Truth:** The user's wallet is responsible for maintaining its own state and history. The gateway provides tools for synchronization but does not act as a permanent, user-specific ledger.

## 3. System Architecture Overview

The Ark Relay is a full-stack Flask application that acts as an orchestration layer on top of several backend daemons.

### 3.1. Application Layer (Flask)
The core product. It consists of:
- A **Nostr Bot Service** using `pynostr` library for ingesting user intents and publishing responses.
- **Asynchronous Task Workers** for processing state changes using **Redis Queue** for Python with Redis pub/sub for real-time event processing.
- A minimal **Flask Web App** for read-only helper endpoints.
- A **unified gRPC Client Layer** (`grpc_client.py`) for communicating with `arkd`, `tapd`, and `lnd` daemons.
- A **MariaDB Database** for storing application-level state (the "color" of VTXOs).
- A **Redis Cache** for session management, performance optimization, and as the message broker for RQ.

### 3.2. Protocol Layer (Backend Daemons)
- `arkd`: Manages the Ark VTXO lifecycle and on-chain settlement.
- `tapd`: Manages Taproot Asset issuance and proof validation.
- `litd` (`lnd`): Manages the on-chain hot wallet, Lightning channels, and Lightning on/off-ramps.
- `bitcoind`: The connection to the Bitcoin blockchain.

### 3.3. Development Environment
- **Testing Framework**: Uses Nigiri for local Bitcoin/Lightning testnet environment
- **Asset Management**: Tracks local LND balances and UTXO L1 holdings managed by LND
- **Integration**: All daemons run in Docker containers with pre-configured testnet setup

## 4. Functional Requirements: The Nostr Protocol

The gateway's primary interface is defined by the following Nostr events. The gateway MUST listen for events `p`-tagged with its own Nostr public key.

### 4.1. Events Processed by the Relay

#### 4.1.1. `kind: 31510` - High-Level Action Intent
- **Who Publishes:** User Wallets and dApp Backends.
- **When:** To initiate any state-changing action (transfer, swap, etc.).
- **What it Represents:** A **single, signed authorization** for the gateway to begin and manage a complete, multi-step transaction on the user's behalf.
- **`content` JSON Schema:**
  ```json
  {
    "action_id": "<client_generated_uuid>", // To prevent replays
    "type": "p2p_transfer" | "atomic_swap" | "add_liquidity" | ...,
    // ... action-specific details ...
    "my_leg": { /* details of what I'm sending */ },
    "counterparty_leg": { /* details of what I expect in return */ },
    "expires_at": <unix_timestamp>
  }
  ```
- **Relay's Action:** Upon receiving a valid `kind: 31510`, the relay creates a new "job" in its database and begins the orchestration process.

#### 4.1.2. Communication Protocol & Wallet Compatibility
All interactive and sensitive communication (Service Requests, Service Responses, Failure Notices) between wallets and the gateway **MUST** use **Nostr NIP-04 Encrypted Direct Messages.** This ensures user privacy and protects against replay attacks on the request-response cycle.

It is a core requirement that this communication model be compatible with standard, general-purpose Nostr wallets. Wallet signing will be handled via browser extensions that support **NIP-07 (`window.nostr.signEvent(...)`)** for signing public events and **NIP-44/04 (`window.nostr.encrypt(...)` / `decrypt(...)`)** for handling encrypted DMs.

**This design explicitly targets compatibility with existing, popular wallets such as Alby, OKX Wallet (with Nostr support), and others that adhere to these widely adopted NIPs.** The dApps built on this gateway will be responsible for calling these standard browser extension functions, ensuring users do not need a specialized wallet.

### 4.2. Events Published by the Relay

#### 4.2.1. `kind: 31511` - Relay Signing Challenge (Encrypted DM)
- **Purpose:** To request a specific, low-level signature from a client wallet as part of the `arkd` dance.
- **Publication:** As an encrypted DM (NIP-04) to the user's `npub`.
- **Structure:**
  - **Tags:** MUST `e`-tag the original `kind: 31510` intent to provide context.
  - **Content:** `{ "session_id": "...", "type": "sign_ark_tx" | "sign_checkpoint_txs", "payload_to_sign": "...", "human_readable_context": "Step 1/2: Authorize transfer..." }`

#### 4.2.2. `kind: 31512` - Client Signing Response (Encrypted DM)
- **Purpose:** The event a client wallet publishes to send a requested signature back to the gateway. (While the gateway *processes* this, the NIP defines it for wallet developers).

#### 4.2.3. `kind: 31340` - Final Transaction Confirmation (Public)
- **Purpose:** The final, public confirmation that the entire multi-step action is complete.
- **Structure:** Unchanged, but it now `e`-tags the high-level `kind: 31510` intent, not the low-level ones.
- **Publication:** Publicly, to all subscribed relays.
- **Structure:**
  - **Tags:** MUST `e`-tag all `kind: 31510` event IDs that were part of the processed batch. MUST `p`-tag all user `pubkey`s that received a new VTXO.
  - **Content:** A detailed breakdown of spent VTXOs and the newly created VTXOs, including their IDs, owners, and asset details.

#### 4.2.4. `kind: 31341` - Transaction Failure Notice
- **Purpose:** To provide clear, machine-readable error feedback.
- **Publication:** As an encrypted DM (NIP-04) to the `pubkey` of the intent's original author.
- **Structure:**
  - **Tags:** MUST `e`-tag the failed `kind: 31510` event ID.
  - **Content:** `{ "status": "failure", "code": <integer>, "message": "<string>" }`. A standardized list of error codes shall be maintained (see Section 8).

#### 4.2.5. `kind: 31342` - L1 Commitment Notice
- **Purpose:** The "hard finality" proof. A public announcement of L1 settlement.
- **Publication:** Publicly.
- **Structure:**
  - **Content:** `{ "l1_txid": "...", "block_height": ..., "merkle_root_of_l2_txs": "..." }`

## 5. Functional Requirements: Core Workflows

### 5.1. P2P Transfer
1. **User Wallet:** Publishes one signed `kind: 31510` intent with `type: "p2p_transfer"`.
2. **Relay:** Receives the intent and initiates an interactive signing session with the user's wallet via `kind: 31511` DMs.
3. **User Wallet:** Automatically responds to the signing challenges within the authorized session.
4. **Relay:** Completes the internal `arkd` dance and publishes the final `kind: 31340` confirmation.

### 5.2. Atomic Swap
1. **User Wallet:** Publishes its signed `kind: 31510` intent to the **DEX Server**.
2. **DEX Server:** Arranges the swap and publishes its own corresponding `kind: 31510` intent.
3. **DEX Server:** Submits both `kind: 31510` intents to the gateway in a single batch request (e.g., via a `submit_batch` DM).
4. **Relay:** Receives the batch. It now initiates **two parallel interactive signing sessions**, one with the user's wallet and one with the DEX server's Nostr key, guiding them both through the `arkd` dance.
5. **Relay:** Once all signatures from all parties are collected, it finalizes the transaction and publishes a single confirmation for the entire atomic swap.

### 5.3. Lightning Lift (On-Ramp)
1. **User Wallet:** Sends a `kind: 31500` ("Service Request") DM to the gateway: `{ "action": "lift_lightning", "asset_id": "...", "amount": ... }`.
2. **Relay:** Responds with a `kind: 31501` ("Service Response") DM containing a unique Taproot Asset Lightning Invoice.
3. **User Wallet:** Pays the invoice.
4. **Relay:** Upon successful payment, activates the VTXO and publishes a `kind: 31340` confirmation.

### 5.4. Lightning Land (Off-Ramp)
1. **User Wallet:** Generates a Taproot Asset Lightning Invoice for the desired withdrawal amount.
2. **User Wallet:** Publishes a single `kind: 31510` intent that transfers the VTXO to the gateway's own pubkey. The `memo` field of the `content` MUST contain the Lightning invoice.
3. **Relay:** Receives the VTXO transfer authorization. It parses the invoice from the `memo`.
4. **Relay:** Pays the Lightning invoice. Upon successful payment, it processes the VTXO transfer, effectively taking ownership of the spent VTXO.

### 5.5. State Synchronization
1. **User Wallet:** When a user restores their wallet or comes online after a long period, it shall send a `kind: 31500` DM to the gateway: `{ "action": "sync_state" }`.
2. **Relay:** Shall respond with a `kind: 31501` DM containing a complete list of the user's current unspent VTXOs and their associated asset "color" data.

## 6. Fee Model (V1)

- **L2 Transfers:** A fixed fee of **10 satoshis** (or equivalent in the transacted asset) per intent within a batch. The fee MUST be paid in the gateway's native `gBTC` asset.
- **Lightning Lifts:** **Free** (Operator absorbs the on-chain pre-provisioning cost).
- **Lightning Lands:** A fee of **0.1%** of the value being withdrawn, charged in the asset being landed.
- **Mechanism:** All fees must be paid as an explicit `output` in the user's signed `kind: 31510` intent. The gateway will reject intents where the fee output is missing or incorrect.

## 7. Asset Support (V1)

- **Relay-Issued Asset (`gBTC`):** The relay shall issue its own wrapped Bitcoin as a Taproot Asset. This will be the primary asset for fee payments. The relay must maintain a 1:1 reserve of BTC for all circulating `gBTC`.
- **Permissionless Assets:** The gateway will be permissionless. It will process any valid Taproot Asset that is "lifted" into the system via its Lightning node. The user is responsible for providing the necessary asset proofs to the gateway upon the first lift of a new asset type.

## 8. Error Handling

The gateway shall provide a clear, machine-readable list of error codes in its documentation, communicated via the `code` field in the `kind: 31341` failure notice. Examples include:
- `1001`: Invalid Nostr Signature
- `2001`: Insufficient VTXO Balance
- `2002`: Input VTXO Already Spent
- `3001`: Atomic Batch Validation Failed (Inconsistent Witness)
- `4001`: Fee Output Missing or Incorrect

## 9. Out of Scope for V1

- **HTTP API for State Changes:** All writes MUST be via Nostr.
- **On-Chain Lifts/Lands:** V1 is Lightning-only.
- **Advanced Witness Types:** V1 only supports `atomic_group`. HTLCs and other types are for future versions.
- **Official SDKs:** The focus is on excellent documentation and tutorials for existing Nostr libraries.

## 10. Technical Implementation Details

### 10.1. Signing Ceremony Design

The interactive signing ceremony is the core orchestration challenge. The gateway must manage multi-step signing processes with user wallets while maintaining security and user experience.

#### 10.1.1. Session Management
- **Session Lifecycle**: Each `kind: 31510` intent creates a signing session with:
  - `session_id`: Unique identifier derived from intent event ID
  - `user_pubkey`: Nostr public key of the user
  - `status`: `pending`, `active`, `completed`, `failed`
  - `created_at`, `expires_at`: Session validity window (typically 15 minutes)
  - `steps_completed`: Array of completed signing steps
  - `current_step`: Current signing step identifier

#### 10.1.2. Signing Steps
1. **Intent Verification**: Verify `kind: 31510` signature and validate intent structure
2. **ARK Transaction Preparation**: Prepare `ark_tx` data for user signature
3. **Checkpoint Transaction Preparation**: Prepare `checkpoint_txs` data for user signature
4. **Signature Collection**: Collect encrypted `kind: 31512` responses
5. **Ark Protocol Execution**: Submit collected signatures to `arkd`
6. **Finalization**: Publish `kind: 31340` confirmation

#### 10.1.3. State Machine
```python
class SigningSession:
    states = [
        'intent_received',
        'ark_tx_prepared',
        'checkpoint_txs_prepared',
        'signatures_collected',
        'ark_executed',
        'completed'
    ]

    def transition_to(self, new_state, data):
        # Validate state transition
        # Update session state
        # Notify user wallet via encrypted DM
        # Set timeout for next step
```

### 10.2. Key Management Strategy

#### 10.2.1. Gateway Keys
- **Nostr Identity**: Single Nostr key pair for gateway identity
- **Storage**: Private key encrypted at rest using AES-256-GCM with key derived from environment variable
- **Access**: Private key only loaded into memory at startup, never logged or persisted
- **Rotation**: Built-in support for key rotation with graceful transition period

#### 10.2.2. Security Measures
- **Environment Variables**: `GATEWAY_NOSTR_PRIVATE_KEY` (encrypted), `GATEWAY_ENCRYPTION_KEY`
- **Memory Protection**: Private key stored in memory as bytearray, zeroed after use
- **Audit Trail**: All signing operations logged without exposing sensitive data
- **Backup Strategy**: Encrypted backup of private key with distributed recovery

#### 10.2.3. Key Derivation
```python
def load_gateway_keys():
    encrypted_key = os.getenv('GATEWAY_NOSTR_PRIVATE_KEY')
    encryption_key = os.getenv('GATEWAY_ENCRYPTION_KEY')

    # Decrypt private key
    private_key = decrypt_aes256_gcm(encrypted_key, encryption_key)

    # Convert to Nostr key object
    return PrivateKey.from_hex(private_key)
```

### 10.3. VTXO Pre-Provisioning Implementation

#### 10.3.1. Hot Inventory Management
- **Database Table**: `vtxo_inventory` tracks available VTXOs
- **Monitoring**: Real-time monitoring via Redis pub/sub channel `inventory:updates`
- **Thresholds**:
  - **Critical**: < 1,000 VTXOs (immediate replenishment)
  - **Warning**: < 3,000 VTXOs (schedule replenishment)
  - **Target**: 10,000 VTXOs
- **Batch Creation**: Create VTXOs in batches of 1,000 to optimize on-chain fees

#### 10.3.2. Replenishment Process
1. **Monitor**: Background task checks inventory levels every 5 minutes
2. **Fee Analysis**: Check current mempool fee rates
3. **Decision Making**: Trigger replenishment if:
   - Inventory below critical level, OR
   - Inventory below warning level AND fees are low (< 10 sat/vB)
4. **Execution**:
   - Call `arkd.CreateVtxos(batch_size=1000)`
   - Wait for on-chain confirmation
   - Update inventory database
5. **Notification**: Publish inventory update to Redis pub/sub

#### 10.3.3. Cost Optimization
- **Fee Estimation**: Use multiple fee estimators (mempool.space, lnd estimates)
- **Timing**: Schedule large replenishments during weekend low-fee periods
- **Batch Size**: Dynamic batch sizing based on current fee environment

### 10.4. L1 Settlement Process Design

#### 10.4.1. Settlement Coordinator
- **Trigger**: Hourly scheduled task with `cron: 0 * * * *`
- **State Gathering**: Query `arkd` for all settled transactions since last settlement
- **Merkle Tree Construction**: Build Merkle tree of all L2 state changes
- **Commitment Transaction**: Create and broadcast L1 commitment transaction

#### 10.4.2. Settlement Workflow
```python
def l1_settlement_task():
    # 1. Get latest L2 state changes
    l2_changes = arkd_client.get_state_changes(since_last_settlement)

    # 2. Build Merkle tree
    merkle_root = build_merkle_tree(l2_changes)

    # 3. Create commitment transaction
    commitment_tx = arkd_client.create_commitment_tx(merkle_root)

    # 4. Broadcast transaction
    txid = bitcoind_client.sendrawtransaction(commitment_tx)

    # 5. Update database and publish notice
    publish_l1_commitment_notice(txid, merkle_root)
```

#### 10.4.3. Failure Handling
- **Transaction Failure**: Retry with higher fees, exponential backoff
- **Ark Daemon Unavailable**: Queue settlement for next run, alert operators
- **Network Issues**: Monitor transaction mempool status, rebroadcast if needed

### 10.5. Error Handling Strategy

#### 10.5.1. Daemon Connection Errors
- **Retry Strategy**: Exponential backoff starting at 1s, max 30s
- **Circuit Breaker**: Open circuit after 5 consecutive failures, reset after 60s
- **Health Checks**: Continuous background health monitoring of all daemons
- **Graceful Degradation**: Read-only mode when critical daemons unavailable

#### 10.5.2. Transaction Processing Errors
- **Intent Validation**: Reject malformed intents immediately with specific error codes
- **Signature Verification**: Detailed error messages for signature validation failures
- **Ark Protocol Errors**: Map `arkd` error codes to Nostr failure notices
- **Timeout Handling**: Session timeouts for all signing steps with user notification

#### 10.5.3. Database Errors
- **Connection Pooling**: Configurable connection pool with automatic reconnection
- **Transaction Rollback**: Automatic rollback on errors during multi-step operations
- **Deadlock Handling**: Automatic retry for deadlock scenarios
- **Backup Connections**: Support for read replicas during primary database issues

#### 10.5.4. Monitoring and Alerting
- **Error Tracking**: Error rate monitoring with alerting on thresholds
- **Performance Metrics**: Transaction processing time monitoring
- **Resource Monitoring**: CPU, memory, disk usage alerting
- **Business Metrics**: Failed transaction rates, settlement success rates

### 10.6. Database Schema Design

#### 10.6.1. VTXO State Tracking
```sql
CREATE TABLE vtxos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vtxo_id VARCHAR(64) UNIQUE NOT NULL,  -- Ark VTXO identifier
    owner_pubkey VARCHAR(64) NOT NULL,     -- Nostr pubkey of owner
    asset_id VARCHAR(64) NOT NULL,        -- Taproot Asset ID
    amount BIGINT NOT NULL,               -- Asset amount (satoshis)
    status ENUM('available', 'assigned', 'spent', 'expired') NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    assigned_at DATETIME,                 -- When assigned to user
    spent_at DATETIME,                    -- When spent
    expires_at DATETIME,                  -- VTXO expiration time
    tx_id VARCHAR(64),                    -- Bitcoin transaction ID
    proof_data TEXT,                      -- Taproot Asset proof data
    metadata JSON                         -- Additional VTXO metadata
);
```

#### 10.6.2. Asset Management
```sql
CREATE TABLE assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id VARCHAR(64) UNIQUE NOT NULL,  -- Taproot Asset ID
    name VARCHAR(100) NOT NULL,           -- Human-readable name
    ticker VARCHAR(20) NOT NULL,          -- Asset ticker (e.g., gBTC)
    asset_type ENUM('relay_issued', 'permissionless') NOT NULL,
    total_supply BIGINT DEFAULT 0,        -- Total circulating supply
    reserve_amount BIGINT DEFAULT 0,      -- BTC reserve for relay-issued assets
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    enabled BOOLEAN DEFAULT TRUE,         -- Asset enabled for operations
    metadata JSON                         -- Asset metadata (proof requirements, etc.)
);

CREATE TABLE asset_balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id VARCHAR(64) NOT NULL,
    lnd_balance BIGINT DEFAULT 0,        -- Balance in LND channels
    utxo_balance BIGINT DEFAULT 0,        -- Balance in on-chain UTXOs
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
);
```

#### 10.6.3. Session Management
```sql
CREATE TABLE signing_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id VARCHAR(64) UNIQUE NOT NULL,
    user_pubkey VARCHAR(64) NOT NULL,
    intent_event_id VARCHAR(64) NOT NULL,  -- Original kind:31510 event ID
    status ENUM('pending', 'active', 'completed', 'failed', 'expired') NOT NULL,
    current_step VARCHAR(50),               -- Current signing step
    steps_completed JSON,                  -- Array of completed steps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,           -- Session expiration
    completed_at DATETIME,                 -- When session completed
    error_code INTEGER,                    -- Error code if failed
    error_message TEXT,                    -- Error message if failed
    session_data JSON                      -- Session-specific data
);

CREATE TABLE signing_challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id VARCHAR(64) NOT NULL,
    challenge_type VARCHAR(50) NOT NULL,   -- 'ark_tx', 'checkpoint_txs', etc.
    challenge_data TEXT NOT NULL,           -- Challenge data to sign
    human_readable TEXT,                    -- Human-readable description
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    responded_at DATETIME,                  -- When user responded
    signature_response TEXT,                -- User's signature response
    FOREIGN KEY (session_id) REFERENCES signing_sessions(session_id)
);
```

## 11. Client (Wallet) Requirements

This section is crucial. It explicitly defines what is expected of a wallet that wants to integrate with our gateway.

- **11.1. Core Functionality:** A client wallet MUST be able to manage a Nostr private key.
- **11.2. Intent Signing:** The wallet MUST be able to construct and sign a high-level `kind: 31510` ("Action Intent") event based on user input.
- **11.3. Session Authorization:** The wallet MUST be able to prompt the user to approve the start of an "interactive signing session" with the gateway, initiated by the submission of a `kind: 31510` intent.
- **11.4. Remote Signing Oracle:** During an authorized session, the wallet MUST listen for encrypted `kind: 31511` ("Signing Challenge") DMs from the gateway.
- **11.5. Contextual Verification:** Upon receiving a signing challenge, the wallet MUST:
  - Verify the challenge is part of the authorized session.
  - Verify that the low-level data it is being asked to sign is consistent with the user's original high-level intent (e.g., the amount and asset have not been maliciously changed by the gateway).
- **11.6. Automated Response:** If verification passes, the wallet should **automatically sign the requested data** with the user's Nostr key and respond with a `kind: 31512` DM, without requiring further user prompts.

## 12. Implementation Scenarios

### Actors
- **Alice's Wallet (Wallet):** A standard Nostr wallet (like Alby) that has implemented our "Interactive Signing Session" NIP. It holds Alice's Nostr private key.
- **dApp Frontend (dApp):** The JavaScript application running in Alice's browser (e.g., `nostrswap.com`). It has no keys.
- **Relay:** The "Smart Relay" server. It's a powerful Nostr bot and orchestrator.
- **DEX Server:** The backend for NostrSwap. A sophisticated Nostr bot that manages the AMM logic and liquidity pool keys.

### Scenario 1: Lift gBTC via Lightning
**Goal:** Alice wants to deposit 0.1 real BTC to get a 0.1 gBTC VTXO in her Ark Pocket.

| Step | Actor | Action & Perspective |
| :--- | :--- | :--- |
| **1** | **dApp** | **Presents UI:** Alice is on the "Deposit" page. The dApp prompts her to enter the amount: `0.1 BTC`. |
| **2** | **dApp** | **Requests Invoice:** The dApp's JS makes a request to a gateway helper endpoint (or sends a Nostr service request): "I need a Lightning invoice for a 0.1 BTC lift for `alice_npub`." |
| **3** | **Relay** | **Provides Invoice:** The relay backend receives the request, prepares the on-chain anchor, and generates a real Bitcoin Lightning invoice. It sends this `lnbc...` invoice back to the dApp. |
| **4** | **dApp** | **Displays Invoice:** The dApp displays the QR code for the invoice. |
| **5** | **Alice** | **Pays Invoice:** Alice uses her separate, custodial Lightning wallet (e.g., Wallet of Satoshi, Cash App) to scan and pay the 0.1 BTC invoice. This happens outside the dApp. |
| **6** | **Relay** | **Detects Payment & Finalizes:** The relay's Lightning node receives the 0.1 BTC. This is the trigger. It updates its internal state, creating a new VTXO for 0.1 `gBTC` and assigning ownership to `alice_npub`. It now has the real BTC in its reserves. |
| **7** | **Relay** | **Publishes Confirmation:** The relay publishes a public `kind: 31340` (VTXO State Confirmation) Nostr event, announcing the creation of Alice's new `gBTC` VTXO. |
| **8** | **Wallet & dApp** | **Listen & Update:** Both Alice's Wallet (via its background Nostr subscription) and the dApp's JS see the confirmation. The dApp updates the UI to show her new balance of 0.1 `gBTC`. |

### Scenario 2: Land gBTC via Lightning
**Goal:** Alice wants to withdraw 0.05 gBTC from her Ark Pocket to her external Lightning wallet.

| Step | Actor | Action & Perspective |
| :--- | :--- | :--- |
| **1** | **Alice** | **Generates Invoice:** Alice uses her external Lightning wallet to generate an invoice for 0.05 BTC. |
| **2** | **dApp** | **Presents UI:** Alice is on the "Withdraw" page. She pastes the `lnbc...` invoice into the input field. |
| **3** | **dApp** | **Constructs Intent:** The dApp's JS constructs a high-level `kind: 31510` (Action Intent) event. Content: `{ "action": "land_lightning", "vutxo_to_spend": "...", "invoice": "lnbc..." }`. |
| **4** | **Wallet** | **Signs Intent:** The dApp uses the NIP-07 extension to ask Alice's Wallet to sign this single intent. Alby pops up asking her to approve the withdrawal. She approves. |
| **5** | **dApp** | **Publishes Intent:** The dApp publishes this single, signed authorization to Nostr, `p`-tagging the Relay. |
| **6** | **Relay** | **Receives & Orchestrates:** The relay sees the signed intent. It now has authorization. It initiates the **internal, interactive "dance"** with Alice's Wallet via encrypted DMs to get the low-level `ark_tx` and `checkpoint_txs` signatures required by `arkd`. The wallet, having been pre-authorized by the initial intent, provides these signatures automatically without further user prompts. |
| **7** | **Relay** | **Pays Invoice:** After successfully completing the internal dance and spending Alice's VTXO, the relay's Lightning node pays the 0.05 BTC invoice. |
| **8** | **Relay** | **Publishes Confirmation:** The relay publishes a `kind: 31340` confirmation showing that Alice's VTXO has been spent for the withdrawal. |

### Scenario 3: Swap gBTC with gUSD on a DEX
**Goal:** Alice wants to swap 0.01 gBTC for gUSD.

| Step | Actor | Action & Perspective |
| :--- | :--- | :--- |
| **1** | **dApp** | **Gets Quote:** The NostrSwap dApp gets a price from its DEX Server backend via a Nostr request. It displays "Receive ~650 gUSD". |
| **2** | **dApp** | **Constructs Intent:** The dApp's JS constructs Alice's high-level `kind: 31510` intent. Content: `{ "action": "atomic_swap", "my_leg": { "asset": "gBTC", "amount": 0.01 }, "counterparty_leg": { "recipient": "dex_pool_npub", "asset": "gUSD", "amount": 65000 } }`. |
| **3** | **Wallet** | **Signs Intent:** The dApp requests a signature via the NIP-07 extension. Alice approves the swap. |
| **4** | **dApp** | **Submits to Arranger:** The dApp sends Alice's single signed intent to its **DEX Server**. |
| **5** | **DEX Server** | **Arranges Batch:** The DEX Server receives Alice's authorization. It creates and signs its own corresponding `kind: 31510` intent (to send 650 gUSD to Alice). |
| **6** | **DEX Server** | **Submits Batch to Relay:** The DEX Server submits **both** high-level intents to the Relay in a single request (e.g., a Nostr DM). |
| **7** | **Relay** | **Orchestrates Dance:** The relay receives the batch. It now initiates **two parallel interactive signing sessions** via encrypted DMs: one with Alice's Wallet and one with the DEX Server's bot. It guides both parties through the low-level `ark_tx` and `checkpoint_tx` signing required by `arkd`. Both the wallet and the DEX bot respond automatically as they were pre-authorized. |
| **8** | **Relay** | **Publishes Confirmation:** After successfully collecting all signatures and finalizing the atomic swap with `arkd`, the relay publishes a single public `kind: 31340` confirmation for the entire swap, tagging both Alice and the DEX. |
| **9** | **Wallet & dApp** | **Update:** Both Alice's wallet and the dApp see the confirmation and update their balances. |

### Scenario 4: Add/Remove Liquidity for gBTC/gUSD
**Goal:** Alice wants to add 0.01 gBTC and 650 gUSD to the liquidity pool.

| Step | Actor | Action & Perspective |
| :--- | :--- | :--- |
| **1** | **dApp** | **Presents UI:** Alice is on the "Add Liquidity" page and enters the amounts. |
| **2** | **dApp** | **Constructs Intent:** The dApp's JS constructs a single, more complex `kind: 31510` intent. Content: `{ "action": "add_liquidity", "my_deposits": [ { "asset": "gBTC", "amount": 0.01 }, { "asset": "gUSD", "amount": 65000 } ], "recipient": "dex_pool_npub" }`. |
| **3** | **Wallet** | **Signs Intent:** The dApp requests a signature via NIP-07. Alby shows Alice is authorizing a deposit of two assets. She approves. |
| **4** | **dApp** | **Submits to Arranger:** The dApp sends Alice's single signed intent to its **DEX Server**. |
| **5** | **DEX Server** | **Arranges Batch:** The DEX Server receives Alice's deposit authorization. It calculates the LP tokens she is due, mints them, and creates its own signed `kind: 31510` intent to send the LP tokens to Alice. |
| **6** | **DEX Server** | **Submits Batch to Relay:** The DEX Server submits the batch of intents (Alice's two-asset deposit + its own LP token payout) to the Relay. |
| **7** | **Relay** | **Orchestrates Dance:** The relay again runs parallel interactive signing sessions with both Alice's Wallet and the DEX Server to get all the necessary low-level signatures for this three-way atomic state change. |
| **8** | **Relay** | **Publishes Confirmation:** The relay publishes a single public confirmation for the entire liquidity provision event. Alice's wallet sees her gBTC/gUSD are gone, but she has received the new LP Token VTXO. |

### Scenario 5: Authenticate User to the dApp
**Goal:** Alice "logs in" to the NostrPerps DEX dApp, proving her identity and allowing the dApp to fetch her balances.

| Step | Actor | Action & Perspective |
| :--- | :--- | :--- |
| **1** | **dApp** | **Presents Login:** The `nostrperps.com` frontend displays a "Connect Wallet" button. |
| **2** | **Alice** | **Initiates Login:** Alice clicks the button. |
| **3** | **dApp** | **Requests Identity:** The dApp's JavaScript uses the NIP-07 extension to call `window.nostr.getPublicKey()`. |
| **4** | **Wallet** | **Prompts for Approval:** The Alby extension pops up: "`nostrperps.com` would like to know your public key. **[ Deny ] [ Approve ]**" |
| **5** | **Alice** | **Approves:** Alice clicks "Approve." |
| **6** | **Wallet** | **Provides Identity:** The Alby extension returns Alice's `npub` (public key) to the dApp's JavaScript. |
| **7** | **dApp** | **Fetches State:** The dApp now knows who Alice is. It uses her `npub` to query the **Relay's** informational services (via Nostr DMs or helper endpoints) to fetch her current VTXO balances and any open positions she might have. |
| **8** | **dApp** | **Displays Dashboard:** The dApp renders her personalized trading dashboard, showing her balances and positions. She is now "logged in." |

*Note: For actions requiring a signature, a more robust NIP-42 "auth challenge" could be used, but for simply identifying the user to display data, `getPublicKey()` is sufficient.*

### Scenario 6: Oracle Adds Price Data
**Goal:** A trusted, independent Oracle needs to publish the price of BTC/USD to the network so the Perps DEX can use it for marking positions and triggering liquidations.

| Step | Actor | Action & Perspective |
| :--- | :--- | :--- |
| **1** | **Oracle** | **Fetches Price Data:** The Oracle's backend server (a sophisticated Nostr bot) fetches the latest BTC price from multiple sources (e.g., Coinbase, Binance, Kraken APIs) and calculates a medianized, tamper-resistant price. |
| **2** | **Oracle** | **Constructs Price Event:** The Oracle constructs a `kind: 10420` ("Oracle Price Data") Nostr event. |
| | | - **Content:** `{ "asset_pair": "BTC/USD", "price": 65432.10, "timestamp": ..., "sources": ["coinbase", "kraken", ...] }` |
| | | - **Tags:** It might use a `d` tag for the asset pair (e.g., `d: BTCUSD`) to make it a replaceable event, ensuring only the latest price is considered canonical. |
| **3** | **Oracle** | **Signs & Publishes:** The Oracle signs this event with its well-known, trusted Nostr private key and publishes it publicly to Nostr relays. This happens on a regular, frequent schedule (e.g., every 10 seconds). |
| **4** | **DEX Server** | **Listens for Price:** The NostrPerps DEX Server is subscribed to events from the Oracle's known `npub` and with `kind: 10420`. |
| **5** | **DEX Server** | **Validates & Stores Price:** The DEX server sees the new price event. It verifies the signature to ensure it came from the legitimate Oracle. It then updates its internal "mark price" for the BTC/USD perpetual contract. |
| **6** | **DEX Server** | **Marks Positions:** The DEX server now iterates through all open positions and re-calculates their current profit/loss and margin ratio based on this new, trusted price. |
| **7** | **Relay & Wallet** | **Are Unaware:** The Relay and the user's wallet are completely unaware of this process. The price feed is application-level data consumed directly by the DeFi protocol (the DEX). |

### Scenario 7: Open & Liquidate a Perpetual Position
**Goal:** Alice wants to open a 10x long on BTC, and later, her position gets liquidated.

#### Opening the Position

| Step | Actor | Action & Perspective |
| :--- | :--- | :--- |
| **1** | **dApp** | **Presents UI:** Alice is on the trading page. She enters: `Long`, `BTC/USD`, Size: `0.1 BTC`, Leverage: `10x`. The UI calculates she needs `0.01 gBTC` as margin. |
| **2** | **dApp** | **Constructs Intent:** The dApp's JS constructs a `kind: 31510` (Action Intent). The content is complex: `{ "action": "open_perp", "margin_deposit": { "asset": "gBTC", "amount": 0.01 }, "position_details": { "side": "long", "leverage": 10, "entry_price": 65432.10 }, "liquidation_oracle": "oracle_npub" }`. This content is her cryptographic agreement to the terms. |
| **3** | **Wallet** | **Signs Intent:** The dApp requests a signature via NIP-07. Alby shows a detailed summary of the position she is opening. Alice approves. |
| **4** | **dApp** | **Submits to DEX Server:** The dApp sends Alice's single signed intent to its **DEX Server**. |
| **5** | **DEX Server** | **Arranges Batch & Submits:** The DEX Server finds a counterparty (a short-seller or its own liquidity pool). It arranges the atomic batch: Alice sends `0.01 gBTC` to the DEX margin account, and the DEX sends a "Position Token" VTXO (an NFT) back to Alice. It submits this batch to the **Relay**. |
| **6** | **Relay & Wallet**| **Settle & Confirm:** The Relay orchestrates the "dance" for this atomic swap. The user wallet and DEX server provide the necessary low-level signatures. Alice's balance now shows `-0.01 gBTC` and `+1 BTC-LONG-PERP-TOKEN`. |

#### Liquidating the Position

| Step | Actor | Action & Perspective |
| :--- | :--- | :--- |
| **1** | **Oracle** | **Publishes Low Price:** The Oracle publishes a new price: `BTC/USD = 58000.00`. |
| **2** | **DEX Server** | **Detects Liquidation:** The DEX Server sees the new price and re-calculates Alice's margin. It determines her position is now below the maintenance margin and must be liquidated. |
| **3** | **DEX Server** | **Constructs Liquidation Intent:** The DEX Server constructs a **new `kind: 31337` intent.** This intent spends the `0.01 gBTC` from the margin account (which it controls). It also spends Alice's "Position Token" VTXO. This is the crucial part. |
| **4** | **DEX Server** | **Provides Proof of Authority:** To authorize spending Alice's VTXO, the `witness` field of the intent includes the **original, signed `kind: 31510` event from when she opened the position.** This is her cryptographic pre-authorization. The witness also includes the signed Oracle price data as proof the liquidation condition was met. |
| **5** | **DEX Server** | **Submits to Relay:** The DEX server submits this liquidation transaction (which moves the margin to its insurance fund and burns Alice's position token) to the Relay. |
| **6** | **Relay** | **Validates & Settles:** The Relay receives this. It doesn't know what a liquidation is. It just performs its checklist: |
| | | - Is the DEX's signature valid? Yes. |
| | | - Is the `witness` (Alice's original signed intent) valid proof of authority for the DEX to spend Alice's Position Token VTXO under these conditions? It verifies the signatures and oracle data. Yes. |
| | | - It processes the state change. |
| **7** | **Relay** | **Publishes Confirmation:** The Relay publishes the confirmation. Alice's wallet sees her "Position Token" VTXO has been spent. Her position is gone. |