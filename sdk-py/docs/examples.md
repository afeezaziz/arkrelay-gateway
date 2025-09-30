# Examples and Use Cases

This document provides comprehensive examples and use cases for the ArkRelay Python SDK, organized by user type and functionality.

## Table of Contents

- [Wallet Developer Examples](#wallet-developer-examples)
- [Solver Developer Examples](#solver-developer-examples)
- [Complete Flow Examples](#complete-flow-examples)
- [Advanced Patterns](#advanced-patterns)

## Wallet Developer Examples

### 1. Basic Wallet Integration

```python
from sdk import GatewayClient
from sdk.wallet_utils import create_intent, monitor_session

# Initialize client
client = GatewayClient("https://gateway.arkrelay.io")

# Create a Lightning lift intent
intent = create_intent(
    action_id="lift_001",
    intent_type="lightning:lift",
    params={
        "asset_id": "gBTC",
        "amount": 100000,  # 100k sats
        "fee_asset_id": "gBTC",
        "fee_amount": 10
    }
)

# User signs and publishes as Nostr event 31510
# See: ../../examples/lightning_operations.py
```

### 2. Handling Nostr Events

```python
from sdk.nostr_utils import verify_event, decrypt_dm

# Verify incoming 31511 challenge
def handle_challenge(event):
    is_valid, _ = verify_event(event)
    if not is_valid:
        raise Exception("Invalid signature")

    # Decrypt the challenge content
    challenge_data = decrypt_dm(event["content"])
    session_id = challenge_data["session_id"]

    # Present to user for signing
    return present_signing_challenge(challenge_data)

# Send 31512 response
def send_signature(session_id, signature, payload_ref):
    response = {
        "session_id": session_id,
        "type": "sign_payload",
        "signature": signature,
        "payload_ref": payload_ref
    }
    # Encrypt and send as DM to gateway
    return send_nostr_dm(response, gateway_pubkey)
```

### 3. Service Request Pattern

```python
from examples.service_requests import ServiceRequestDemo

# Initialize service request handler
service_demo = ServiceRequestDemo(
    gateway_url="https://gateway.arkrelay.io",
    user_npub="npub1user...",
    gateway_npub="npub1gateway..."
)

# Sync user state
sync_result = service_demo.execute_sync_state_flow()
user_vtxos = sync_result["response"]["user_vtxos"]
user_balances = sync_result["response"]["user_balances"]

# Query specific assets
balance_result = service_demo.execute_balance_query_flow(["gBTC", "gUSD"])
```

## Solver Developer Examples

### 1. Basic Solver Setup

```python
from sdk import GatewayClient
from sdk.solver_flows import (
    accept_intent_and_issue_challenge,
    start_and_wait_ceremony,
    monitor_ceremony
)

# Initialize solver client
client = GatewayClient("https://gateway.arkrelay.io", retry_enabled=True)

# Listen for 31510 intents
def handle_intent(nostr_event):
    intent = json.loads(nostr_event["content"])

    # Validate intent
    if not validate_intent(intent):
        return

    # Create session and issue challenge
    result = accept_intent_and_issue_challenge(
        client,
        user_pubkey=nostr_event["pubkey"],
        intent=intent
    )

    # Start ceremony and wait for completion
    success, status = start_and_wait_ceremony(
        client,
        result["session_id"],
        timeout=120
    )

    if success:
        finalize_transaction(result["session_id"])
```

### 2. VTXO Management

```python
from examples.vtxo_split_operations import VtxoSplitOperationsDemo

# Initialize VTXO operations
vtxo_demo = VtxoSplitOperationsDemo("https://gateway.arkrelay.io")

# Split VTXO for optimal payment execution
split_result = vtxo_demo.execute_split_flow(
    vtxo_id="vtxo_large_001",
    split_amounts=[200000, 300000],
    asset_id="gBTC"
)

# Multi-VTXO transaction for large transfers
multi_result = vtxo_demo.execute_multi_vtxo_flow(
    asset_id="gUSD",
    total_amount=400000000,
    recipient_pubkey="npub1recipient..."
)

# Optimal change management
change_result = vtxo_demo.execute_optimal_change_flow(
    asset_id="gBTC",
    amount_needed=123456,
    recipient_pubkey="npub1recipient..."
)
```

### 3. Protocol Integration (Lending Example)

```python
class LendingSolver:
    def __init__(self, gateway_url):
        self.client = GatewayClient(gateway_url)
        self.db = LendingDatabase()

    def handle_deposit(self, intent):
        # Validate deposit intent
        params = intent["params"]
        asset_id = params["asset_id"]
        amount = params["amount"]

        # Check market conditions
        if not self.db.is_market_open(asset_id):
            return self.reject_intent(intent, "Market closed")

        # Calculate interest rate
        rate = self.db.get_deposit_rate(asset_id, amount)

        # Create session for signature
        result = accept_intent_and_issue_challenge(
            self.client,
            user_pubkey=intent["user_pubkey"],
            intent=intent
        )

        # Monitor ceremony completion
        success, status = start_and_wait_ceremony(self.client, result["session_id"])

        if success:
            # Record deposit in lending database
            self.db.record_deposit(
                user_pubkey=intent["user_pubkey"],
                asset_id=asset_id,
                amount=amount,
                rate=rate
            )

            # Update user position
            self.db.update_position(
                user_pubkey=intent["user_pubkey"],
                asset_id=asset_id,
                amount=amount
            )
```

### 4. AMM Swap Integration

```python
class AMMSolver:
    def __init__(self, gateway_url):
        self.client = GatewayClient(gateway_url)
        self.amm = AMMEngine()

    def handle_swap(self, intent):
        params = intent["params"]
        pool_id = params["pool_id"]
        in_asset = params["in_asset"]
        in_amount = params["in_amount"]
        min_out_amount = params["min_out_amount"]

        # Calculate swap output
        out_amount = self.amm.calculate_output(pool_id, in_asset, in_amount)

        # Check slippage
        if out_amount < min_out_amount:
            return self.reject_intent(intent, "Insufficient output")

        # Check liquidity
        if not self.amm.has_sufficient_liquidity(pool_id, in_asset, in_amount):
            return self.reject_intent(intent, "Insufficient liquidity")

        # Execute swap
        result = accept_intent_and_issue_challenge(
            self.client,
            user_pubkey=intent["user_pubkey"],
            intent=intent
        )

        # Monitor and finalize
        success, status = start_and_wait_ceremony(self.client, result["session_id"])

        if success:
            self.amm.execute_swap(
                pool_id=pool_id,
                user_pubkey=intent["user_pubkey"],
                in_asset=in_asset,
                in_amount=in_amount,
                out_amount=out_amount
            )
```

## Complete Flow Examples

### 1. Complete Lightning Lift Flow

```python
# Step 1: User initiates lift request
def complete_lift_flow(user_pubkey, amount_sats):
    # Create service request (31500)
    service_demo = ServiceRequestDemo(gateway_url, user_pubkey, gateway_npub)
    service_request = service_demo.create_service_request(
        "lift_lightning",
        asset_id="gBTC",
        amount=amount_sats
    )

    # Gateway responds with invoice (31501)
    # User pays Lightning invoice

    # Create action intent (31510)
    lightning_demo = LightningOperationsDemo(gateway_url)
    intent = lightning_demo.create_lift_intent(amount_sats)

    # Solver handles the flow
    solver = LightningSolver(gateway_url)
    result = solver.handle_lift_intent(intent)

    # Monitor completion
    completion = lightning_demo.monitor_session(result["session_id"])

    return completion
```

### 2. Complete VTXO Split and Transfer

```python
def complete_split_and_transfer(vtxo_id, amounts, recipient_pubkey):
    # Initialize operations
    vtxo_demo = VtxoSplitOperationsDemo(gateway_url)

    # Split VTXO
    split_result = vtxo_demo.execute_split_flow(vtxo_id, amounts)

    # Monitor split completion
    split_completion = monitor_ceremony(
        client,
        split_result["session_id"],
        timeout=60
    )

    if split_completion["status"] == "completed":
        # Transfer split VTXOs
        for split_vtxo_id in split_completion["vtxo_ids"]:
            transfer_result = vtxo_demo.execute_multi_vtxo_flow(
                asset_id="gBTC",
                total_amount=amounts[0],  # Example amount
                recipient_pubkey=recipient_pubkey
            )

            # Monitor transfer
            transfer_completion = monitor_ceremony(
                client,
                transfer_result["session_id"],
                timeout=60
            )

            if transfer_completion["status"] != "completed":
                raise Exception("Transfer failed")

    return True
```

## Advanced Patterns

### 1. Multi-Protocol Solver

```python
class MultiProtocolSolver:
    def __init__(self, gateway_url):
        self.client = GatewayClient(gateway_url)
        self.protocols = {
            "lend:lend": LendingProtocol(),
            "amm:swap": AMMProtocol(),
            "vault:deposit": VaultProtocol()
        }

    def handle_intent(self, intent):
        protocol_type = intent["type"]

        if protocol_type not in self.protocols:
            return self.reject_intent(intent, "Unsupported protocol")

        protocol = self.protocols[protocol_type]

        # Protocol-specific validation
        if not protocol.validate_intent(intent):
            return self.reject_intent(intent, "Invalid intent for protocol")

        # Execute protocol flow
        return protocol.execute_intent(self.client, intent)
```

### 2. Error Handling and Recovery

```python
class RobustSolver:
    def __init__(self, gateway_url):
        self.client = GatewayClient(gateway_url, retry_enabled=True)
        self.error_handlers = {
            "insufficient_balance": self.handle_insufficient_balance,
            "invalid_signature": self.handle_invalid_signature,
            "network_timeout": self.handle_network_timeout
        }

    def handle_error(self, session_id, error_code, error_message):
        if error_code in self.error_handlers:
            return self.error_handlers[error_code](session_id, error_message)
        else:
            # Log unknown errors
            self.log_error(session_id, error_code, error_message)
            return {"status": "failed", "reason": error_message}

    def handle_insufficient_balance(self, session_id, error_message):
        # Get user balance
        balance = self.get_user_balance(session_id)

        # Suggest alternative amounts
        suggestions = self.calculate_alternative_amounts(balance)

        # Notify user
        return self.notify_user(session_id, {
            "error": "insufficient_balance",
            "suggestions": suggestions,
            "current_balance": balance
        })
```

### 3. Performance Monitoring

```python
class MonitoringSolver:
    def __init__(self, gateway_url):
        self.client = GatewayClient(gateway_url)
        self.metrics = MetricsCollector()

    def handle_intent_with_monitoring(self, intent):
        start_time = time.time()

        try:
            result = self.handle_intent(intent)

            # Record success metrics
            self.metrics.record_success(
                intent_type=intent["type"],
                duration=time.time() - start_time
            )

            return result

        except Exception as e:
            # Record failure metrics
            self.metrics.record_failure(
                intent_type=intent["type"],
                error=str(e),
                duration=time.time() - start_time
            )

            raise
```

## Integration Checklist

### For Wallet Developers
- [ ] Implement Nostr event handling (31510, 31511, 31512)
- [ ] Add user interface for signing challenges
- [ ] Handle session monitoring and status updates
- [ ] Implement error handling and user notifications
- [ ] Add transaction history and balance display

### For Solver Developers
- [ ] Set up Nostr event ingestion
- [ ] Implement intent validation
- [ ] Create protocol-specific business logic
- [ ] Add database integration for state management
- [ ] Implement monitoring and alerting
- [ ] Add performance metrics and logging

### Common Requirements
- [ ] Error handling and retry mechanisms
- [ ] Rate limiting and security measures
- [ ] Testing and validation
- [ ] Documentation and examples
- [ ] Monitoring and observability

## Additional Resources

- [Nostr Event Flows Documentation](../../docs/examples/nostr_flows.md)
- [Solver Integration Guide](../../docs/developers/solver-integration.md)
- [Complete Examples](../../examples/)
- [API Reference](../README.md)