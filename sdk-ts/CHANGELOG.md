# Changelog

All notable changes to the ArkRelay TypeScript SDK will be documented in this file.

The format is based on Keep a Changelog and this project adheres to Semantic Versioning.

## [Unreleased]
- Add typed interfaces mirroring Python `sdk/types.py`.
- Provide optional OpenAPI-generated clients once the spec is enriched.

## [0.1.0] - 2025-09-25
### Added
- Initial TypeScript SDK package (`arkrelay-sdk-ts`).
- `GatewayClient` with optional retry/backoff (with `withRetryAsync`) and retriable status codes.
- Nostr utilities (`nostrUtils`): `computeEventId`, `verifyEvent` (BIP340), `hexToNpub`, `npubToHex`.
- Validation (`validation`): AJV-based validators for 31510/31511/31512.
- React hook example `useCeremonyStatus` and Vite React demo app under `examples/react-app`.
- Package metadata for npm publish and README with usage and release instructions.

[Unreleased]: https://github.com/afeezaziz/arkrelay-gateway/compare/sdk-ts-v0.1.0...HEAD
[0.1.0]: https://github.com/afeezaziz/arkrelay-gateway/releases/tag/sdk-ts-v0.1.0
