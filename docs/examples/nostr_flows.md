# ArkRelay Nostr Event Flows

This document provides comprehensive, real-world examples of Nostr event sequences for common ArkRelay Gateway operations.

## Event Types Overview

| Kind | Direction | Description | Encryption |
|------|-----------|-------------|------------|
| 31500 | User → Gateway | Service Request | Encrypted DM |
| 31501 | Gateway → User | Service Response | Encrypted DM |
| 31502 | User ↔ Gateway | Service Notifications | Encrypted DM |
| 31510 | User → Gateway | Action Intent | Public |
| 31511 | Gateway → User | Signing Challenge | Encrypted DM |
| 31512 | User → Gateway | Signing Response | Encrypted DM |
| 31340 | Gateway → Public | Transaction Confirmation | Public |
| 31341 | Gateway → User | Transaction Failure | Encrypted DM |
| 31342 | Gateway → Public | L1 Commitment Notice | Public |

---

## 1. gBTC Lift Flow (Lightning → VTXO)

### Step 1: Service Request (31500)
```json
{
  "id": "event_001",
  "pubkey": "npub1user123...",
  "created_at": 1735689600,
  "kind": 31500,
  "tags": [
    ["p", "npub1gateway..."],
    ["e", "req_001"]
  ],
  "content": "{\"action\":\"lift_lightning\",\"asset_id\":\"gBTC\",\"amount\":1000000,\"timestamp\":1735689600}",
  "sig": "signature_here"
}
```

### Step 2: Service Response (31501)
```json
{
  "id": "event_002",
  "pubkey": "npub1gateway...",
  "created_at": 1735689601,
  "kind": 31501,
  "tags": [
    ["p", "npub1user123..."],
    ["e", "event_001"]
  ],
  "content": "{\"status\":\"pending\",\"action\":\"lift_lightning\",\"asset_id\":\"gBTC\",\"amount\":1000000,\"invoice\":\"lnbc1000000n1p3k8...\",\"expires_at\":1735693200}",
  "sig": "gateway_signature"
}
```

### Step 3: Action Intent (31510) - After Lightning Payment
```json
{
  "id": "event_003",
  "pubkey": "npub1user123...",
  "created_at": 1735689700,
  "kind": 31510,
  "tags": [
    ["p", "npub1gateway..."],
    ["e", "event_001"]
  ],
  "content": "{\"action_id\":\"lift_001_abc123\",\"type\":\"lightning:lift\",\"params\":{\"asset_id\":\"gBTC\",\"amount\":1000000,\"payment_hash\":\"abc123...\",\"fee_asset_id\":\"gBTC\",\"fee_amount\":10},\"expires_at\":1735690500}",
  "sig": "user_signature"
}
```

### Step 4: Signing Challenge (31511)
```json
{
  "id": "event_004",
  "pubkey": "npub1gateway...",
  "created_at": 1735689701,
  "kind": 31511,
  "tags": [
    ["p", "npub1user123..."],
    ["e", "event_003"]
  ],
  "content": "{\"session_id\":\"sess_01HXABC123\",\"type\":\"sign_payload\",\"payload_to_sign\":\"0xdeadbeef123...\",\"payload_ref\":\"sha256:8c1fabc...\",\"algo\":\"BIP340\",\"domain\":\"arkrelay/lightning/v1\",\"context\":{\"human\":\"Authorize gBTC lift of 1000000 sats via Lightning payment\",\"step_index\":1,\"step_total\":1,\"amount\":1000000,\"asset_id\":\"gBTC\"}}",
  "sig": "gateway_signature"
}
```

### Step 5: Signing Response (31512)
```json
{
  "id": "event_005",
  "pubkey": "npub1user123...",
  "created_at": 1735689702,
  "kind": 31512,
  "tags": [
    ["p", "npub1gateway..."],
    ["e", "event_004"]
  ],
  "content": "{\"session_id\":\"sess_01HXABC123\",\"type\":\"sign_payload\",\"signature\":\"schnorr_sig_abc...\",\"payload_ref\":\"sha256:8c1fabc...\"}",
  "sig": "user_signature"
}
```

### Step 6: Transaction Confirmation (31340)
```json
{
  "id": "event_006",
  "pubkey": "npub1gateway...",
  "created_at": 1735689800,
  "kind": 31340,
  "tags": [
    ["e", "event_003"],  // Original intent
    ["p", "npub1user123..."],
    ["amount", "1000000"],
    ["asset", "gBTC"]
  ],
  "content": "{\"status\":\"success\",\"ref_action_id\":\"lift_001_abc123\",\"results\":{\"txid\":\"abc123def456...\",\"vtxo_id\":\"vtxo_new_001\",\"amount_processed\":1000000,\"fee_paid\":10,\"payment_hash\":\"abc123...\"},\"timestamp\":1735689800}",
  "sig": "gateway_signature"
}
```

