# RGB Smart Contract Integration Guide

This guide provides comprehensive documentation for integrating RGB smart contracts with the Ark Relay Gateway's VTXO system.

## Overview

The Ark Relay Gateway now supports RGB (RGB v0.1) smart contracts through extended VTXO functionality. This allows developers to:

- Issue and manage RGB smart contracts on Bitcoin
- Create fungible and non-fungible assets with RGB
- Handle RGB allocations within VTXOs
- Validate RGB proofs and state transitions
- Build RGB-powered DeFi applications

## Architecture

### RGB-Enhanced VTXO System

The existing VTXO system has been extended to support RGB assets:

```
VTXO (Virtual UTXO)
├── Standard Fields
│   ├── vtxo_id, txid, vout
│   ├── amount_sats, script_pubkey
│   └── asset_id, user_pubkey, status
└── RGB-Specific Fields
    ├── rgb_asset_type (CFA, NIA, RIA, UDA)
    ├── rgb_proof_data
    ├── rgb_state_commitment
    ├── rgb_contract_state
    └── rgb_allocation_id
```

### Database Schema

New tables have been added to support RGB:

- **rgb_contracts**: Stores RGB contract metadata and state
- **rgb_allocations**: Tracks RGB asset allocations within VTXOs
- **Enhanced assets table**: RGB-specific columns for contract linkage
- **Enhanced vtxos table**: RGB state and proof data

## RGB Schema Types

The system supports four RGB schema types:

### CFA (Collectible Fungible Asset)
- **Use Case**: Fungible tokens with fixed supply
- **Examples**: Stablecoins, utility tokens
- **Features**: Non-inflatable, transferable, divisible

### NIA (Non-Inflatable Asset)
- **Use Case**: Tokens with issuance controls
- **Examples**: Governance tokens, wrapped assets
- **Features**: Fixed total supply, controlled issuance

### RIA (Reissuable Asset)
- **Use Case**: Assets that need additional issuance
- **Examples**: Reward tokens, credit systems
- **Features**: Controlled reissuance capabilities

### UDA (Unique Digital Asset)
- **Use Case**: NFTs and unique collectibles
- **Examples**: Digital art, unique rights
- **Features**: Non-divisible, unique identifiers

## API Reference

### Contract Management

#### Register RGB Contract
```http
POST /rgb/contracts
Content-Type: application/json

{
  "contract_id": "rgb_contract_001",
  "name": "My RGB Token",
  "description": "A sample RGB token",
  "interface_id": "RGB20Interface",
  "specification_id": "RGB20Spec",
  "genesis_proof": "base64_encoded_genesis_proof",
  "schema_type": "cfa",
  "metadata": {
    "website": "https://example.com",
    "icon": "data:image/png;base64,..."
  },
  "creator_pubkey": "npub1...",
  "ticker": "RGBT"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "contract_id": "rgb_contract_001",
    "name": "My RGB Token",
    "asset_id": "rgb_rgb_contract_001",
    "schema_type": "cfa",
    "status": "registered",
    "created_at": "2025-09-30T12:00:00Z"
  },
  "message": "RGB contract rgb_contract_001 registered successfully"
}
```

#### Get RGB Contract
```http
GET /rgb/contracts/{contract_id}
```

#### List RGB Contracts
```http
GET /rgb/contracts?active_only=true
```

### Allocation Management

#### Create RGB Allocation
```http
POST /rgb/allocations
Content-Type: application/json

{
  "contract_id": "rgb_contract_001",
  "vtxo_id": "vtxo_123456",
  "owner_pubkey": "npub1...",
  "amount": 1000000,
  "state_commitment": "base64_encoded_state",
  "proof_data": "base64_encoded_proof",
  "seal_type": "tapret_first"
}
```

#### Get RGB Allocations
```http
GET /rgb/allocations?owner_pubkey=npub1...&contract_id=rgb_contract_001
```

#### Transfer RGB Allocation
```http
POST /rgb/allocations/transfer
Content-Type: application/json

{
  "from_pubkey": "npub1sender...",
  "to_pubkey": "npub1receiver...",
  "allocation_id": "vtxo_123_rgb_contract_001",
  "amount": 500000
}
```

### VTXO Operations

#### Create RGB VTXO
```http
POST /rgb/vtxos/create
Content-Type: application/json

{
  "user_pubkey": "npub1...",
  "asset_id": "rgb_rgb_contract_001",
  "amount_sats": 1000000,
  "rgb_contract_id": "rgb_contract_001",
  "rgb_allocation_data": {
    "metadata": {"custom": "data"}
  }
}
```

