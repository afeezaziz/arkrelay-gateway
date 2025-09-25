# Testing Strategy and Improvement Plan

Last updated: 2025-09-24 22:54 +08:00

This document outlines how to run tests in this repo, what currently runs by default, and a prioritized action plan to improve stability, coverage, and confidence.

## Current Baseline

- Default command: `uv run pytest -q`
- Pytest config: `pytest.ini`
  - Selects a stable subset via markers and a `-k` filter to exclude heavy/flake-prone areas
  - Excludes by marker: `integration`, `slow`, `e2e`, `load`, `performance`, `failure`, `stress`
  - Excludes by keyword (via `-k`): `nostr`, `lightning`, `session_manager`, `session_management`, `app`, `grpc`, `lnd`, `tapd`, `arkd`, `end_to_end`, `nigiri`, `phase5`, `error_recovery`, `failure_scenarios`, `security`, `performance`, `load`
- Latest run (baseline, stable subset): 209 passed, 0 failed, 3 warnings, ~9s
- Suites covered in baseline:
  - `tests/test_asset_manager.py`
  - `tests/test_core_config.py`
  - `tests/test_models.py`
  - `tests/test_signing_orchestrator.py`
  - `tests/test_signing_orchestrator_simple.py`
  - `tests/test_transaction_processor.py`
  - `tests/test_transaction_processor_simple.py`

## How to Run Tests

- Default stable subset (recommended for quick signal):
  - `uv run pytest -q`

- Verbose run with short tracebacks:
  - `uv run pytest -v --tb=short`

- Specific files or tests:
  - `uv run pytest tests/test_asset_manager.py -q`
  - `uv run pytest tests/test_asset_manager.py::TestAssetManager::test_transfer_assets_success -q`

- Include excluded categories on-demand (override filters):
  - Integration (example): `uv run pytest -v -m integration`
  - End-to-End: `uv run pytest -v -m e2e`
  - Performance: `uv run pytest -v -m performance`
  - Stress: `uv run pytest -v -m stress`

- Lightning-focused harness (integration/perf helpers):
  - `uv run python tests/run_lightning_tests.py --integration -v`
  - `uv run python tests/run_lightning_tests.py --performance -v`

- Coverage:
  - Quick coverage: `uv run pytest --cov=core --cov=grpc_clients --cov-report=term-missing -q`
  - Full coverage with HTML: `uv run pytest --cov=. --cov-report=term-missing --cov-report=html -v`

## Test Infrastructure

- Central config: `pytest.ini`
  - Defines default filters and markers to maintain fast, consistent signal

- Global fixtures and environment: `tests/conftest.py`
  - Loads DB fixtures via `pytest_plugins = ["tests.test_database_setup"]`
  - Provides mocks for ARKD/TAPD/LND clients and Lightning helpers

- Database isolation and concurrency: `tests/test_database_setup.py`
  - Provides a per-test SQLite file database to allow concurrency across threads
  - Patches `core.models.get_session`, `core.asset_manager.get_session`, and `core.session_manager.get_session` to return a new `Session` per call bound to the same per-test engine
  - Also patches `builtins.get_session` for components that import a `get_session` alias at module load time
  - This design stabilizes concurrency tests and prevents nested SAVEPOINT conflicts

## Known Warnings and Quick Fixes

- SQLAlchemy deprecation warning for `declarative_base()` in `core/models.py`:
  - Switch to `from sqlalchemy.orm import declarative_base`
  - Replace usage accordingly to remove `MovedIn20Warning`

- Pytest collection warning in `tests/test_utils.py` (`TestConfig` has `__init__`):
  - If intentional utility class, rename to avoid `Test*` prefix or remove `__init__`

## Priority Action Items

### A. Stabilization and Hygiene (Immediate)

1. SQLAlchemy 2.0 deprecation cleanup
   - Update `core/models.py` to import `declarative_base` from `sqlalchemy.orm`
   - Re-run baseline to confirm warnings reduced to 0

2. Test collection hygiene
   - In `tests/test_utils.py`, avoid collecting non-test classes:
     - Option A: rename `TestConfig` to `ConfigTestUtils` (or similar)
     - Option B: remove `__init__` or convert to functions/fixtures

3. Document baseline in CI
   - Ensure CI uses `uv run pytest -q` as the primary quick gate
   - Add a separate workflow job or step for on-demand heavy suites (integration/e2e/perf), not blocking the quick gate

4. Coverage baseline
   - Add a coverage reporting job (non-blocking) using `--cov=core --cov=grpc_clients`
   - Publish `htmlcov/` as an artifact (optional)

Acceptance criteria:
- Baseline run yields 0 warnings
- CI has two lanes: quick gate (stable subset) and optional heavy suites
- Coverage job runs and produces a report

