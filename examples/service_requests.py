#!/usr/bin/env python3
"""
Service Request Patterns (31500/31501/31502) Examples

This example demonstrates complete service request/response patterns:
1. Service requests (31500) - User-initiated service calls
2. Service responses (31501) - Gateway responses to requests
3. Service notifications (31502) - Ongoing status updates and notifications

These patterns are used for:
- Lightning lift/land operations
- VTXO status synchronization
- Gateway health monitoring
- Asset balance queries

Usage:
    python service_requests.py --gateway http://localhost:8000 sync-state
    python service_requests.py --gateway http://localhost:8000 lift-lightning --amount 100000
    python service_requests.py --gateway http://localhost:8000 monitor-status --session-id sess_123
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure we can import the SDK from the repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.gateway_client import GatewayClient, GatewayClientError  # noqa: E402


class ServiceRequestDemo:
    """Complete service request patterns demo with 31500/31501/31502 events"""

    def __init__(self, gateway_url: str, user_npub: str, gateway_npub: str):
        self.client = GatewayClient(gateway_url)
        self.user_npub = user_npub
        self.gateway_npub = gateway_npub
        self.request_counter = 0

    def create_service_request(self, action: str, **kwargs) -> Dict[str, Any]:
        """Create a 31500 service request"""
        self.request_counter += 1
        request_id = f"req_{int(time.time())}_{self.request_counter:03d}"

        request = {
            "request_id": request_id,
            "action": action,
            "timestamp": int(time.time()),
            "user_pubkey": self.user_npub,
            **kwargs
        }

        # Create the Nostr event structure
        nostr_event = {
            "id": self._compute_event_id(request),
            "pubkey": self.user_npub,
            "created_at": int(time.time()),
            "kind": 31500,
            "tags": [
                ["p", self.gateway_npub],
                ["e", request_id]
            ],
            "content": json.dumps(request),
            "sig": "user_signature_placeholder"  # In real implementation, sign with user's key
        }

        return {
            "request": request,
            "nostr_event": nostr_event
        }

    def create_service_response(self, request: Dict[str, Any], **response_data) -> Dict[str, Any]:
        """Create a 31501 service response"""
        response = {
            "request_id": request["request_id"],
            "action": request["action"],
            "status": "success",
            "timestamp": int(time.time()),
            "gateway_pubkey": self.gateway_npub,
            **response_data
        }

        # Create the Nostr event structure
        nostr_event = {
            "id": self._compute_event_id(response),
            "pubkey": self.gateway_npub,
            "created_at": int(time.time()),
            "kind": 31501,
            "tags": [
                ["p", self.user_npub],
                ["e", request["request_id"]]
            ],
            "content": json.dumps(response),
            "sig": "gateway_signature_placeholder"  # In real implementation, sign with gateway's key
        }

        return {
            "response": response,
            "nostr_event": nostr_event
        }

    def create_service_notification(self, notification_type: str, **notification_data) -> Dict[str, Any]:
        """Create a 31502 service notification"""
        notification_id = f"notif_{int(time.time())}_{os.urandom(2).hex()}"

        notification = {
            "notification_id": notification_id,
            "type": notification_type,
            "timestamp": int(time.time()),
            "gateway_pubkey": self.gateway_npub,
            **notification_data
        }

        # Create the Nostr event structure
        nostr_event = {
            "id": self._compute_event_id(notification),
            "pubkey": self.gateway_npub,
            "created_at": int(time.time()),
            "kind": 31502,
            "tags": [
                ["p", self.user_npub],
                ["type", notification_type]
            ],
            "content": json.dumps(notification),
            "sig": "gateway_signature_placeholder"  # In real implementation, sign with gateway's key
        }

        return {
            "notification": notification,
            "nostr_event": nostr_event
        }

    def _compute_event_id(self, data: Dict[str, Any]) -> str:
        """Compute Nostr event ID (simplified)"""
        content = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(content.encode()).hexdigest()

    def execute_sync_state_flow(self) -> Dict[str, Any]:
        """Execute complete state synchronization flow"""
        print(f"\n🔄 Starting State Synchronization Flow")

        # Step 1: User sends sync state request (31500)
        sync_request = self.create_service_request("sync_state")
        print(f"\n📤 31500 Service Request:")
        print(json.dumps(sync_request["request"], indent=2))

        # Step 2: Gateway responds with current state (31501)
        mock_vtxos = [
            {"vtxo_id": "vtxo_001", "amount": 500000, "asset_id": "gBTC", "status": "available"},
            {"vtxo_id": "vtxo_002", "amount": 1000000, "asset_id": "gUSD", "status": "available"},
            {"vtxo_id": "vtxo_003", "amount": 200000, "asset_id": "gBTC", "status": "assigned"}
        ]

        mock_balances = [
            {"asset_id": "gBTC", "balance": 500000, "reserved": 200000},
            {"asset_id": "gUSD", "balance": 1000000, "reserved": 0}
        ]

        sync_response = self.create_service_response(
            sync_request["request"],
            user_vtxos=mock_vtxos,
            user_balances=mock_balances,
            last_sync=int(time.time()) - 3600  # 1 hour ago
        )
        print(f"\n📥 31501 Service Response:")
        print(json.dumps(sync_response["response"], indent=2))

        # Step 3: Gateway sends ongoing status notifications (31502)
        for i in range(3):
            notification = self.create_service_notification(
                "sync_progress",
                step=i+1,
                total_steps=3,
                message=f"Synchronizing {['VTXOs', 'balances', 'transactions'][i]}...",
                progress_percent=(i+1) * 33
            )
            print(f"\n📢 31502 Service Notification {i+1}:")
            print(json.dumps(notification["notification"], indent=2))
            time.sleep(1)

        return {
            "request": sync_request,
            "response": sync_response,
            "status": "sync_completed"
        }

    def execute_lift_lightning_flow(self, amount_sats: int, asset_id: str = "gBTC") -> Dict[str, Any]:
        """Execute complete Lightning lift flow via service requests"""
        print(f"\n🚀 Starting Lightning Lift Flow via Service Requests: {amount_sats} sats")

        # Step 1: User requests Lightning lift (31500)
        lift_request = self.create_service_request(
            "lift_lightning",
            asset_id=asset_id,
            amount=amount_sats,
            preferred_expiry=3600  # 1 hour
        )
        print(f"\n📤 31500 Service Request:")
        print(json.dumps(lift_request["request"], indent=2))

        # Step 2: Gateway responds with Lightning invoice (31501)
        mock_invoice = f"lnbc{amount_sats}n1p3k8..."
        lift_response = self.create_service_response(
            lift_request["request"],
            invoice=mock_invoice,
            amount=amount_sats,
            asset_id=asset_id,
            expires_at=int(time.time()) + 3600,
            fee_estimate=10,
            status="pending_payment"
        )
        print(f"\n📥 31501 Service Response:")
        print(json.dumps(lift_response["response"], indent=2))

        # Step 3: Gateway sends payment status notifications (31502)
        notifications = [
            {"type": "payment_received", "message": "Lightning payment received", "amount": amount_sats},
            {"type": "vtxo_creation", "message": "Creating VTXO...", "estimated_time": 30},
            {"type": "vtxo_ready", "message": "VTXO created successfully", "vtxo_id": "vtxo_lift_001"}
        ]

        for i, notif_data in enumerate(notifications):
            notification = self.create_service_notification(
                notif_data["type"],
                request_id=lift_request["request"]["request_id"],
                **notif_data
            )
            print(f"\n📢 31502 Service Notification {i+1}:")
            print(json.dumps(notification["notification"], indent=2))
            time.sleep(1)

        # Step 4: Final completion notification
        completion_notification = self.create_service_notification(
            "lift_completed",
            request_id=lift_request["request"]["request_id"],
            vtxo_id="vtxo_lift_001",
            amount=amount_sats,
            asset_id=asset_id,
            final_txid="abc123def456..."
        )
        print(f"\n🎉 31502 Completion Notification:")
        print(json.dumps(completion_notification["notification"], indent=2))

        return {
            "request": lift_request,
            "response": lift_response,
            "vtxo_id": "vtxo_lift_001",
            "status": "lift_completed"
        }

    def execute_monitoring_flow(self, session_id: str) -> Dict[str, Any]:
        """Execute monitoring and status flow"""
        print(f"\n📊 Starting Monitoring Flow for session: {session_id}")

        # Step 1: User requests status monitoring (31500)
        monitor_request = self.create_service_request(
            "monitor_status",
            session_id=session_id,
            timeout=300,  # 5 minutes
            detailed=True
        )
        print(f"\n📤 31500 Service Request:")
        print(json.dumps(monitor_request["request"], indent=2))

        # Step 2: Gateway responds with current status (31501)
        mock_status = {
            "session_id": session_id,
            "status": "in_progress",
            "current_step": 3,
            "total_steps": 5,
            "progress_percent": 60,
            "started_at": int(time.time()) - 120,  # 2 minutes ago
            "estimated_completion": int(time.time()) + 180  # 3 minutes
        }

        monitor_response = self.create_service_response(
            monitor_request["request"],
            **mock_status
        )
        print(f"\n📥 31501 Service Response:")
        print(json.dumps(monitor_response["response"], indent=2))

        # Step 3: Gateway sends progress updates (31502)
        progress_updates = [
            {"step": 4, "message": "Validating transaction...", "progress": 80},
            {"step": 5, "message": "Finalizing transaction...", "progress": 95},
            {"status": "completed", "message": "Transaction completed successfully!", "progress": 100}
        ]

        for i, update in enumerate(progress_updates):
            notification = self.create_service_notification(
                "status_update",
                session_id=session_id,
                request_id=monitor_request["request"]["request_id"],
                **update
            )
            print(f"\n📢 31502 Status Update {i+1}:")
            print(json.dumps(notification["notification"], indent=2))
            time.sleep(1)

        return {
            "request": monitor_request,
            "response": monitor_response,
            "status": "monitoring_completed"
        }

    def execute_balance_query_flow(self, asset_ids: List[str]) -> Dict[str, Any]:
        """Execute balance query flow"""
        print(f"\n💰 Starting Balance Query Flow for assets: {asset_ids}")

        # Step 1: User requests balance information (31500)
        query_request = self.create_service_request(
            "query_balances",
            asset_ids=asset_ids,
            include_vtxos=True
        )
        print(f"\n📤 31500 Service Request:")
        print(json.dumps(query_request["request"], indent=2))

        # Step 2: Gateway responds with balance information (31501)
        mock_balances = []
        for asset_id in asset_ids:
            if asset_id == "gBTC":
                mock_balances.append({
                    "asset_id": "gBTC",
                    "balance": 500000,
                    "reserved": 200000,
                    "available": 300000,
                    "vtxo_count": 3
                })
            elif asset_id == "gUSD":
                mock_balances.append({
                    "asset_id": "gUSD",
                    "balance": 1000000,
                    "reserved": 0,
                    "available": 1000000,
                    "vtxo_count": 2
                })

        query_response = self.create_service_response(
            query_request["request"],
            balances=mock_balances,
            last_updated=int(time.time()) - 60  # 1 minute ago
        )
        print(f"\n📥 31501 Service Response:")
        print(json.dumps(query_response["response"], indent=2))

        return {
            "request": query_request,
            "response": query_response,
            "status": "query_completed"
        }

    def execute_error_handling_flow(self) -> Dict[str, Any]:
        """Demonstrate error handling in service requests"""
        print(f"\n❌ Starting Error Handling Flow")

        # Step 1: User makes an invalid request (31500)
        invalid_request = self.create_service_request(
            "invalid_action",
            invalid_param="test"
        )
        print(f"\n📤 31500 Invalid Service Request:")
        print(json.dumps(invalid_request["request"], indent=2))

        # Step 2: Gateway responds with error (31501)
        error_response = self.create_service_response(
            invalid_request["request"],
            status="error",
            error_code=4001,
            error_message="Unknown service action: invalid_action",
            valid_actions=["sync_state", "lift_lightning", "land_lightning", "monitor_status", "query_balances"]
        )
        print(f"\n📥 31501 Error Response:")
        print(json.dumps(error_response["response"], indent=2))

        # Step 3: Gateway sends error notification (31502)
        error_notification = self.create_service_notification(
            "request_error",
            request_id=invalid_request["request"]["request_id"],
            error_code=4001,
            error_message="Unknown service action",
            timestamp=int(time.time())
        )
        print(f"\n📢 31502 Error Notification:")
        print(json.dumps(error_notification["notification"], indent=2))

        return {
            "request": invalid_request,
            "response": error_response,
            "status": "error_handled"
        }


def main():
    parser = argparse.ArgumentParser(description="Service Request Patterns Demo (31500/31501/31502)")
    parser.add_argument("--gateway", default=os.getenv("GATEWAY_BASE_URL", "http://localhost:8000"),
                       help="Gateway base URL")
    parser.add_argument("--user-npub", required=True, help="User's npub key")
    parser.add_argument("--gateway-npub", required=True, help="Gateway's npub key")

    subparsers = parser.add_subparsers(dest="command", help="Service request to perform")

    # Sync state command
    sync_parser = subparsers.add_parser("sync-state", help="Synchronize user state")

    # Lift lightning command
    lift_parser = subparsers.add_parser("lift-lightning", help="Lightning lift request")
    lift_parser.add_argument("--amount", type=int, required=True, help="Amount in satoshis")
    lift_parser.add_argument("--asset", default="gBTC", help="Asset ID")

    # Monitor status command
    monitor_parser = subparsers.add_parser("monitor-status", help="Monitor session status")
    monitor_parser.add_argument("--session-id", required=True, help="Session ID to monitor")

    # Query balances command
    balance_parser = subparsers.add_parser("query-balances", help="Query asset balances")
    balance_parser.add_argument("--assets", nargs="+", required=True, help="Asset IDs to query")

    # Error handling demo
    error_parser = subparsers.add_parser("error-demo", help="Demonstrate error handling")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    demo = ServiceRequestDemo(args.gateway, args.user_npub, args.gateway_npub)

    try:
        if args.command == "sync-state":
            result = demo.execute_sync_state_flow()
            print(f"\n✅ Sync state flow completed")

        elif args.command == "lift-lightning":
            result = demo.execute_lift_lightning_flow(args.amount, args.asset)
            print(f"\n✅ Lightning lift flow completed")

        elif args.command == "monitor-status":
            result = demo.execute_monitoring_flow(args.session_id)
            print(f"\n✅ Monitoring flow completed")

        elif args.command == "query-balances":
            result = demo.execute_balance_query_flow(args.assets)
            print(f"\n✅ Balance query flow completed")

        elif args.command == "error-demo":
            result = demo.execute_error_handling_flow()
            print(f"\n✅ Error handling demo completed")

    except GatewayClientError as e:
        print(f"❌ Gateway Error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()