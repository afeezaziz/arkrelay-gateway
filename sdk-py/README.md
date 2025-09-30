# ArkRelay Python SDK (arkrelay-sdk)

Python SDK for interacting with ArkRelay Gateway: sessions/challenges, ceremony polling, assets helpers, and Nostr (BIP340) utilities.

## Install (local)

```bash
cd sdk-py
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Usage

### Basic Usage

```python
from sdk import GatewayClient
from sdk.solver_flows import accept_intent_and_issue_challenge, start_and_wait_ceremony

client = GatewayClient("http://localhost:8000", retry_enabled=True)
intent = {"action_id":"uuid...","type":"amm:swap","params":{},"expires_at":1735689600}
out = accept_intent_and_issue_challenge(client, user_pubkey="npub1...", intent=intent)
ok, status = start_and_wait_ceremony(client, out["session_id"], timeout=120)
print(ok, status)
```

### Lightning Operations (for Wallet Developers)

```python
from examples.lightning_operations import LightningOperationsDemo

lightning = LightningOperationsDemo("http://localhost:8000")
result = lightning.execute_lift_flow(100000, "gBTC")
print(f"Lift initiated: {result['session_id']}")
```

### VTXO Operations (for Solver Developers)

```python
from examples.vtxo_split_operations import VtxoSplitOperationsDemo

vtxo_demo = VtxoSplitOperationsDemo("http://localhost:8000")
result = vtxo_demo.execute_multi_vtxo_flow("gUSD", 400000000, "npub1recipient...")
print(f"Multi-VTXO flow: {result['session_id']}")
```

### Service Request Patterns

```python
from examples.service_requests import ServiceRequestDemo

service_demo = ServiceRequestDemo(
    gateway_url="http://localhost:8000",
    user_npub="npub1user...",
    gateway_npub="npub1gateway..."
)
result = service_demo.execute_sync_state_flow()
```

NIP-01 verify:

```python
from sdk import verify_event
ok, info = verify_event(event)
```

## Examples and Documentation

### Available Examples
- **Lightning Operations**: Complete gBTC lift/land flows (`examples/lightning_operations.py`)
- **VTXO Operations**: Splitting, multi-VTXO transactions, optimal change (`examples/vtxo_split_operations.py`)
- **Service Requests**: 31500/31501/31502 patterns (`examples/service_requests.py`)

### Running Examples
```bash
# Lightning operations
python ../../examples/lightning_operations.py --help

# VTXO operations
python ../../examples/vtxo_split_operations.py --help

# Service request patterns
python ../../examples/service_requests.py --help
```

### Documentation
- [Examples Guide](examples/README.md) - Complete usage examples
- [Examples Documentation](docs/examples.md) - In-depth examples and patterns
- [Nostr Event Flows](../../docs/examples/nostr_flows.md) - Complete event sequences
- [Solver Integration Guide](../../docs/developers/solver-integration.md) - Solver development

## Architecture Patterns

### For Wallet Developers
- Lightning lift/land operations
- Service request patterns (31500/31501/31502)
- Nostr event handling (31510/31511/31512)
- Session monitoring and status updates

### For Solver Developers
- VTXO management (splitting, multi-VTXO transactions)
- Protocol integration (lending, AMM, vaults)
- Multi-protocol support
- Error handling and recovery

## Publish (PyPI)

1) Build

```bash
cd sdk-py
python -m pip install --upgrade build twine
python -m build
```

2) Upload

```bash
python -m twine upload dist/*
```

Update `pyproject.toml` metadata (name, version, authors, URLs) before publishing.

## Releasing (CI/CD)

This repo includes a GitHub Actions workflow to publish the SDK to PyPI when you push a tag of the form `sdk-py-vX.Y.Z`.

1) Create a PyPI API token and add it to the repo as `PYPI_API_TOKEN` secret.
2) Bump the version in `sdk-py/pyproject.toml`.
3) Create and push a tag, e.g.:

```bash
git tag sdk-py-v0.1.0
git push origin sdk-py-v0.1.0
```

The workflow at `.github/workflows/release.yml` will build and publish `gateway/sdk-py` using the token.
