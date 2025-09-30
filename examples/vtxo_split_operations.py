#!/usr/bin/env python3
"""
VTXO Split-and-Send Operations Examples

This example demonstrates:
1. VTXO splitting for optimal payment execution
2. Multi-VTXO transactions for large transfers
3. Optimal change management
4. Complete split-and-send workflows with Nostr events

Usage:
    python vtxo_split_operations.py --gateway http://localhost:8000 split --vtxo vtxo_123 --amounts 200000,300000
    python vtxo_split_operations.py --gateway http://localhost:8000 multi-send --asset gUSD --amount 400000000
    python vtxo_split_operations.py --gateway http://localhost:8000 optimal-change --asset gBTC --amount 123456
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure we can import the SDK from the repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.gateway_client import GatewayClient, GatewayClientError  # noqa: E402


class VtxoSplitOperationsDemo:
    """Complete VTXO split operations demo with advanced coin selection"""

    def __init__(self, gateway_url: str):
        self.client = GatewayClient(gateway_url)
        self.gateway_npub = "npub1gateway..."  # Replace with actual gateway npub

    def create_split_intent(self, vtxo_id: str, split_amounts: List[int],
                           asset_id: str = "gBTC", fee_asset_id: str = "gBTC") -> Dict[str, Any]:
        """Create a 31510 intent for VTXO splitting"""
        return {
            "action_id": f"split_{int(time.time())}_{os.urandom(4).hex()}",
            "type": "vtxo:split",
            "params": {
                "vtxo_id": vtxo_id,
                "split_amounts": split_amounts,
                "asset_id": asset_id,
                "fee_asset_id": fee_asset_id,
                "fee_amount": 10,  # 10 sats in gBTC
                "min_change": 1000  # Minimum change threshold
            },
            "expires_at": int(time.time()) + 15 * 60
        }

    def create_multi_vtxo_intent(self, asset_id: str, total_amount: int, recipient_pubkey: str,
                               source_vtxos: Optional[List[str]] = None,
                               fee_asset_id: str = "gBTC") -> Dict[str, Any]:
        """Create a 31510 intent for multi-VTXO transaction"""
        return {
            "action_id": f"multi_{int(time.time())}_{os.urandom(4).hex()}",
            "type": "vtxo:multi_transfer",
            "params": {
                "asset_id": asset_id,
                "total_amount": total_amount,
                "recipient_pubkey": recipient_pubkey,
                "source_vtxos": source_vtxos or [],  # Optional: specify which VTXOs to use
                "fee_asset_id": fee_asset_id,
                "fee_amount": 10,
                "min_change": 1000,
                "max_inputs": 5,  # Maximum VTXOs to combine
                "strategy": "optimal"  # optimal, greedy, minimal
            },
            "expires_at": int(time.time()) + 15 * 60
        }

    def create_optimal_change_intent(self, asset_id: str, amount_needed: int,
                                   recipient_pubkey: str, fee_asset_id: str = "gBTC") -> Dict[str, Any]:
        """Create a 31510 intent for optimal change management"""
        return {
            "action_id": f"change_{int(time.time())}_{os.urandom(4).hex()}",
            "type": "vtxo:optimal_change",
            "params": {
                "asset_id": asset_id,
                "amount_needed": amount_needed,
                "recipient_pubkey": recipient_pubkey,
                "fee_asset_id": fee_asset_id,
                "fee_amount": 10,
                "change_threshold": 5000,  # Minimum change amount to create
                "dust_limit": 1,  # 1 satoshi dust limit for VTXOs
                "prefer_existing_change": True  # Prefer using existing change VTXOs
            },
            "expires_at": int(time.time()) + 15 * 60
        }

    def simulate_vtxo_inventory(self, user_pubkey: str, asset_id: str) -> List[Dict[str, Any]]:
        """Simulate getting user's available VTXOs"""
        # In real implementation, this would call the gateway
        return [
            {"vtxo_id": "vtxo_large_1", "amount": 500000000, "asset_id": asset_id, "status": "available"},
            {"vtxo_id": "vtxo_medium_1", "amount": 100000000, "asset_id": asset_id, "status": "available"},
            {"vtxo_id": "vtxo_small_1", "amount": 50000000, "asset_id": asset_id, "status": "available"},
            {"vtxo_id": "vtxo_change_1", "amount": 12345, "asset_id": asset_id, "status": "available"},
        ]

    def find_optimal_vtxo_combination(self, available_vtxos: List[Dict[str, Any]],
                                    amount_needed: int, strategy: str = "optimal") -> List[str]:
        """Find optimal VTXO combination for given amount"""
        available_amounts = [(vtxo["vtxo_id"], vtxo["amount"]) for vtxo in available_vtxos]

        if strategy == "greedy":
            # Use largest VTXOs first
            available_amounts.sort(key=lambda x: x[1], reverse=True)
        elif strategy == "minimal":
            # Use minimal number of VTXOs
            available_amounts.sort(key=lambda x: x[1], reverse=True)
        else:  # optimal
            # Optimal: minimize change while using reasonable number of inputs
            available_amounts.sort(key=lambda x: x[1], reverse=True)

        selected = []
        total = 0

        for vtxo_id, amount in available_amounts:
            if total >= amount_needed:
                break
            selected.append(vtxo_id)
            total += amount

        if total < amount_needed:
            raise ValueError(f"Insufficient VTXO balance. Need: {amount_needed}, Available: {total}")

        return selected

    def calculate_change_amount(self, selected_vtxos: List[Dict[str, Any]],
                               amount_needed: int, fees: int = 10) -> int:
        """Calculate optimal change amount"""
        total_input = sum(vtxo["amount"] for vtxo in selected_vtxos)
        change = total_input - amount_needed - fees

        # Only create change if above threshold
        change_threshold = 5000
        return max(0, change) if change >= change_threshold else 0

    def execute_split_flow(self, vtxo_id: str, split_amounts: List[int],
                          asset_id: str = "gBTC") -> Dict[str, Any]:
        """Execute complete VTXO split flow"""
        total_split = sum(split_amounts)
        print(f"\n✂️ Starting VTXO Split Flow: {vtxo_id} → {split_amounts} (total: {total_split})")

        # Step 1: Create split intent
        intent = self.create_split_intent(vtxo_id, split_amounts, asset_id)
        print(f"\n📋 31510 Split Intent:")
        print(json.dumps(intent, indent=2))

        # Step 2: Create session
        session_resp = self.client.create_session(
            user_pubkey="npub1user...",
            session_type="vtxo_split",
            intent_data=intent
        )
        session_id = session_resp.get("session_id")
        print(f"\n✅ Session created: {session_id}")

        # Step 3: Create multi-step challenge for split authorization
        for i, amount in enumerate(split_amounts):
            step_data = {
                "step_index": i + 1,
                "step_total": len(split_amounts),
                "split_amount": amount,
                "vtxo_id": vtxo_id
            }

            challenge_data = {
                "payload_to_sign": f"0x{hashlib.sha256(json.dumps(step_data, sort_keys=True).encode()).hexdigest()}",
                "type": "sign_payload",
                "payload_ref": f"sha256:split_{i+1}_{hashlib.sha256(str(amount).encode()).hexdigest()}"
            }

            context = {
                "human": f"Step {i+1}/{len(split_amounts)}: Authorize split of {amount} from {vtxo_id}",
                "split_details": step_data
            }

            challenge = self.client.create_challenge(
                session_id=session_id,
                challenge_data=challenge_data,
                context=context
            )
            print(f"\n🔐 Challenge {i+1}/{len(split_amounts)} created")

        # Step 4: Start ceremony
        ceremony_resp = self.client.start_ceremony(session_id=session_id)
        print(f"\n🎭 Split ceremony started: {ceremony_resp.get('status')}")

        return {
            "session_id": session_id,
            "intent": intent,
            "split_amounts": split_amounts,
            "status": "split_initiated"
        }

    def execute_multi_vtxo_flow(self, asset_id: str, total_amount: int,
                               recipient_pubkey: str) -> Dict[str, Any]:
        """Execute multi-VTXO transaction flow"""
        print(f"\n🔄 Starting Multi-VTXO Flow: {total_amount} {asset_id} → {recipient_pubkey}")

        # Step 1: Get available VTXOs
        available_vtxos = self.simulate_vtxo_inventory("npub1user...", asset_id)
        print(f"\n💰 Available VTXOs:")
        for vtxo in available_vtxos:
            print(f"  - {vtxo['vtxo_id']}: {vtxo['amount']} {vtxo['asset_id']}")

        # Step 2: Find optimal combination
        selected_vtxo_ids = self.find_optimal_vtxo_combination(available_vtxos, total_amount)
        selected_vtxos = [v for v in available_vtxos if v["vtxo_id"] in selected_vtxo_ids]

        print(f"\n🎯 Selected VTXOs:")
        for vtxo in selected_vtxos:
            print(f"  - {vtxo['vtxo_id']}: {vtxo['amount']}")

        # Step 3: Calculate change
        change_amount = self.calculate_change_amount(selected_vtxos, total_amount)
        print(f"\n💱 Change amount: {change_amount}")

        # Step 4: Create intent
        intent = self.create_multi_vtxo_intent(
            asset_id=asset_id,
            total_amount=total_amount,
            recipient_pubkey=recipient_pubkey,
            source_vtxos=selected_vtxo_ids
        )

        # Add change information
        if change_amount > 0:
            intent["params"]["change_amount"] = change_amount
            intent["params"]["change_address"] = "npub1user..."  # User's address for change

        print(f"\n📋 31510 Multi-VTXO Intent:")
        print(json.dumps(intent, indent=2))

        # Step 5: Create session
        session_resp = self.client.create_session(
            user_pubkey="npub1user...",
            session_type="multi_vtxo_transfer",
            intent_data=intent
        )
        session_id = session_resp.get("session_id")
        print(f"\n✅ Session created: {session_id}")

        # Step 6: Create challenge
        challenge_data = {
            "payload_to_sign": f"0x{hashlib.sha256(json.dumps(intent, sort_keys=True).encode()).hexdigest()}",
            "type": "sign_tx",
            "payload_ref": f"sha256:multi_tx_{hashlib.sha256(json.dumps(intent['params'], sort_keys=True).encode()).hexdigest()}"
        }

        context = {
            "human": f"Authorize multi-VTXO transfer: {total_amount} {asset_id} to {recipient_pubkey[:20]}...",
            "total_amount": total_amount,
            "vtxo_count": len(selected_vtxos),
            "change_amount": change_amount
        }

        challenge = self.client.create_challenge(
            session_id=session_id,
            challenge_data=challenge_data,
            context=context
        )
        print(f"\n🔐 Challenge created: {challenge.get('challenge_id')}")

        # Step 7: Start ceremony
        ceremony_resp = self.client.start_ceremony(session_id=session_id)
        print(f"\n🎭 Multi-VTXO ceremony started: {ceremony_resp.get('status')}")

        return {
            "session_id": session_id,
            "intent": intent,
            "selected_vtxos": selected_vtxos,
            "change_amount": change_amount,
            "status": "multi_vtxo_initiated"
        }

    def execute_optimal_change_flow(self, asset_id: str, amount_needed: int,
                                   recipient_pubkey: str) -> Dict[str, Any]:
        """Execute optimal change management flow"""
        print(f"\n💱 Starting Optimal Change Flow: {amount_needed} {asset_id}")

        # Step 1: Get available VTXOs including existing change
        available_vtxos = self.simulate_vtxo_inventory("npub1user...", asset_id)

        # Check for existing change VTXOs that could be used
        change_vtxos = [v for v in available_vtxos if "change" in v["vtxo_id"]]
        regular_vtxos = [v for v in available_vtxos if "change" not in v["vtxo_id"]]

        print(f"\n💰 Available VTXOs:")
        print(f"  Regular: {len(regular_vtxos)} VTXOs")
        print(f"  Change: {len(change_vtxos)} VTXOs")

        # Step 2: Try to use existing change first
        try:
            # Try regular VTXOs first, then add change if needed
            all_vtxos = regular_vtxos + change_vtxos
            selected_vtxo_ids = self.find_optimal_vtxo_combination(all_vtxos, amount_needed, "optimal")
            selected_vtxos = [v for v in all_vtxos if v["vtxo_id"] in selected_vtxo_ids]
        except ValueError:
            # Insufficient balance
            raise

        # Step 3: Calculate optimal change
        fees = 10
        total_input = sum(vtxo["amount"] for vtxo in selected_vtxos)
        change_amount = total_input - amount_needed - fees

        # Determine if change should be created
        change_threshold = 5000
        should_create_change = change_amount >= change_threshold

        print(f"\n📊 Change Analysis:")
        print(f"  Total input: {total_input}")
        print(f"  Amount needed: {amount_needed}")
        print(f"  Fees: {fees}")
        print(f"  Raw change: {change_amount}")
        print(f"  Create change: {should_create_change}")

        # Step 4: Create intent
        intent = self.create_optimal_change_intent(asset_id, amount_needed, recipient_pubkey)
        intent["params"]["selected_vtxos"] = selected_vtxo_ids
        intent["params"]["should_create_change"] = should_create_change

        if should_create_change:
            intent["params"]["change_amount"] = change_amount

        print(f"\n📋 31510 Optimal Change Intent:")
        print(json.dumps(intent, indent=2))

        # Step 5: Create session
        session_resp = self.client.create_session(
            user_pubkey="npub1user...",
            session_type="optimal_change",
            intent_data=intent
        )
        session_id = session_resp.get("session_id")
        print(f"\n✅ Session created: {session_id}")

        # Step 6: Create challenge
        challenge_data = {
            "payload_to_sign": f"0x{hashlib.sha256(json.dumps(intent, sort_keys=True).encode()).hexdigest()}",
            "type": "sign_tx",
            "payload_ref": f"sha256:optimal_change_{hashlib.sha256(json.dumps(intent['params'], sort_keys=True).encode()).hexdigest()}"
        }

        change_text = f" + {change_amount} change" if should_create_change else ""
        context = {
            "human": f"Authorize optimal payment: {amount_needed} {asset_id}{change_text}",
            "input_vtxos": len(selected_vtxos),
            "optimize_strategy": "use_existing_change_first"
        }

        challenge = self.client.create_challenge(
            session_id=session_id,
            challenge_data=challenge_data,
            context=context
        )
        print(f"\n🔐 Challenge created: {challenge.get('challenge_id')}")

        # Step 7: Start ceremony
        ceremony_resp = self.client.start_ceremony(session_id=session_id)
        print(f"\n🎭 Optimal change ceremony started: {ceremony_resp.get('status')}")

        return {
            "session_id": session_id,
            "intent": intent,
            "selected_vtxos": selected_vtxos,
            "change_amount": change_amount if should_create_change else 0,
            "status": "optimal_change_initiated"
        }


