# ArkRelay Python SDK Examples

This directory contains comprehensive examples demonstrating how to use the ArkRelay Python SDK for wallet and solver development.

## Available Examples

### Lightning Operations
```bash
# gBTC Lift (Lightning → VTXO)
python ../../examples/lightning_operations.py --gateway http://localhost:8000 lift --amount 100000 --user-npub npub1user...

# gBTC Land (VTXO → Lightning)
python ../../examples/lightning_operations.py --gateway http://localhost:8000 land --amount 50000 --invoice lnbc... --user-npub npub1user...

# Monitor session status
python ../../examples/lightning_operations.py --gateway http://localhost:8000 monitor --session-id sess_123 --user-npub npub1user...
```

### VTXO Operations
```bash
# Split VTXO into smaller denominations
python ../../examples/vtxo_split_operations.py --gateway http://localhost:8000 split --vtxo vtxo_123 --amounts 200000,300000

# Multi-VTXO transactions
python ../../examples/vtxo_split_operations.py --gateway http://localhost:8000 multi-send --asset gUSD --amount 400000000 --recipient npub1recipient...

# Optimal change management
python ../../examples/vtxo_split_operations.py --gateway http://localhost:8000 optimal-change --asset gBTC --amount 123456 --recipient npub1recipient...
```

### Service Request Patterns
```bash
# State synchronization
python ../../examples/service_requests.py --gateway http://localhost:8000 sync-state --user-npub npub1user... --gateway-npub npub1gateway...

# Balance queries
python ../../examples/service_requests.py --gateway http://localhost:8000 query-balances --assets gBTC gUSD --user-npub npub1user... --gateway-npub npub1gateway...
```

## SDK Integration

### Using Examples in Your Code

```python
from sdk import GatewayClient
from sdk.solver_flows import accept_intent_and_issue_challenge, start_and_wait_ceremony
from examples.lightning_operations import LightningOperationsDemo

# For wallet developers
client = GatewayClient("http://localhost:8000")
lightning_demo = LightningOperationsDemo("http://localhost:8000")

# Execute lift flow
result = lightning_demo.execute_lift_flow(100000, "gBTC")
print(f"Lift initiated: {result['session_id']}")

# For solver developers
intent = {"action_id": "uuid...", "type": "amm:swap", "params": {}, "expires_at": 1735689600}
out = accept_intent_and_issue_challenge(client, user_pubkey="npub1...", intent=intent)
ok, status = start_and_wait_ceremony(client, out["session_id"], timeout=120)
```

## Key Concepts

### Nostr Event Flow
- **31500**: Service requests (user → gateway)
- **31501**: Service responses (gateway → user)
- **31502**: Service notifications (ongoing updates)
- **31510**: Action intents (user → gateway)
- **31511/31512**: Signing challenges/responses
- **31340**: Transaction confirmations (gateway → public)
- **31341**: Transaction failures (gateway → user)

### VTXO Management
- **Split**: Divide large VTXOs into smaller denominations
- **Multi-VTXO**: Combine multiple VTXOs for larger transfers
- **Optimal Change**: Create change VTXOs efficiently

### Architecture Patterns
- **Dumb Gateway**: Gateway handles only VTXO/signing, solvers handle business logic
- **Solver Integration**: External DeFi services using gateway for settlement
- **Asset Support**: Multi-asset support with Taproot asset tagging

## Documentation

- [Nostr Event Flows](../../docs/examples/nostr_flows.md) - Complete event sequences
- [Solver Integration Guide](../../docs/developers/solver-integration.md) - Solver development guide
- [Solver Guide](../../docs/developers/solver-guide.md) - Advanced integration patterns

## Development

### Running Examples

1. Install the SDK:
```bash
cd sdk-py
pip install -e .
```

2. Run examples:
```bash
# From examples directory
python ../../examples/lightning_operations.py --help
```

### Contributing

When adding new examples:
1. Follow the existing structure
2. Include comprehensive CLI interfaces
3. Add error handling and logging
4. Document the Nostr event flows
5. Update this README

## Support

For issues and questions:
- Check the [main documentation](../../docs/)
- Review [Nostr event flows](../../docs/examples/nostr_flows.md)
- See [solver integration guide](../../docs/developers/solver-integration.md)