---

## 2. gBTC Land Flow (VTXO → Lightning)

### Step 1: Action Intent (31510)
```json
{
  "id": "event_101",
  "pubkey": "npub1user123...",
  "created_at": 1735689900,
  "kind": 31510,
  "tags": [
    ["p", "npub1gateway..."]
  ],
  "content": "{\"action_id\":\"land_001_def456\",\"type\":\"lightning:land\",\"params\":{\"asset_id\":\"gBTC\",\"amount\":500000,\"lightning_invoice\":\"lnbc500000n1p3k8...\",\"fee_asset_id\":\"gBTC\",\"fee_amount\":50},\"expires_at\":1735690800}",
  "sig": "user_signature"
}
```

### Step 2: Multi-step Signing Challenge (31511)
```json
{
  "id": "event_102",
  "pubkey": "npub1gateway...",
  "created_at": 1735689901,
  "kind": 31511,
  "tags": [
    ["p", "npub1user123..."],
    ["e", "event_101"]
  ],
  "content": "{\"session_id\":\"sess_01HXDEF456\",\"type\":\"sign_tx\",\"payload_to_sign\":\"020000000001abcd...\",\"payload_ref\":\"sha256:land123...\",\"algo\":\"BIP340\",\"domain\":\"arkrelay/lightning/v1\",\"context\":{\"human\":\"Step 1/2: Authorize VTXO spend for Lightning land\",\"step_index\":1,\"step_total\":2,\"amount\":500000,\"invoice\":\"lnbc500000n1p3k8...\"}}",
  "sig": "gateway_signature"
}
```

### Step 3: Lightning Payment Challenge (31511)
```json
{
  "id": "event_103",
  "pubkey": "npub1gateway...",
  "created_at": 1735689902,
  "kind": 31511,
  "tags": [
    ["p", "npub1user123..."],
    ["e", "event_101"]
  ],
  "content": "{\"session_id\":\"sess_01HXDEF456\",\"type\":\"sign_tx\",\"payload_to_sign\":\"020000000001efgh...\",\"payload_ref\":\"sha256:lightning_pay...\",\"algo\":\"BIP340\",\"domain\":\"arkrelay/lightning/v1\",\"context\":{\"human\":\"Step 2/2: Authorize Lightning invoice payment\",\"step_index\":2,\"step_total\":2,\"invoice\":\"lnbc500000n1p3k8...\"}}",
  "sig": "gateway_signature"
}
```

### Step 4: Transaction Confirmation (31340)
```json
{
  "id": "event_104",
  "pubkey": "npub1gateway...",
  "created_at": 1735690000,
  "kind": 31340,
  "tags": [
    ["e", "event_101"],
    ["p", "npub1user123..."],
    ["amount", "500000"],
    ["asset", "gBTC"]
  ],
  "content": "{\"status\":\"success\",\"ref_action_id\":\"land_001_def456\",\"results\":{\"txid\":\"def456ghi789...\",\"vtxo_spent\":\"vtxo_abc123\",\"lightning_payment\":\"lnbc500000n1p3k8...\",\"amount_processed\":500000,\"fee_paid\":50},\"timestamp\":1735690000}",
  "sig": "gateway_signature"
}
```

---

## 3. VTXO Split-and-Send Flow

### Step 1: Split Intent (31510)
```json
{
  "id": "event_201",
  "pubkey": "npub1user123...",
  "created_at": 1735690100,
  "kind": 31510,
  "tags": [
    ["p", "npub1gateway..."]
  ],
  "content": "{\"action_id\":\"split_001_ghi789\",\"type\":\"vtxo:split\",\"params\":{\"vtxo_id\":\"vtxo_large_001\",\"split_amounts\":[200000000,300000000],\"asset_id\":\"gUSD\",\"fee_asset_id\":\"gBTC\",\"fee_amount\":10,\"min_change\":1000},\"expires_at\":1735691000}",
  "sig": "user_signature"
}
```