def main():
    parser = argparse.ArgumentParser(description="VTXO Split Operations Demo")
    parser.add_argument("--gateway", default=os.getenv("GATEWAY_BASE_URL", "http://localhost:8000"),
                       help="Gateway base URL")

    subparsers = parser.add_subparsers(dest="command", help="Operation to perform")

    # Split command
    split_parser = subparsers.add_parser("split", help="Split VTXO into smaller denominations")
    split_parser.add_argument("--vtxo", required=True, help="VTXO ID to split")
    split_parser.add_argument("--amounts", required=True, help="Comma-separated split amounts (e.g., 200000,300000)")
    split_parser.add_argument("--asset", default="gBTC", help="Asset ID")

    # Multi-VTXO command
    multi_parser = subparsers.add_parser("multi-send", help="Multi-VTXO transaction")
    multi_parser.add_argument("--asset", required=True, help="Asset ID")
    multi_parser.add_argument("--amount", type=int, required=True, help="Total amount to send")
    multi_parser.add_argument("--recipient", required=True, help="Recipient npub")

    # Optimal change command
    change_parser = subparsers.add_parser("optimal-change", help="Optimal change management")
    change_parser.add_argument("--asset", required=True, help="Asset ID")
    change_parser.add_argument("--amount", type=int, required=True, help="Amount needed")
    change_parser.add_argument("--recipient", required=True, help="Recipient npub")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    demo = VtxoSplitOperationsDemo(args.gateway)

    try:
        if args.command == "split":
            amounts = [int(x.strip()) for x in args.amounts.split(",")]
            result = demo.execute_split_flow(args.vtxo, amounts, args.asset)
            print(f"\n✂️ Split flow initiated. Session ID: {result['session_id']}")

        elif args.command == "multi-send":
            result = demo.execute_multi_vtxo_flow(args.asset, args.amount, args.recipient)
            print(f"\n🔄 Multi-VTXO flow initiated. Session ID: {result['session_id']}")

        elif args.command == "optimal-change":
            result = demo.execute_optimal_change_flow(args.asset, args.amount, args.recipient)
            print(f"\n💱 Optimal change flow initiated. Session ID: {result['session_id']}")

    except GatewayClientError as e:
        print(f"❌ Gateway Error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()