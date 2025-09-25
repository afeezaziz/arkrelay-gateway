# ArkRelay Python SDK (arkrelay-sdk)

Python SDK for interacting with ArkRelay Gateway: sessions/challenges, ceremony polling, assets helpers, and Nostr (BIP340) utilities.

## Install (local)

```bash
cd sdk
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Usage

```python
from sdk import GatewayClient
from sdk.solver_flows import accept_intent_and_issue_challenge, start_and_wait_ceremony

client = GatewayClient("http://localhost:8000", retry_enabled=True)
intent = {"action_id":"uuid...","type":"amm:swap","params":{},"expires_at":1735689600}
out = accept_intent_and_issue_challenge(client, user_pubkey="npub1...", intent=intent)
ok, status = start_and_wait_ceremony(client, out["session_id"], timeout=120)
print(ok, status)
```

NIP-01 verify:

```python
from sdk import verify_event
ok, info = verify_event(event)
```

## Publish (PyPI)

1) Build

```bash
cd sdk
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
2) Bump the version in `sdk/pyproject.toml`.
3) Create and push a tag, e.g.:

```bash
git tag sdk-py-v0.1.0
git push origin sdk-py-v0.1.0
```

The workflow at `.github/workflows/release.yml` will build and publish `gateway/sdk` using the token.
