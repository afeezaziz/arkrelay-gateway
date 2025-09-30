#!/usr/bin/env python3
"""
RGB Token Example for Ark Relay Gateway

This example demonstrates how to:
1. Register an RGB smart contract
2. Create RGB allocations within VTXOs
3. Transfer RGB assets between users
4. Validate RGB proofs and state
"""

import json
import time
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Mock user pubkeys for demonstration
USER_ALICE = "npub1alice7x8d9v5x3y2z1w9u8s7r6q5p4o3n2m1k0j9h8g7f6d5c4b3a2"
USER_BOB = "npub1bob9x8d7v6x5y4z3w2u1t9s8r7q6p5o4n3m2l1k0j9h8g7f6d5c4b"
GATEWAY_URL = "http://localhost:8000"

def register_rgb_contract() -> Dict[str, Any]:
    """Register a new RGB contract for a token"""

    logger.info("🔗 Registering RGB contract...")

    contract_data = {
        "contract_id": "ark_token_001",
        "name": "Ark Token",
        "description": "A demonstration RGB token on the Ark Relay Gateway",
        "interface_id": "RGB20Interface",
        "specification_id": "RGB20Spec",
        "genesis_proof": "base64_encoded_genesis_proof_placeholder",
        "schema_type": "cfa",  # Collectible Fungible Asset
        "metadata": {
            "website": "https://arkrelay.io",
            "icon": "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPGNpcmNsZSBjeD0iMTIiIGN5PSIxMiIgcj0iMTAiIGZpbGw9IiMwMDc0RkYiLz4KPGNpcmNsZSBjeD0iMTIiIGN5PSIxMiIgcj0iNiIgZmlsbD0id2hpdGUiLz4KPC9zdmc+",
            "decimals": 8,
            "total_supply": 21000000
        },
        "creator_pubkey": USER_ALICE,
        "ticker": "ARKT"
    }

    try:
        import requests
        response = requests.post(
            f"{GATEWAY_URL}/rgb/contracts",
            json=contract_data,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 201:
            result = response.json()
            logger.info(f"✅ RGB contract registered: {result['data']['contract_id']}")
            logger.info(f"   Asset ID: {result['data']['asset_id']}")
            logger.info(f"   Schema: {result['data']['schema_type']}")
            return result['data']
        else:
            logger.error(f"❌ Failed to register RGB contract: {response.text}")
            return {}

    except Exception as e:
        logger.error(f"❌ Error registering RGB contract: {e}")
        return {}

def create_rgb_vtxo(user_pubkey: str, contract_id: str, amount: int) -> Dict[str, Any]:
    """Create a VTXO with RGB allocation"""

    logger.info(f"🏗️  Creating RGB VTXO for {user_pubkey[:20]}...")

    vtxo_data = {
        "user_pubkey": user_pubkey,
        "asset_id": f"rgb_{contract_id}",
        "amount_sats": amount,
        "rgb_contract_id": contract_id,
        "rgb_allocation_data": {
            "memo": "Initial RGB token allocation",
            "created_by": "example_script"
        }
    }

    try:
        import requests
        response = requests.post(
            f"{GATEWAY_URL}/rgb/vtxos/create",
            json=vtxo_data,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 201:
            result = response.json()
            logger.info(f"✅ RGB VTXO created: {result['data']['vtxo_id']}")
            logger.info(f"   Amount: {result['data']['amount_sats']} units")
            logger.info(f"   RGB Type: {result['data']['rgb_asset_type']}")
            return result['data']
        else:
            logger.error(f"❌ Failed to create RGB VTXO: {response.text}")
            return {}

    except Exception as e:
        logger.error(f"❌ Error creating RGB VTXO: {e}")
        return {}

def get_user_rgb_vtxos(user_pubkey: str) -> list:
    """Get all RGB VTXOs for a user"""

    logger.info(f"📋 Getting RGB VTXOs for {user_pubkey[:20]}...")

    try:
        import requests
        response = requests.get(
            f"{GATEWAY_URL}/rgb/vtxos/user/{user_pubkey}",
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            result = response.json()
            vtxos = result['data']
            logger.info(f"✅ Found {len(vtxos)} RGB VTXOs")

            for vtxo in vtxos:
                logger.info(f"   VTXO: {vtxo['vtxo_id']}")
                logger.info(f"   Amount: {vtxo['amount_sats']}")
                logger.info(f"   Status: {vtxo['status']}")

            return vtxos
        else:
            logger.error(f"❌ Failed to get RGB VTXOs: {response.text}")
            return []

    except Exception as e:
        logger.error(f"❌ Error getting RGB VTXOs: {e}")
        return []

def transfer_rgb_tokens(from_pubkey: str, to_pubkey: str, allocation_id: str, amount: int) -> bool:
    """Transfer RGB tokens between users"""

    logger.info(f"💸 Transferring {amount} RGB tokens from {from_pubkey[:20]} to {to_pubkey[:20]}...")

    transfer_data = {
        "from_pubkey": from_pubkey,
        "to_pubkey": to_pubkey,
        "allocation_id": allocation_id,
        "amount": amount
    }

    try:
        import requests
        response = requests.post(
            f"{GATEWAY_URL}/rgb/allocations/transfer",
            json=transfer_data,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ RGB transfer successful")
            logger.info(f"   From Allocation: {result['data']['from_allocation_id']}")
            logger.info(f"   To Allocation: {result['data']['to_allocation_id']}")
            logger.info(f"   Amount: {result['data']['amount']}")
            return True
        else:
            logger.error(f"❌ Failed to transfer RGB tokens: {response.text}")
            return False

    except Exception as e:
        logger.error(f"❌ Error transferring RGB tokens: {e}")
        return False

def validate_rgb_vtxo(vtxo_id: str) -> bool:
    """Validate the RGB state of a VTXO"""

    logger.info(f"🔍 Validating RGB VTXO: {vtxo_id}")

    try:
        import requests
        response = requests.get(
            f"{GATEWAY_URL}/rgb/vtxos/{vtxo_id}/validate",
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            result = response.json()
            validation = result['data']

            logger.info(f"✅ RGB VTXO validation result:")
            logger.info(f"   Valid: {validation['valid']}")
            logger.info(f"   Contract: {validation['contract_id']}")
            logger.info(f"   Amount: {validation['amount']}")
            logger.info(f"   Proof Valid: {validation['proof_valid']}")
            logger.info(f"   State Consistent: {validation['state_consistent']}")

            return validation['valid']
        else:
            logger.error(f"❌ Failed to validate RGB VTXO: {response.text}")
            return False

    except Exception as e:
        logger.error(f"❌ Error validating RGB VTXO: {e}")
        return False

def get_rgb_stats() -> Dict[str, Any]:
    """Get RGB system statistics"""

    logger.info("📊 Getting RGB system statistics...")

    try:
        import requests
        response = requests.get(
            f"{GATEWAY_URL}/rgb/stats",
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            result = response.json()
            stats = result['data']

            logger.info("✅ RGB System Statistics:")
            logger.info(f"   Contracts: {stats['contracts']['active']} active, {stats['contracts']['total']} total")
            logger.info(f"   Allocations: {stats['allocations']['active']} active, {stats['allocations']['total']} total")
            logger.info(f"   Total Value: {stats['allocations']['total_value']}")

            # Schema breakdown
            for schema in stats['schema_breakdown']:
                logger.info(f"   {schema['schema_type'].upper()}: {schema['contract_count']} contracts, {schema['total_issued']} issued")

            return stats
        else:
            logger.error(f"❌ Failed to get RGB stats: {response.text}")
            return {}

    except Exception as e:
        logger.error(f"❌ Error getting RGB stats: {e}")
        return {}

def main():
    """Main demonstration function"""

    logger.info("🚀 Starting RGB Token Example")
    logger.info("=" * 50)

    # Check RGB service health
    try:
        import requests
        response = requests.get(f"{GATEWAY_URL}/rgb/health")
        if response.status_code == 200:
            logger.info("✅ RGB service is healthy")
        else:
            logger.error("❌ RGB service is not available")
            return
    except:
        logger.error("❌ Cannot connect to RGB service")
        logger.info("   Make sure the Ark Relay Gateway is running")
        return

    # Step 1: Register RGB contract
    logger.info("\n📝 Step 1: Register RGB Contract")
    contract = register_rgb_contract()
    if not contract:
        logger.error("❌ Failed to register contract, exiting")
        return

    contract_id = contract['contract_id']

    # Step 2: Create RGB VTXOs for Alice and Bob
    logger.info("\n🏗️  Step 2: Create RGB VTXOs")

    alice_vtxo = create_rgb_vtxo(USER_ALICE, contract_id, 1000000)
    if not alice_vtxo:
        logger.error("❌ Failed to create Alice's VTXO")
        return

    bob_vtxo = create_rgb_vtxo(USER_BOB, contract_id, 500000)
    if not bob_vtxo:
        logger.error("❌ Failed to create Bob's VTXO")
        return

    # Wait a moment for creation to process
    time.sleep(1)

    # Step 3: Check user VTXOs
    logger.info("\n📋 Step 3: Check User VTXOs")

    alice_vtxos = get_user_rgb_vtxos(USER_ALICE)
    bob_vtxos = get_user_rgb_vtxos(USER_BOB)

    if not alice_vtxos:
        logger.error("❌ Alice has no RGB VTXOs")
        return

    # Step 4: Validate VTXOs
    logger.info("\n🔍 Step 4: Validate RGB VTXOs")

    for vtxo in alice_vtxos:
        validate_rgb_vtxo(vtxo['vtxo_id'])

    # Step 5: Transfer RGB tokens (simulation)
    logger.info("\n💸 Step 5: Transfer RGB Tokens")

    # Note: In a real scenario, you would need the actual allocation_id
    # For this example, we'll simulate the transfer
    allocation_id = alice_vtxos[0]['rgb_allocation_id']
    transfer_success = transfer_rgb_tokens(
        USER_ALICE,
        USER_BOB,
        allocation_id,
        100000  # Transfer 100k tokens
    )

    # Step 6: Get final statistics
    logger.info("\n📊 Step 6: Final Statistics")
    get_rgb_stats()

    # Step 7: Verify final state
    logger.info("\n🔍 Step 7: Verify Final State")

    final_alice_vtxos = get_user_rgb_vtxos(USER_ALICE)
    final_bob_vtxos = get_user_rgb_vtxos(USER_BOB)

    logger.info("\n🎉 RGB Token Example Completed!")
    logger.info("=" * 50)
    logger.info("Summary:")
    logger.info(f"   - Contract: {contract_id}")
    logger.info(f"   - Alice VTXOs: {len(final_alice_vtxos)}")
    logger.info(f"   - Bob VTXOs: {len(final_bob_vtxos)}")
    logger.info("   - RGB tokens successfully created and managed!")

if __name__ == "__main__":
    main()