### Step 2: Split Authorization Challenge (31511) - Step 1
```json
{
  "id": "event_202",
  "pubkey": "npub1gateway...",
  "created_at": 1735690101,
  "kind": 31511,
  "tags": [
    ["p", "npub1user123..."],
    ["e", "event_201"]
  ],
  "content": "{\"session_id\":\"sess_01HXGHI789\",\"type\":\"sign_payload\",\"payload_to_sign\":\"0xsplit_part1_abc...\",\"payload_ref\":\"sha256:split_part1_123...\",\"algo\":\"BIP340\",\"domain\":\"arkrelay/vtxo/split/v1\",\"context\":{\"human\":\"Step 1/2: Split 200M gUSD from vtxo_large_001\",\"step_index\":1,\"step_total\":2,\"split_amount\":200000000,\"total_split\":500000000}}",
  "sig": "gateway_signature"
}
```

### Step 3: Split Authorization Challenge (31511) - Step 2
```json
{
  "id": "event_203",
  "pubkey": "npub1gateway...",
  "created_at": 1735690102,
  "kind": 31511,
  "tags": [
    ["p", "npub1user123..."],
    ["e", "event_201"]
  ],
  "content": "{\"session_id\":\"sess_01HXGHI789\",\"type\":\"sign_payload\",\"payload_to_sign\":\"0xsplit_part2_def...\",\"payload_ref\":\"sha256:split_part2_456...\",\"algo\":\"BIP340\",\"domain\":\"arkrelay/vtxo/split/v1\",\"context\":{\"human\":\"Step 2/2: Split 300M gUSD from vtxo_large_001\",\"step_index\":2,\"step_total\":2,\"split_amount\":300000000,\"total_split\":500000000}}",
  "sig": "gateway_signature"
}
```

### Step 4: Split Confirmation (31340)
```json
{
  "id": "event_204",
  "pubkey": "npub1gateway...",
  "created_at": 1735690200,
  "kind": 31340,
  "tags": [
    ["e", "event_201"],
    ["p", "npub1user123..."],
    ["vtxo", "vtxo_large_001"]
  ],
  "content": "{\"status\":\"success\",\"ref_action_id\":\"split_001_ghi789\",\"results\":{\"txid\":\"ghi789jkl012...\",\"input_vtxo\":\"vtxo_large_001\",\"outputs\":[{\"vtxo_id\":\"vtxo_split_001\",\"amount\":200000000,\"asset_id\":\"gUSD\"},{\"vtxo_id\":\"vtxo_split_002\",\"amount\":300000000,\"asset_id\":\"gUSD\"}],\"fee_paid\":10},\"timestamp\":1735690200}",
  "sig": "gateway_signature"
}
```

---

## 4. Multi-VTXO Transfer Flow

### Step 1: Multi-VTXO Intent (31510)
```json
{
  "id": "event_301",
  "pubkey": "npub1user123...",
  "created_at": 1735690300,
  "kind": 31510,
  "tags": [
    ["p", "npub1gateway..."]
  ],
  "content": "{\"action_id\":\"multi_001_jkl012\",\"type\":\"vtxo:multi_transfer\",\"params\":{\"asset_id\":\"gUSD\",\"total_amount\":400000000,\"recipient_pubkey\":\"npub1recipient...\",\"source_vtxos\":[\"vtxo_split_001\",\"vtxo_split_002\"],\"fee_asset_id\":\"gBTC\",\"fee_amount\":10,\"max_inputs\":5,\"strategy\":\"optimal\"},\"expires_at\":1735691200}",
  "sig": "user_signature"
}
```

### Step 2: Multi-VTXO Challenge (31511)
```json
{
  "id": "event_302",
  "pubkey": "npub1gateway...",
  "created_at": 1735690301,
  "kind": 31511,
  "tags": [
    ["p", "npub1user123..."],
    ["e", "event_301"]
  ],
  "content": "{\"session_id\":\"sess_01HXJKL012\",\"type\":\"sign_tx\",\"payload_to_sign\":\"020000000001multi_vtxo...\",\"payload_ref\":\"sha256:multi_vtxo_abc...\",\"algo\":\"BIP340\",\"domain\":\"arkrelay/vtxo/multi/v1\",\"context\":{\"human\":\"Authorize multi-VTXO transfer: 400M gUSD to npub1recipient...\",\"total_amount\":400000000,\"vtxo_count\":2,\"change_amount\":100000000,\"strategy\":\"optimal\"}}",
  "sig": "gateway_signature"
}
```

