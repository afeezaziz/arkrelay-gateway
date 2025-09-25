"""
High-level ceremony helpers for ArkRelay Gateway.

- wait_for_ceremony: poll ceremony status until completion or timeout
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable, Tuple

from .gateway_client import GatewayClient


def wait_for_ceremony(
    client: GatewayClient,
    session_id: str,
    success_states: Iterable[str] = ("completed", "finalized", "settled"),
    failure_states: Iterable[str] = ("failed", "expired", "error"),
    timeout: float = 120.0,
    interval: float = 1.0,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Poll the gateway for ceremony status until it reaches a terminal state or times out.

    Returns (ok, last_status). ok is True when a success state was reached.

    The status object may expose "state" or "status"; both are handled.
    """
    t0 = time.time()
    last: Dict[str, Any] = {}
    succ = {s.lower() for s in success_states}
    fail = {s.lower() for s in failure_states}

    while time.time() - t0 < timeout:
        last = client.get_ceremony_status(session_id)
        state = str(last.get("state") or last.get("status") or "").lower()
        if state in succ:
            return True, {**last, "elapsed": time.time() - t0}
        if state in fail:
            return False, {**last, "elapsed": time.time() - t0}
        time.sleep(interval)

    # Timeout
    return False, {**last, "elapsed": time.time() - t0, "timeout": True}
