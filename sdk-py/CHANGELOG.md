# Changelog

All notable changes to the ArkRelay Python SDK will be documented in this file.

The format is based on Keep a Changelog and this project adheres to Semantic Versioning.

## [Unreleased]
- Add more typed models and schemas.
- Provide optional OpenAPI-generated clients once the spec is enriched.

## [0.1.1] - 2025-09-25
### Changed
- Python 3.9 compatibility: replaced PEP 604 unions with `Optional[...]` and added `NotRequired` fallback via `typing_extensions`.
- Improved packaging/build verifications; local build+install import sanity now covered in CI and release workflow.

### Fixed
- Adjusted examples to import SDK from `sdk-py` path during local development.

## [0.1.0] - 2025-09-25
### Added
- Initial Python SDK package (`arkrelay-sdk`).
- `GatewayClient` with optional retry/backoff using `sdk.retry.with_retry`.
- NIP-01 utilities (`sdk.nostr_utils`): `verify_event`, `compute_event_id`, `npub_to_hex`, `hex_to_npub`.
- Wallet helpers (`sdk.wallet_utils`): BIP340 sign message/data/event.
- Solver flows (`sdk.solver_flows`): `accept_intent_and_issue_challenge`, `start_and_wait_ceremony`, `make_intent_digest`.
- Ceremony helper (`sdk.ceremony`): `wait_for_ceremony`.
- Payloads (`sdk.payloads`): 31510/31511/31512 builders and basic validators.
- Types (`sdk.types`): TypedDict models for intents, challenges, responses, ceremony, balances, assets.
- Errors (`sdk.errors`): `VerificationError`, `SchemaValidationError`, `RetryExceededError`, `CeremonyTimeoutError`.
- Packaging metadata and README with publish instructions.

[Unreleased]: https://github.com/afeezaziz/arkrelay-gateway/compare/sdk-py-v0.1.1...HEAD
[0.1.1]: https://github.com/afeezaziz/arkrelay-gateway/compare/sdk-py-v0.1.0...sdk-py-v0.1.1
[0.1.0]: https://github.com/afeezaziz/arkrelay-gateway/releases/tag/sdk-py-v0.1.0