### B. Test Suite Expansion (Short Term)

5. Asset Manager edge cases
   - Add tests for:
     - Negative `reserved_balance` handling in `mint_assets()` and input validation
     - VTXO operations with mismatched `user_pubkey` ownership checks
     - Validation on unusually large `decimal_places` and `asset_type` variants

6. Signing Orchestrator robustness
   - Expand tests for wrong-state transitions, timeouts, and expired sessions
   - Verify Option B compatibility methods and state aliasing are covered (`RESPONSE_RECEIVED` etc.)
   - Add tests for failure paths with clear error messages

7. Transaction Processor correctness under concurrency
   - Add a test to detect potential double-spend-like logical scenarios across threads
   - Property-style randomized tests (optional) for `validate_transaction()` output parsing

8. gRPC client error handling (unit)
   - Add unit tests for `grpc_clients/arkd_client.py` error mapping, especially when `grpc.RpcError` lacks `code()`
   - Confirm spend/signing request error surfaces are covered

Acceptance criteria:
- +10–15 new unit tests across Asset Manager, Orchestrator, and Transaction Processor
- gRPC client error mapping has explicit unit coverage

### C. Heavier Categories as Separate Lanes (Short Term)

9. Integration tests
   - Define a documented command to run integration tests with real daemons
   - Provide a `.env` template section for integration (`ARKD_*`, `LND_*`, `TAPD_*`, `REDIS_URL`, `DATABASE_URL`)

10. End-to-End smoke
   - Add a minimal, hermetic E2E path guarded by `-m e2e`, skippable when dependencies aren’t present

11. Performance and stress
   - Use `tests/run_lightning_tests.py --performance` for quick perf health checks
   - Guard stress runs with `-m stress` and keep them non-blocking in CI

Acceptance criteria:
- Doc section in this file references commands and env requirements
- Heavy lanes are green locally with configured dependencies

### D. Quality and Coverage (Mid Term)

12. Coverage thresholds in CI
   - Configure a soft threshold (e.g., 85% for `core/`) for non-blocking warnings
   - Gradually tighten as suites expand

13. Test parametrization and deduplication
   - Identify repetitive tests in `test_transaction_processor.py` and `test_asset_manager.py`
   - Convert to `@pytest.mark.parametrize` where appropriate

14. Property-based testing (optional)
   - Introduce Hypothesis for transaction parsing/validation and VTXO ID generation fuzzing
   - Keep opt-in for developers, not mandatory in quick gate

Acceptance criteria:
- Coverage report shows stable/improving trend
- Reduced duplication and faster suite execution

### E. Tooling and Process (Mid to Long Term)

15. Flake tracking and promotion process
   - Maintain a small list of temporarily excluded tests
   - Require N consecutive green runs locally/CI before promoting to the quick gate

16. Containerized integration environment
   - Provide a helper script (or `make` target) to spin up integration dependencies via `docker-compose.dev.yml`
   - One command to run: `./scripts/integration_up.sh` then `uv run pytest -v -m integration`

17. Contract tests for external APIs
   - Define minimal contract tests for ARKD/LND/TAPD client request/response shapes using serialized fixtures

Acceptance criteria:
- Documented flake handling policy
- Reproducible integration setup locally

## Markers and Conventions

- Use markers to categorize:
  - `@pytest.mark.unit`
  - `@pytest.mark.integration`
  - `@pytest.mark.e2e`
  - `@pytest.mark.performance`
  - `@pytest.mark.slow`
  - `@pytest.mark.stress`

- Naming conventions:
  - Files: `tests/test_*.py`
  - Classes: `Test*`
  - Functions: `test_*`

- Keep external I/O behind mocks in unit tests. Prefer `core.models.get_session` for session access to remain patchable by test fixtures.

## Troubleshooting

- Unexpected DB session behavior or nested transaction errors:
  - Ensure new code retrieves sessions via `core.models.get_session()`
  - Avoid capturing a session at module import time; fetch per-operation

- Slow tests or timeouts:
  - Check for network calls that aren’t mocked
  - Use smaller datasets and parameterized tests

- Failing integration tests:
  - Verify env vars in `.env`
  - Confirm daemons are reachable

## Quick Checklists

- Before merging:
  - `uv run pytest -q` is green
  - No warnings (or justified with an issue link)

- When adding features:
  - Add unit tests and update this document if new markers or lanes are introduced
  - Consider coverage impact; add tests as needed

---

Questions or proposals for improving this plan? Open a PR updating `TESTING.md` and reference specific files (e.g., `pytest.ini`, `tests/conftest.py`, `tests/test_database_setup.py`).
