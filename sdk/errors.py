"""
SDK error hierarchy for ArkRelay Gateway helpers.

Keep exceptions small and focused. The HTTP client exposes GatewayClientError.
This module provides higher-level errors used by helper utilities.
"""
from __future__ import annotations


class VerificationError(ValueError):
    """Raised when a cryptographic verification fails (e.g., NIP-01 verify)."""


class SchemaValidationError(ValueError):
    """Raised when a payload does not conform to 31510/31511/31512 schema."""


class RetryExceededError(RuntimeError):
    """Raised when a retry operation exceeds maximum attempts or timeout."""


class CeremonyTimeoutError(TimeoutError):
    """Raised when a ceremony wait helper times out."""
