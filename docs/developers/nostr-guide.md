# ArkRelay Nostr Developer Guide

This guide explains how to integrate a Nostr-capable wallet or dApp with the ArkRelay Gateway using standard Nostr NIPs and the event kinds used by this project.

The Gateway is designed so wallets can authorize complex, multi-step Ark protocol operations using a single, high-level intent event, and then answer low-level signing challenges over encrypted DMs.

- Core principle: Nostr is the API (writes are initiated via Nostr)
- Privacy and safety: Encrypted DMs (NIP-04/NIP-44) for all interactive steps
- UX: One user authorization upfront (high-level), automated responses to low-level signing challenges thereafter

---

## Event Kinds and Protocol

The Gateway processes and emits these kinds (per PRD):

- 31510 — High-Level Action Intent (published by wallet or dApp)
- 31511 — Relay Signing Challenge (encrypted DM from gateway to wallet)
- 31512 — Client Signing Response (encrypted DM from wallet to gateway)
- 31340 — Final Transaction Confirmation (public, by gateway)
- 31341 — Transaction Failure Notice (encrypted DM, by gateway)
- 31342 — L1 Commitment Notice (public, by gateway)

All interactive messages (challenges and responses) must use encrypted DMs per NIP-04/NIP-44.

---

## Required NIPs

- NIP-01: Basic event format
- NIP-04: Encrypted Direct Messages (required for challenges/responses)
- NIP-07: Browser extension APIs for signing and identity (wallet UX)
- NIP-44: Modern encryption for DMs (use as supported by your tooling)

---

## High-Level Action Intent (kind: 31510)

Published by the client to initiate any state-changing action. The intent is a single, user-approved authorization.

- MUST p-tag the Gateway’s pubkey (`p` tag)
- SHOULD include a unique `action_id` to prevent replays
- MUST include an `expires_at` to bound authorization

Example content (p2p transfer):
```json
{
  "action_id": "e4b7ff53-4f83-4b62-9a4d-4b04a51e2c61",
  "type": "p2p_transfer",
  "my_leg": {
    "asset": "BTC",
    "amount": 10000
  },
  "counterparty_leg": {
    "recipient": "<recipient_npub>",
    "asset": "BTC",
    "amount": 10000
  },
  "recipient_pubkey": "<recipient_npub>",
  "asset_id": "BTC",
  "amount": 10000,
  "expires_at": 1735689600
}
```

Tags:
- `p`: gateway’s `npub` (target)
- (Optional) `e`: parent or correlating event ids

---

## Relay Signing Challenge (kind: 31511) — Encrypted DM

Sent by the gateway to the wallet via encrypted DM. Requests a precise signature over low-level data necessary to complete Ark protocol steps.

- Content example (JSON):
```json
{
  "session_id": "<session_id>",
  "type": "sign_ark_tx",
  "payload_to_sign": "<hex or serialized bytes>",
  "human_readable_context": "Step 1/2: Authorize transfer of 0.0001 BTC to <recipient>"
}
```
- Tags: MUST include an `e` tag referencing the original 31510 Intent.

---

## Client Signing Response (kind: 31512) — Encrypted DM

Published by the wallet back to the gateway.

- Content example:
```json
{
  "session_id": "<session_id>",
  "type": "sign_ark_tx",
  "signature": "<wallet_signature_hex>",
  "payload_ref": "<hash or id of payload>"
}
```

---

## Final Transaction and Notifications

- 31340 — Final Transaction Confirmation (public):
  - Tags: SHOULD `e`-tag the associated 31510 intent id(s). SHOULD `p`-tag recipients.
  - Content: details of spent and created VTXOs and final transactions.
- 31341 — Transaction Failure Notice (encrypted DM):
  - Content: `{ "status": "failure", "code": <int>, "message": "..." }`
- 31342 — L1 Commitment Notice (public):
  - Content: `{ "l1_txid": "...", "block_height": 0, "merkle_root_of_l2_txs": "..." }`

---

## Recommended Wallet Flow

1) Prompt the user to approve a single high-level intent (31510). Sign with NIP-07.
2) After the gateway acknowledges the intent, listen for encrypted DMs from the gateway (31511 challenges).
3) For each challenge:
   - Verify it matches the authorized session (`session_id`, `type`).
   - Verify low-level data matches the high-level intent (amounts, asset, recipients).
   - Automatically sign and reply with an encrypted DM (31512) without re-prompting the user.
