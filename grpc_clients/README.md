# gRPC Client Package

This package provides unified gRPC client interfaces for communicating with ARKD, TAPD, and LND daemons in the Ark Relay Gateway.

## Structure

```
grpc_clients/
├── __init__.py           # Package exports
├── grpc_client.py        # Core client manager and utilities
├── arkd_client.py        # ARKD daemon client
├── tapd_client.py        # TAPD daemon client
└── lnd_client.py         # LND daemon client
```

## Features

### Core Infrastructure
- **Unified Interface**: Single point of access to all gRPC services
- **Connection Pooling**: Efficient connection handling with thread safety
- **Retry Logic**: Exponential backoff retry mechanism for failed calls
- **Circuit Breaker**: Protection against cascading failures
- **Health Monitoring**: Continuous health checking of all services

### Client Implementations
- **ARKD Client**: VTXO management, transaction signing, session management
- **TAPD Client**: Asset management, proof validation, Lightning integration
- **LND Client**: Lightning operations, balance tracking, channel management

## Usage

### Basic Usage
```python
from grpc_clients import get_grpc_manager, ServiceType

# Get gRPC manager
manager = get_grpc_manager()

# Check service health
health_status = manager.health_check_all()

# Get specific client
arkd_client = manager.get_client(ServiceType.ARKD)

# Use client methods
vtxos = arkd_client.list_vtxos(owner_pubkey="user_pubkey")
```

### Error Handling
```python
try:
    client = manager.get_client(ServiceType.ARKD)
    result = client.create_vtxos(amount=100000, asset_id="test_asset")
except ConnectionError as e:
    # Handle connection issues
    logger.error(f"Service unavailable: {e}")
except Exception as e:
    # Handle other errors
    logger.error(f"Operation failed: {e}")
```

### Flask Integration
```python
# In Flask routes
from grpc_clients import get_grpc_manager

@app.route('/balances')
def get_balances():
    manager = get_grpc_manager()
    lnd_client = manager.get_client(ServiceType.LND)
    balances = lnd_client.get_total_balance()
    return jsonify(balances)
```

## Configuration

### Environment Variables
```bash
# ARKD Configuration
ARKD_HOST=localhost
ARKD_PORT=10009
ARKD_TLS_CERT=/path/to/tls.cert
ARKD_MACAROON=/path/to/macaroon

# TAPD Configuration
TAPD_HOST=localhost
TAPD_PORT=10029
TAPD_TLS_CERT=/path/to/tls.cert
TAPD_MACAROON=/path/to/macaroon

# LND Configuration
LND_HOST=localhost
LND_PORT=10009
LND_TLS_CERT=/path/to/tls.cert
LND_MACAROON=/path/to/macaroon

# gRPC Settings
GRPC_MAX_MESSAGE_LENGTH=4194304
GRPC_TIMEOUT_SECONDS=30
```

## Available Methods

### ARKD Client
- `create_vtxos(amount, asset_id, count)` - Create new VTXOs
- `get_vtxo_info(vtxo_id)` - Get VTXO information
- `list_vtxos(owner_pubkey, asset_id, status)` - List VTXOs with filters
- `spend_vtxos(vtxo_ids, destination_pubkey, amount, asset_id)` - Prepare VTXO spending
- `prepare_signing_request(session_id, challenge_type, context)` - Prepare signing request
- `submit_signatures(session_id, signatures)` - Submit signatures
- `get_session_status(session_id)` - Get session status
- `get_network_info()` - Get network information
- `get_pending_transactions()` - Get pending transactions
- `create_commitment_transaction(l2_changes)` - Create L1 commitment transaction

### TAPD Client
- `list_assets(include_spent)` - List all assets
- `get_asset_info(asset_id)` - Get asset information
- `issue_asset(name, ticker, amount, asset_type, meta_data)` - Issue new asset
- `get_asset_balances()` - Get all asset balances
- `get_asset_balance(asset_id)` - Get specific asset balance
- `get_asset_proof(asset_id, script_key)` - Get asset proof
- `verify_asset_proof(proof_data)` - Verify asset proof
- `export_proof(asset_id, script_key)` - Export proof
- `import_proof(proof_data)` - Import proof
- `create_asset_invoice(asset_id, amount, description, expiry)` - Create Lightning invoice
- `pay_asset_invoice(invoice, asset_id)` - Pay Lightning invoice
- `send_asset(asset_id, amount, destination)` - Send asset
- `mint_asset(asset_id, amount)` - Mint additional asset units

### LND Client
- `get_lightning_balance()` - Get Lightning channel balances
- `get_onchain_balance()` - Get on-chain balance
- `get_total_balance()` - Get combined balance information
- `list_channels(active_only)` - List Lightning channels
- `open_channel(pubkey, amount, private)` - Open new channel
- `close_channel(channel_id, force)` - Close channel
- `add_invoice(amount, memo, expiry)` - Create Lightning invoice
- `list_invoices(pending_only)` - List invoices
- `lookup_invoice(payment_hash)` - Lookup invoice
- `send_payment(payment_request, amount)` - Send payment
- `list_payments()` - List payments
- `get_info()` - Get node information
- `list_peers()` - List connected peers
- `send_onchain(address, amount, sat_per_byte)` - Send on-chain transaction
- `new_address(address_type)` - Generate new address

## Error Handling and Resilience

### Circuit Breaker Pattern
- **Failure Threshold**: Opens circuit after configurable number of failures
- **Recovery Timeout**: Automatically attempts recovery after timeout period
- **Half-Open State**: Tests service availability before fully reopening

### Retry Logic
- **Exponential Backoff**: Increasing delays between retry attempts
- **Maximum Retries**: Configurable limit on retry attempts
- **gRPC Error Handling**: Specific handling for gRPC error codes

### Connection Management
- **Thread Safety**: Thread-safe connection handling
- **Graceful Degradation**: Read-only mode when services unavailable
- **Automatic Reconnection**: Configurable reconnection logic

## Testing

Run tests with:
```bash
uv run python test_grpc_clients.py
```

Available test classes:
- `TestCircuitBreaker` - Circuit breaker functionality
- `TestConfiguration` - Configuration validation
- `TestGrpcClientManager` - Client manager initialization
- `TestDataStructures` - Data structure integrity

## Architecture Benefits

1. **Unified Interface**: Single point of access to all gRPC services
2. **Resilience**: Built-in error handling and recovery mechanisms
3. **Scalability**: Connection pooling and efficient resource management
4. **Testability**: Clean interfaces for unit testing
5. **Monitoring**: Health checks and status reporting
6. **Security**: Proper handling of TLS certificates and macaroons

This implementation provides a solid foundation for the subsequent phases of the Ark Relay Gateway development.