#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure we can import the SDK from the repo root when running this example standalone
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.gateway_client import GatewayClient, GatewayClientError  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Demo: create asset, mint, and transfer using Gateway SDK")
    p.add_argument("--gateway", default=os.getenv("GATEWAY_BASE_URL", "http://localhost:8000"), help="Gateway base URL")
    p.add_argument("--asset-id", default="gDEMO", help="Asset ID e.g. gDEMO")
    p.add_argument("--name", default="Gateway DEMO", help="Asset name")
    p.add_argument("--ticker", default="gDEMO", help="Asset ticker")
    p.add_argument("--sender", required=True, help="Sender pubkey (npub)")
    p.add_argument("--recipient", required=True, help="Recipient pubkey (npub)")
    p.add_argument("--mint-amount", type=int, default=100_000, help="Amount to mint to sender")
    p.add_argument("--transfer-amount", type=int, default=10_000, help="Amount to transfer to recipient")

    args = p.parse_args()

    gc = GatewayClient(args.gateway)

    def jprint(label: str, obj: Any) -> None:
        print(f"\n=== {label} ===")
        print(json.dumps(obj, indent=2))

    # 1) Create asset (ignore if already exists)
    try:
        created = gc.create_asset(args.asset_id, args.name, args.ticker, total_supply=0)
        jprint("create_asset", created)
    except GatewayClientError as e:
        print(f"[warn] create_asset failed (may already exist): {e}")
        info = gc.get_asset_info(args.asset_id)
        jprint("get_asset_info", info)

    # 2) Mint to sender
    try:
        minted = gc.mint_asset(args.asset_id, args.sender, args.mint_amount)
        jprint("mint_asset", minted)
    except GatewayClientError as e:
        print(f"[warn] mint_asset failed: {e}")

    # 3) Check balances before transfer
    bal_sender_before = gc.get_user_balances(args.sender)
    bal_recipient_before = gc.get_user_balances(args.recipient)
    jprint("balances_sender_before", bal_sender_before)
    jprint("balances_recipient_before", bal_recipient_before)

    # 4) Transfer
    try:
        tx = gc.transfer_asset(args.sender, args.recipient, args.asset_id, args.transfer_amount)
        jprint("transfer_asset", tx)
    except GatewayClientError as e:
        print(f"[error] transfer_asset failed: {e}")
        sys.exit(2)

    # 5) Check balances after transfer
    bal_sender_after = gc.get_user_balances(args.sender)
    bal_recipient_after = gc.get_user_balances(args.recipient)
    jprint("balances_sender_after", bal_sender_after)
    jprint("balances_recipient_after", bal_recipient_after)


if __name__ == "__main__":
    main()
