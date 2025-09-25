"""
GatewayClient: a minimal Python SDK to interact with ArkRelay Gateway helper endpoints.

Scope: sessions/signing, ceremony status, and VTXO settlement helpers.
Do not implement protocol logic here; use this only as infrastructure plumbing.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, Type

import requests

from .retry import with_retry

class GatewayClientError(RuntimeError):
    """Raised for non-2xx responses or network errors when calling the gateway."""


class GatewayClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        session: Optional[requests.Session] = None,
        # Retry options (opt-in)
        retry_enabled: bool = False,
        retry_max_attempts: int = 5,
        retry_backoff_base: float = 0.2,
        retry_backoff_factor: float = 2.0,
        retry_jitter: float = 0.1,
        retry_exceptions: Tuple[Type[BaseException], ...] = (),
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()
        self._headers = {"Content-Type": "application/json"}
        # Retry config
        self._retry_enabled = retry_enabled
        self._retry_max_attempts = retry_max_attempts
        self._retry_backoff_base = retry_backoff_base
        self._retry_backoff_factor = retry_backoff_factor
        self._retry_jitter = retry_jitter
        # Default retry exceptions: network errors and non-2xx mapped GatewayClientError
        self._retry_exceptions = retry_exceptions or (GatewayClientError, requests.RequestException)

    # ---- Sessions & Signing ----
    def create_session(self, user_pubkey: str, session_type: str, intent_data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/sessions/create"
        payload = {
            "user_pubkey": user_pubkey,
            "session_type": session_type,
            "intent_data": intent_data,
        }
        return self._post(url, json=payload)

    def create_challenge(self, session_id: str, challenge_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/sessions/{session_id}/challenge"
        payload = {
            "challenge_data": challenge_data,
        }
        if context is not None:
            payload["context"] = context
        return self._post(url, json=payload)

    def respond_to_challenge(self, session_id: str, signature: str, user_pubkey: Optional[str] = None) -> Dict[str, Any]:
        """Primarily for development/testing. In production, responses arrive via 31512 DM."""
        url = f"{self.base_url}/sessions/{session_id}/respond"
        payload: Dict[str, Any] = {"signature": signature}
        if user_pubkey:
            payload["user_pubkey"] = user_pubkey
        return self._post(url, json=payload)

    def complete_session(self, session_id: str, result_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/sessions/{session_id}/complete"
        payload: Dict[str, Any] = {}
        if result_data is not None:
            payload["result_data"] = result_data
        return self._post(url, json=payload)

    def fail_session(self, session_id: str, reason: str) -> Dict[str, Any]:
        url = f"{self.base_url}/sessions/{session_id}/fail"
        payload = {"reason": reason}
        return self._post(url, json=payload)

    def start_ceremony(self, session_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/signing/ceremony/start"
        payload = {"session_id": session_id}
        return self._post(url, json=payload)

    def get_ceremony_status(self, session_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/signing/ceremony/{session_id}/status"
        return self._get(url)

    # ---- Asset Management ----
    def create_asset(self, asset_id: str, name: str, ticker: str, total_supply: int = 0) -> Dict[str, Any]:
        url = f"{self.base_url}/assets"
        payload = {
            "asset_id": asset_id,
            "name": name,
            "ticker": ticker,
            "total_supply": total_supply,
        }
        return self._post(url, json=payload)

    def get_asset_info(self, asset_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/assets/{asset_id}"
        return self._get(url)

    def mint_asset(self, asset_id: str, user_pubkey: str, amount: int) -> Dict[str, Any]:
        url = f"{self.base_url}/assets/{asset_id}/mint"
        payload = {"user_pubkey": user_pubkey, "amount": amount}
        return self._post(url, json=payload)

    def transfer_asset(self, sender_pubkey: str, recipient_pubkey: str, asset_id: str, amount: int) -> Dict[str, Any]:
        url = f"{self.base_url}/assets/transfer"
        payload = {
            "sender_pubkey": sender_pubkey,
            "recipient_pubkey": recipient_pubkey,
            "asset_id": asset_id,
            "amount": amount,
        }
        return self._post(url, json=payload)

    def get_user_balances(self, user_pubkey: str) -> Dict[str, Any]:
        url = f"{self.base_url}/balances/{user_pubkey}"
        return self._get(url)

    # ---- VTXO & Settlement ----
    def vtxo_batch_create(self, asset_id: str, count: int, amount_sats: int) -> Dict[str, Any]:
        url = f"{self.base_url}/vtxos/batch/create"
        payload = {"asset_id": asset_id, "count": count, "amount_sats": amount_sats}
        return self._post(url, json=payload)

    def vtxo_assign(self, user_pubkey: str, asset_id: str, amount_needed: int) -> Dict[str, Any]:
        url = f"{self.base_url}/vtxos/assign"
        payload = {"user_pubkey": user_pubkey, "asset_id": asset_id, "amount_needed": amount_needed}
        return self._post(url, json=payload)

    def vtxo_settlement_process(self) -> Dict[str, Any]:
        url = f"{self.base_url}/vtxos/settlement/process"
        return self._post(url)

    def vtxo_settlement_status(self) -> Dict[str, Any]:
        url = f"{self.base_url}/vtxos/settlement/status"
        return self._get(url)

    # ---- Lightning (optional rails) ----
    def lightning_lift(self, user_pubkey: str, asset_id: str, amount_sats: int) -> Dict[str, Any]:
        url = f"{self.base_url}/lightning/lift"
        payload = {"user_pubkey": user_pubkey, "asset_id": asset_id, "amount_sats": amount_sats}
        return self._post(url, json=payload)

    def lightning_land(self, user_pubkey: str, asset_id: str, amount_sats: int, lightning_invoice: str) -> Dict[str, Any]:
        url = f"{self.base_url}/lightning/land"
        payload = {
            "user_pubkey": user_pubkey,
            "asset_id": asset_id,
            "amount_sats": amount_sats,
            "lightning_invoice": lightning_invoice,
        }
        return self._post(url, json=payload)

    def lightning_pay(self, payment_hash: str) -> Dict[str, Any]:
        url = f"{self.base_url}/lightning/pay/{payment_hash}"
        return self._post(url)

    # ---- Internal HTTP helpers ----
    def _get(self, url: str) -> Dict[str, Any]:
        def _call() -> Dict[str, Any]:
            try:
                resp = self._session.get(url, headers=self._headers, timeout=self.timeout)
                if not (200 <= resp.status_code < 300):
                    raise GatewayClientError(f"GET {url} -> {resp.status_code}: {resp.text}")
                return resp.json() if resp.content else {}
            except requests.RequestException as e:
                raise GatewayClientError(str(e)) from e

        if not self._retry_enabled:
            return _call()
        return with_retry(
            _call,
            exceptions=self._retry_exceptions,
            max_attempts=self._retry_max_attempts,
            backoff_base=self._retry_backoff_base,
            backoff_factor=self._retry_backoff_factor,
            jitter=self._retry_jitter,
        )

    def _post(self, url: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def _call() -> Dict[str, Any]:
            try:
                resp = self._session.post(url, headers=self._headers, json=json, timeout=self.timeout)
                if not (200 <= resp.status_code < 300):
                    raise GatewayClientError(f"POST {url} -> {resp.status_code}: {resp.text}")
                return resp.json() if resp.content else {}
            except requests.RequestException as e:
                raise GatewayClientError(str(e)) from e

        if not self._retry_enabled:
            return _call()
        return with_retry(
            _call,
            exceptions=self._retry_exceptions,
            max_attempts=self._retry_max_attempts,
            backoff_base=self._retry_backoff_base,
            backoff_factor=self._retry_backoff_factor,
            jitter=self._retry_jitter,
        )