### Step 3: Multi-VTXO Confirmation (31340)
```json
{
  "id": "event_303",
  "pubkey": "npub1gateway...",
  "created_at": 1735690400,
  "kind": 31340,
  "tags": [
    ["e", "event_301"],
    ["p", "npub1user123..."],
    ["p", "npub1recipient..."],
    ["amount", "400000000"],
    ["asset", "gUSD"]
  ],
  "content": "{\"status\":\"success\",\"ref_action_id\":\"multi_001_jkl012\",\"results\":{\"txid\":\"jkl012mno345...\",\"inputs\":[\"vtxo_split_001\",\"vtxo_split_002\"],\"outputs\":[{\"amount\":400000000,\"recipient\":\"npub1recipient...\"},{\"amount\":100000000,\"recipient\":\"npub1user123...\"}],\"fee_paid\":10},\"timestamp\":1735690400}",
  "sig": "gateway_signature"
}
```

---

## 5. Error Handling (31341 Failure)

### Insufficient Balance Error
```json
{
  "id": "event_401",
  "pubkey": "npub1gateway...",
  "created_at": 1735690500,
  "kind": 31341,
  "tags": [
    ["p", "npub1user123..."],
    ["e", "event_101"],  // Original intent
    ["code", "2001"]
  ],
  "content": "{\"status\":\"failure\",\"code\":2001,\"message\":\"Insufficient VTXO balance for transfer\",\"ref_action_id\":\"land_001_def456\",\"details\":{\"required\":500000,\"available\":300000,\"asset_id\":\"gBTC\"},\"timestamp\":1735690500}",
  "sig": "gateway_signature"
}
```

### VTXO Already Spent Error
```json
{
  "id": "event_402",
  "pubkey": "npub1gateway...",
  "created_at": 1735690600,
  "kind": 31341,
  "tags": [
    ["p", "npub1user123..."],
    ["e", "event_201"],
    ["code", "2002"]
  ],
  "content": "{\"status\":\"failure\",\"code\":2002,\"message\":\"Input VTXO already spent\",\"ref_action_id\":\"split_001_ghi789\",\"details\":{\"vtxo_id\":\"vtxo_large_001\",\"spending_txid\":\"abc123def456...\"},\"timestamp\":1735690600}",
  "sig": "gateway_signature"
}
```

### Signature Verification Error
```json
{
  "id": "event_403",
  "pubkey": "npub1gateway...",
  "created_at": 1735690700,
  "kind": 31341,
  "tags": [
    ["p", "npub1user123..."],
    ["e", "event_301"],
    ["code", "1001"]
  ],
  "content": "{\"status\":\"failure\",\"code\":1001,\"message\":\"Invalid Nostr signature\",\"ref_action_id\":\"multi_001_jkl012\",\"details\":{\"signature\":\"invalid_sig_123...\",\"pubkey\":\"npub1user123...\"},\"timestamp\":1735690700}",
  "sig": "gateway_signature"
}
```

---

## 6. L1 Commitment Notice (31342)

```json
{
  "id": "event_501",
  "pubkey": "npub1gateway...",
  "created_at": 1735690800,
  "kind": 31342,
  "tags": [
    ["l1_tx", "abc123def456..."],
    ["block_height", "850000"],
    ["batch_id", "batch_001"]
  ],
  "content": "{\"status\":\"committed\",\"l1_txid\":\"abc123def456...\",\"block_height\":850000,\"batch_id\":\"batch_001\",\"vtxo_count\":150,\"total_value\":5000000000,\"timestamp\":1735690800}",
  "sig": "gateway_signature"
}
```

---

## Key Implementation Notes

### 1. **Event Correlation**
- Use `e` tags to correlate related events
- Include `ref_action_id` in all confirmations and failures
- Maintain `session_id` throughout multi-step operations

### 2. **Security Best Practices**
- Always verify signatures before processing events
- Check `expires_at` timestamps on all intents and challenges
- Validate `payload_ref` matches expected hash of logical payload

### 3. **Multi-step Operations**
- Use `step_index` and `step_total` in context for clarity
- Send separate 31511 challenges for each authorization step
- Include human-readable descriptions for each step

### 4. **Error Handling**
- Provide specific error codes (1000-1999: validation, 2000-2999: business logic, 3000-3999: system)
- Include detailed error context for debugging
- Always reference the original action_id

### 5. **Tag Usage**
- `p` tags for public keys (participants)
- `e` tags for event correlation
- Custom tags for metadata (amount, asset, etc.)

### 6. **Encryption Requirements**
- 31500/31501/31502/31511/31512/31341 MUST be encrypted DMs (NIP-04/44)
- 31510/31340/31342 are public events
- Always verify encryption/decryption success

These examples provide complete, production-ready Nostr event flows for all major ArkRelay Gateway operations.