4) Monitor for final public confirmation (31340) or failure DM (31341).

---

## JavaScript Example (Browser with NIP-07)

```js
// Assumes a NIP-07 provider is available as window.nostr
const gatewayPubkey = "<gateway_npub_hex>"; // hex (not bech32)

// 1) Get user identity
const userPubKey = await window.nostr.getPublicKey();

// 2) Build and sign 31510
const intent = {
  kind: 31510,
  content: JSON.stringify({
    action_id: crypto.randomUUID(),
    type: "p2p_transfer",
    recipient_pubkey: "<recipient_npub>",
    asset_id: "BTC",
    amount: 10000,
    expires_at: Math.floor(Date.now() / 1000) + 15 * 60
  }),
  tags: [["p", gatewayPubkey]],
  created_at: Math.floor(Date.now() / 1000),
  pubkey: userPubKey
};
const signedIntent = await window.nostr.signEvent(intent);
// 3) Publish to your chosen relays (use your Nostr relay client)
// relay.publish(signedIntent)

// 4) Listen for encrypted DM (31511) from gateway and respond with 31512
// Pseudocode: use your favorite nostr lib to subscribe to DMs from gateway
// On receiving challenge DM content:
//   - decrypt with NIP-04/44
//   - verify session and context
//   - produce signature over payload_to_sign using your key policy
//   - send encrypted DM back with kind 31512
```

---

## Python Example (pynostr)

```python
from pynostr.key import PrivateKey
from pynostr.event import Event
from pynostr.relay_manager import RelayManager
from pynostr.encryption import encrypt_message
import json, time

# Setup keys and relays
priv = PrivateKey()  # or load from secure storage
pub_hex = priv.public_key.hex()
relays = ["wss://relay.damus.io", "wss://nos.lol"]
rm = RelayManager()
for r in relays:
    rm.add_relay(r)
rm.open_connections({"cert_reqs": 0})

# Build 31510
content = {
    "action_id": "...",
    "type": "p2p_transfer",
    "recipient_pubkey": "<recipient_npub>",
    "asset_id": "BTC",
    "amount": 10000,
    "expires_at": int(time.time()) + 15 * 60
}
intent = Event(
    public_key=pub_hex,
    content=json.dumps(content),
    kind=31510,
    tags=[["p", "<gateway_pubkey_hex>"]]
)
priv.sign_event(intent)
rm.publish_event(intent)
```

Use your library’s DM encryption helpers to implement 31511/31512.

---

## Session Correlation and Security

- Use `session_id` provided by the gateway to correlate challenges.
- Validate `expires_at` on the intent and challenge.
- Include `action_id` as a client nonce to prevent replays.
- Always match amounts/asset/recipient in the low-level payload to the high-level authorization.

---

## Error Codes (examples)

- 1001 — Invalid Nostr Signature
- 2001 — Insufficient VTXO Balance
- 2002 — Input VTXO Already Spent
- 3001 — Atomic Batch Validation Failed
- 4001 — Fee Output Missing or Incorrect

The gateway sends failures via 31341 (encrypted DM).

---

## Gateway Helper Endpoints (HTTP)

While state-changing actions are via Nostr, the gateway exposes helper HTTP endpoints to manage sessions and monitor progress during development.

Key endpoints:
- `POST /sessions/create` — create a session (dev/testing)
- `POST /sessions/{session_id}/challenge` — create challenge (dev/testing)
- `POST /sessions/{session_id}/respond` — validate response (dev/testing)
- `POST /signing/ceremony/start` — start ceremony
- `GET  /signing/ceremony/{session_id}/status` — ceremony status
- `GET  /nostr/status` — nostr connectivity info

See `docs/users/guide.md` and the OpenAPI spec for full details.

---

## Tips for dApp Builders

- Cache the user’s `npub` and 31510 drafts client-side for smoother UX.
- Show clear, human-readable context before signing (reflecting the fields the user is authorizing).
- Use multiple relays to improve reliability.
- Handle retries for DM encryption/decryption gracefully.
- Do not log plaintext DM contents.

---

## Tips for Wallet Builders

- Provide a user setting to auto-respond to gateway challenges within a time window (e.g., 15 minutes) after approving a 31510.
- Display the gateway’s `npub` and verified identity metadata.
- Validate that low-level payloads requested to sign are consistent with high-level authorizations.
- Consider rate-limiting and per-session protections.
