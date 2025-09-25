# Roadmap and Implementation Plan

Last updated: 2025-09-25 12:14 +08:00

This roadmap tracks key milestones for ArkRelay Gateway V1, their status, and near-term priorities. It complements the full PRD and the Testing Strategy.

References
- PRD: ./prd.md
- Testing plan: ./testing.md
- Docs index: ../README.md
- OpenAPI spec: ../../openapi.yaml
- Releasing: ../../RELEASING.md

## Status Overview

- Core architecture: Flask app, RQ workers, scheduler, SQLAlchemy, Redis — established
- gRPC client layer: Unified clients for ARKD, TAPD, LND — baseline in place
- Production hardening: Dockerfile, docker-compose, services runner, ADMIN_API_KEY — done
- OpenAPI (initial): Minimal spec with admin security — done
- Test stability: Baseline stable subset passes (see testing.md) — done

## In Progress

- Nostr orchestration refinements
  - Ensure failure modes map to 31341 failure notices with stable error codes
  - Expand signing session state alias support and analytics hooks
- Operator runbooks and observability
  - Enrich operator guide with alerts, dashboards, and backup runbooks
- SDK documentation polish (Python + TypeScript)
  - Ensure examples align with current API shapes and error surfaces

## Upcoming (Short Term)

- End-to-end flows (happy-path demos)
  - Lift via Lightning → VTXO creation → 31340 confirmation
  - Land via Lightning → VTXO spend → invoice settle → 31340 confirmation
- Transaction processor + orchestrator
  - Broaden unit tests for wrong-state transitions and timeouts
  - Clearer error taxonomy and mapping across layers
- OpenAPI enrichment
  - Flesh out read-only endpoints with schemas and examples
  - Ensure `/admin/*` endpoints include X-Admin-Key security details

Acceptance criteria
- Documented happy-path E2E demo commands and expected outputs
- Enriched OpenAPI describes request/response bodies for helper endpoints
- Unit tests added for orchestrator edge cases and error mapping

## Near-Term (Mid Term)

- L1 settlement coordinator
  - Implement and document workflow, monitoring, and retries
- Integration harness
  - Containerized environment and scripts for running integration suites
- Coverage and quality
  - Add non-blocking coverage reporting in CI and trend tracking

Acceptance criteria
- Settlement task runs on schedule with observable metrics and logs
- Reproducible integration setup with documented env vars
- Coverage report generated in CI (non-blocking)

## Dependencies and Risks

- External daemons (ARKD, TAPD, LND, bitcoind) availability and version drift
- Nostr ecosystem changes (NIP variants for encrypted DMs and auth)
- Resource constraints for performance and stress tests

Mitigations
- Circuit breakers and retries on gRPC boundaries
- Version pinning and contract tests for clients
- Separate CI lanes for heavy suites and local opt-in scripts

## Change Log

- 2025-09-25: Initial roadmap created and linked from docs index
