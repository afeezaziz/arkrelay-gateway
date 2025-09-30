#!/usr/bin/env python3
"""
Complete gBTC Lightning Operations Examples

This example demonstrates:
1. gBTC Lift (On-Ramp): Lightning → VTXO conversion
2. gBTC Land (Off-Ramp): VTXO → Lightning conversion
3. Complete Nostr event flows for Lightning operations
4. Error handling and status monitoring

Usage:
    python lightning_operations.py --gateway http://localhost:8000 lift --amount 100000
    python lightning_operations.py --gateway http://localhost:8000 land --amount 50000 --invoice lnbc...
    python lightning_operations.py --gateway http://localhost:8000 monitor --session-id sess_123
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure we can import the SDK from the repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.gateway_client import GatewayClient, GatewayClientError  # noqa: E402


class LightningOperationsDemo:
    """Complete Lightning operations demo with Nostr event flows"""

    def __init__(self, gateway_url: str):
        self.client = GatewayClient(gateway_url)
        self.gateway_npub = "npub1gateway..."  # Replace with actual gateway npub

    def create_lift_intent(self, amount_sats: int, asset_id: str = "gBTC") -> Dict[str, Any]:
        """Create a 31510 intent for gBTC lift operation"""
        return {
            "action_id": f"lift_{int(time.time())}_{os.urandom(4).hex()}",
            "type": "lightning:lift",
            "params": {
                "asset_id": asset_id,
                "amount": amount_sats,
                "fee_asset_id": "gBTC",
                "fee_amount": 10  # 10 sats in gBTC
            },
            "expires_at": int(time.time()) + 15 * 60  # 15 minutes
        }

    def create_land_intent(self, amount_sats: int, lightning_invoice: str, asset_id: str = "gBTC") -> Dict[str, Any]:
        """Create a 31510 intent for gBTC land operation"""
        return {
            "action_id": f"land_{int(time.time())}_{os.urandom(4).hex()}",
            "type": "lightning:land",
            "params": {
                "asset_id": asset_id,
                "amount": amount_sats,
                "lightning_invoice": lightning_invoice,
                "fee_asset_id": "gBTC",
                "fee_amount": int(amount_sats * 0.001)  # 0.1% fee
            },
            "expires_at": int(time.time()) + 15 * 60
        }

    def simulate_31500_service_request(self, action: str, asset_id: str, amount: int) -> Dict[str, Any]:
        """Simulate 31500 Service Request for Lightning operations"""
        request = {
            "action": action,
            "asset_id": asset_id,
            "amount": amount,
            "timestamp": int(time.time())
        }

        print(f"\n📤 31500 Service Request:")
        print(json.dumps(request, indent=2))
        return request

    def simulate_31501_service_response(self, request: Dict[str, Any], invoice: Optional[str] = None) -> Dict[str, Any]:
        """Simulate 31501 Service Response from gateway"""
        response = {
            "status": "pending",
            "action": request["action"],
            "asset_id": request["asset_id"],
            "amount": request["amount"],
            "timestamp": int(time.time())
        }

        if request["action"] == "lift_lightning" and invoice:
            response["invoice"] = invoice
            response["expires_at"] = int(time.time()) + 3600  # 1 hour

        print(f"\n📥 31501 Service Response:")
        print(json.dumps(response, indent=2))
        return response

    def execute_lift_flow(self, amount_sats: int, asset_id: str = "gBTC") -> Dict[str, Any]:
        """Complete gBTC lift flow: Lightning → VTXO"""
        print(f"\n🚀 Starting gBTC Lift Flow: {amount_sats} sats")

        # Step 1: 31500 Service Request
        service_request = self.simulate_31500_service_request("lift_lightning", asset_id, amount_sats)

        # Step 2: Get Lightning invoice from gateway (simulated)
        mock_invoice = f"lnbc{amount_sats}n1p3k8..."  # Mock invoice
        service_response = self.simulate_31501_service_response(service_request, mock_invoice)

        # Step 3: Create 31510 intent (after user pays Lightning invoice)
        intent = self.create_lift_intent(amount_sats, asset_id)
        print(f"\n📋 31510 Intent (after Lightning payment):")
        print(json.dumps(intent, indent=2))

        # Step 4: Create session
        session_resp = self.client.create_session(
            user_pubkey="npub1user...",  # Replace with actual user npub
            session_type="lightning_lift",
            intent_data=intent
        )
        session_id = session_resp.get("session_id")
        print(f"\n✅ Session created: {session_id}")

        # Step 5: Create challenge
        challenge_data = {
            "payload_to_sign": f"0x{hashlib.sha256(json.dumps(intent, sort_keys=True).encode()).hexdigest()}",
            "type": "sign_payload",
            "payload_ref": f"sha256:{hashlib.sha256(json.dumps(intent['params'], sort_keys=True).encode()).hexdigest()}"
        }
        context = {
            "human": f"Authorize gBTC lift of {amount_sats} sats via Lightning payment",
            "step_index": 1,
            "step_total": 1
        }

        challenge = self.client.create_challenge(
            session_id=session_id,
            challenge_data=challenge_data,
            context=context
        )
        print(f"\n🔐 Challenge created: {challenge.get('challenge_id')}")

        # Step 6: Start ceremony (simulating user approval)
        ceremony_resp = self.client.start_ceremony(session_id=session_id)
        print(f"\n🎭 Ceremony started: {ceremony_resp.get('status')}")

        return {
            "session_id": session_id,
            "intent": intent,
            "service_request": service_request,
            "service_response": service_response,
            "status": "lift_initiated"
        }

    def execute_land_flow(self, amount_sats: int, lightning_invoice: str, asset_id: str = "gBTC") -> Dict[str, Any]:
        """Complete gBTC land flow: VTXO → Lightning"""
        print(f"\n🛬 Starting gBTC Land Flow: {amount_sats} sats")

        # Step 1: Create 31510 intent
        intent = self.create_land_intent(amount_sats, lightning_invoice, asset_id)
        print(f"\n📋 31510 Intent:")
        print(json.dumps(intent, indent=2))

        # Step 2: Create session
        session_resp = self.client.create_session(
            user_pubkey="npub1user...",  # Replace with actual user npub
            session_type="lightning_land",
            intent_data=intent
        )
        session_id = session_resp.get("session_id")
        print(f"\n✅ Session created: {session_id}")

        # Step 3: Create challenge for VTXO spending
        challenge_data = {
            "payload_to_sign": f"0x{hashlib.sha256(json.dumps(intent, sort_keys=True).encode()).hexdigest()}",
            "type": "sign_tx",
            "payload_ref": f"sha256:{hashlib.sha256(json.dumps(intent['params'], sort_keys=True).encode()).hexdigest()}"
        }
        context = {
            "human": f"Authorize gBTC land of {amount_sats} sats to Lightning invoice",
            "step_index": 1,
            "step_total": 1
        }

        challenge = self.client.create_challenge(
            session_id=session_id,
            challenge_data=challenge_data,
            context=context
        )
        print(f"\n🔐 Challenge created: {challenge.get('challenge_id')}")

        # Step 4: Start ceremony
        ceremony_resp = self.client.start_ceremony(session_id=session_id)
        print(f"\n🎭 Ceremony started: {ceremony_resp.get('status')}")

        return {
            "session_id": session_id,
            "intent": intent,
            "status": "land_initiated"
        }

    def monitor_session(self, session_id: str, timeout: int = 120) -> Dict[str, Any]:
        """Monitor session status and print 31340/31341 events"""
        print(f"\n📊 Monitoring session: {session_id}")

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                status = self.client.get_ceremony_status(session_id=session_id)
                print(f"📈 Status: {status.get('status')} | Step: {status.get('current_step', 'N/A')}")

                if status.get('status') in ['completed', 'failed']:
                    print(f"\n🎉 Session {status.get('status')}!")

                    # Simulate 31340/31341 event
                    if status.get('status') == 'completed':
                        event_31340 = {
                            "status": "success",
                            "ref_action_id": status.get('intent_data', {}).get('action_id'),
                            "results": {
                                "txid": "mock_txid_abc123...",
                                "amount_processed": status.get('intent_data', {}).get('params', {}).get('amount'),
                                "fee_paid": status.get('intent_data', {}).get('params', {}).get('fee_amount')
                            },
                            "timestamp": int(time.time())
                        }
                        print(f"\n✅ 31340 Success Event:")
                        print(json.dumps(event_31340, indent=2))
                    else:
                        event_31341 = {
                            "status": "failure",
                            "code": status.get('error_code', 1000),
                            "message": status.get('error_message', 'Unknown error'),
                            "ref_action_id": status.get('intent_data', {}).get('action_id'),
                            "timestamp": int(time.time())
                        }
                        print(f"\n❌ 31341 Failure Event:")
                        print(json.dumps(event_31341, indent=2))

                    return status

                time.sleep(5)

            except GatewayClientError as e:
                print(f"❌ Error monitoring session: {e}")
                break

        print(f"\n⏰ Timeout waiting for session completion")
        return {"status": "timeout"}


def main():
    parser = argparse.ArgumentParser(description="gBTC Lightning Operations Demo")
    parser.add_argument("--gateway", default=os.getenv("GATEWAY_BASE_URL", "http://localhost:8000"),
                       help="Gateway base URL")
    parser.add_argument("--user-npub", required=True, help="User's npub key")

    subparsers = parser.add_subparsers(dest="command", help="Operation to perform")

    # Lift command
    lift_parser = subparsers.add_parser("lift", help="gBTC lift operation")
    lift_parser.add_argument("--amount", type=int, required=True, help="Amount in satoshis")
    lift_parser.add_argument("--asset", default="gBTC", help="Asset ID (default: gBTC)")

    # Land command
    land_parser = subparsers.add_parser("land", help="gBTC land operation")
    land_parser.add_argument("--amount", type=int, required=True, help="Amount in satoshis")
    land_parser.add_argument("--invoice", required=True, help="Lightning invoice")
    land_parser.add_argument("--asset", default="gBTC", help="Asset ID (default: gBTC)")

    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Monitor session status")
    monitor_parser.add_argument("--session-id", required=True, help="Session ID to monitor")
    monitor_parser.add_argument("--timeout", type=int, default=120, help="Timeout in seconds")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    demo = LightningOperationsDemo(args.gateway)

    try:
        if args.command == "lift":
            result = demo.execute_lift_flow(args.amount, args.asset)
            print(f"\n🎯 Lift flow initiated. Session ID: {result['session_id']}")

        elif args.command == "land":
            result = demo.execute_land_flow(args.amount, args.invoice, args.asset)
            print(f"\n🎯 Land flow initiated. Session ID: {result['session_id']}")

        elif args.command == "monitor":
            result = demo.monitor_session(args.session_id, args.timeout)
            print(f"\n📊 Final status: {result.get('status')}")

    except GatewayClientError as e:
        print(f"❌ Gateway Error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    import hashlib  # For demo purposes
    main()