#### Split RGB VTXO
```http
POST /rgb/vtxos/{vtxo_id}/split
Content-Type: application/json

{
  "split_amounts": [300000, 700000],
  "rgb_allocation_splits": [
    {
      "contract_id": "rgb_contract_001",
      "seal_type": "tapret_first"
    },
    {
      "contract_id": "rgb_contract_001",
      "seal_type": "tapret_first"
    }
  ]
}
```

#### Get User RGB VTXOs
```http
GET /rgb/vtxos/user/{user_pubkey}?contract_id=rgb_contract_001
```

#### Validate RGB VTXO State
```http
GET /rgb/vtxos/{vtxo_id}/validate
```

### Proof Validation

#### Validate RGB Proof
```http
POST /rgb/proofs/validate
Content-Type: application/json

{
  "proof_data": "base64_encoded_proof",
  "contract_id": "rgb_contract_001"
}
```

### System Information

#### Get RGB Statistics
```http
GET /rgb/stats
```

#### RGB Health Check
```http
GET /rgb/health
```

## SDK Integration

### Python SDK

```python
from sdk import GatewayClient
from core.rgb_manager import get_rgb_manager

# Initialize client
client = GatewayClient("http://localhost:8000")
rgb_manager = get_rgb_manager()

# Register RGB contract
contract_data = {
    "contract_id": "my_token_001",
    "name": "My Token",
    "interface_id": "RGB20Interface",
    "specification_id": "RGB20Spec",
    "genesis_proof": "base64_proof_data",
    "schema_type": "cfa"
}

result = rgb_manager.register_rgb_contract(contract_data)
print(f"Contract registered: {result['contract_id']}")

# Create RGB allocation
allocation_data = {
    "contract_id": "my_token_001",
    "vtxo_id": "vtxo_123",
    "owner_pubkey": "npub1user...",
    "amount": 1000000
}

allocation = rgb_manager.create_rgb_allocation(allocation_data)
print(f"Allocation created: {allocation['allocation_id']}")
```

### TypeScript SDK

```typescript
import { GatewayClient } from "arkrelay-sdk-ts";

const client = new GatewayClient("http://localhost:8000");

// Register RGB contract
const contractData = {
  contract_id: "my_token_001",
  name: "My Token",
  interface_id: "RGB20Interface",
  specification_id: "RGB20Spec",
  genesis_proof: "base64_proof_data",
  schema_type: "cfa"
};

const contract = await client.post("/rgb/contracts", contractData);
console.log("Contract registered:", contract.data.contract_id);

// Create RGB allocation
const allocationData = {
  contract_id: "my_token_001",
  vtxo_id: "vtxo_123",
  owner_pubkey: "npub1user...",
  amount: 1000000
};

const allocation = await client.post("/rgb/allocations", allocationData);
console.log("Allocation created:", allocation.data.allocation_id);
```

## Nostr Integration

RGB operations can be integrated with the existing Nostr event system:

### RGB Contract Registration (Kind 31510)
```json
{
  "action_id": "rgb_contract_register_001",
  "type": "rgb:contract_register",
  "params": {
    "contract_id": "my_token_001",
    "name": "My Token",
    "interface_id": "RGB20Interface",
    "specification_id": "RGB20Spec",
    "genesis_proof": "base64_proof",
    "schema_type": "cfa",
    "metadata": {"description": "My RGB token"}
  },
  "expires_at": 1735689600
}
```

### RGB Transfer (Kind 31510)
```json
{
  "action_id": "rgb_transfer_001",
  "type": "rgb:transfer",
  "params": {
    "contract_id": "my_token_001",
    "allocation_id": "vtxo_123_my_token_001",
    "to_pubkey": "npub1receiver...",
    "amount": 500000
  },
  "expires_at": 1735689600
}
```

## Development Workflow

### 1. Contract Creation

1. **Prepare Genesis Proof**: Create RGB genesis proof using RGB SDK
2. **Register Contract**: Use `/rgb/contracts` endpoint
3. **Create Asset**: System automatically creates corresponding asset
4. **Verify Registration**: Check contract status with `/rgb/contracts/{id}`

### 2. Asset Issuance

1. **Create VTXO**: Use `/rgb/vtxos/create` with RGB contract
2. **Create Allocation**: System creates RGB allocation within VTXO
3. **Mint Tokens**: Issue tokens to user VTXOs
4. **Track Balances**: Monitor via `/rgb/allocations` endpoint

### 3. Transfer Operations

1. **Validate State**: Ensure VTXO and allocation are valid
2. **Create Transfer**: Use `/rgb/allocations/transfer` endpoint
3. **Update Allocations**: System manages allocation transfers
4. **Broadcast Confirmation**: Nostr event kind 31340 for success

### 4. Proof Management

1. **Generate Proofs**: Create RGB proofs for state transitions
2. **Validate Proofs**: Use `/rgb/proofs/validate` endpoint
3. **Store Proofs**: Maintain proof data in VTXOs
4. **Audit Trail**: Track all proof validations

## Best Practices

### Security

1. **Proof Validation**: Always validate RGB proofs before accepting transfers
2. **State Verification**: Verify RGB state consistency regularly
3. **Access Control**: Implement proper authorization for RGB operations
4. **Audit Logging**: Maintain comprehensive logs of RGB operations

### Performance

1. **Batch Operations**: Use VTXO splitting for multiple RGB operations
2. **Caching**: Cache RGB contract metadata and validation results
3. **Async Processing**: Use background jobs for heavy RGB computations
4. **Monitoring**: Track RGB operation metrics and performance

### Error Handling

1. **Graceful Degradation**: Handle RGB failures without affecting base VTXO operations
2. **Retry Logic**: Implement retry mechanisms for transient RGB failures
3. **User Feedback**: Provide clear error messages for RGB operation failures
4. **Recovery Procedures**: Document recovery procedures for RGB state corruption

## Testing

### Unit Tests

```python
# Test RGB contract registration
def test_register_rgb_contract():
    rgb_manager = get_rgb_manager()
    contract_data = {
        "contract_id": "test_contract",
        "name": "Test Contract",
        "interface_id": "RGB20Interface",
        "specification_id": "RGB20Spec",
        "genesis_proof": "test_proof",
        "schema_type": "cfa"
    }

    result = rgb_manager.register_rgb_contract(contract_data)
    assert result['contract_id'] == "test_contract"
    assert result['schema_type'] == "cfa"
```

### Integration Tests

```python
# Test RGB allocation transfer
def test_rgb_allocation_transfer():
    # Setup: Create contract and initial allocation
    # Execute: Transfer allocation
    # Verify: New allocation created and state updated
    pass
```

### Load Testing

Test RGB operations under various loads:
- Contract registration throughput
- Allocation creation rate
- Transfer operation latency
- Proof validation performance

## Troubleshooting

### Common Issues

1. **Contract Registration Fails**
   - Check genesis proof format
   - Verify interface and specification IDs
   - Ensure contract ID uniqueness

2. **Allocation Creation Errors**
   - Verify VTXO exists and is available
   - Check contract is active
   - Validate amount limits

3. **Transfer Failures**
   - Verify allocation ownership
   - Check sufficient balance
   - Validate recipient pubkey format

4. **Proof Validation Issues**
   - Check proof data encoding
   - Verify contract state consistency
   - Ensure proof is not expired

### Debug Tools

1. **RGB Health Check**: `GET /rgb/health`
2. **System Statistics**: `GET /rgb/stats`
3. **VTXO Validation**: `GET /rgb/vtxos/{id}/validate`
4. **Contract Verification**: Check contract state and metadata

## Migration Guide

### From Existing VTXO System

1. **Database Migration**: Run Alembic migration for RGB tables
2. **Asset Updates**: Existing assets can be enhanced with RGB metadata
3. **VTXO Compatibility**: Existing VTXOs remain functional
4. **API Changes**: RGB endpoints are additive, no breaking changes

### Data Migration

```python
# Example: Enhance existing asset with RGB support
from core.models import Asset, get_session

session = get_session()
asset = session.query(Asset).filter_by(asset_id="existing_asset").first()

if asset:
    asset.rgb_contract_id = "new_rgb_contract"
    asset.is_rgb_enabled = True
    session.commit()
```

## Future Enhancements

### Planned Features

1. **Advanced Schema Support**: RGBv0.2 and beyond
2. **Batch RGB Operations**: Multi-contract operations
3. **Cross-Contract Transfers**: Atomic swaps between RGB contracts
4. **RGB Lightning Integration**: RGB assets in Lightning channels
5. **Enhanced Proof System**: ZK-proof integration

### Development Roadmap

1. **Phase 1**: Basic RGB functionality (Current)
2. **Phase 2**: Advanced features and optimizations
3. **Phase 3**: Lightning integration and scaling
4. **Phase 4**: Cross-chain RGB support

## Support

For RGB integration support:

1. **Documentation**: This guide and API reference
2. **Examples**: GitHub repository with sample implementations
3. **Community**: Discord/Telegram for developer discussions
4. **Issues**: GitHub issues for bug reports and feature requests

## Resources

- [RGB Protocol Specification](https://github.com/RGB-WG/rgb-spec)
- [RGB SDK Documentation](https://github.com/RGB-WG/rgb-sdk)
- [Bitcoin Taproot Assets](https://github.com/lightninglabs/taproot-assets)
- [Ark Relay Documentation](../README.md)