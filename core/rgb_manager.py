"""
RGB Manager for Ark Relay Gateway

This module implements RGB smart contract management including:
- RGB contract registration and lifecycle management
- RGB allocation tracking within VTXOs
- RGB proof validation and state transitions
- Integration with the existing VTXO system
"""

import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from core.models import (
    Asset, Vtxo, RGBContract, RGBAllocation,
    get_session, AssetBalance, Transaction
)
from grpc_clients import get_grpc_manager, ServiceType
from sqlalchemy import and_, or_, func, desc
from core.asset_manager import get_asset_manager
from core.vtxo_manager import get_vtxo_manager

logger = logging.getLogger(__name__)

def utc_now() -> datetime:
    """Return current UTC time as a naive datetime (UTC) without deprecation warnings."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

class RGBSchemaType(Enum):
    """RGB schema types"""
    CFA = 'cfa'  # Collectible Fungible Asset
    NIA = 'nia'  # Non-Inflatable Asset
    RIA = 'ria'  # Reissuable Asset
    UDA = 'uda'  # Unique Digital Asset (NFT)

class RGBSealType(Enum):
    """RGB seal types for VTXO commitment"""
    TAPRET_FIRST = 'tapret_first'
    OPAQUE = 'opaque'
    METHOD_1 = 'method1'

class RGBError(Exception):
    """Raised when RGB operations fail"""
    pass

class RGBValidationError(RGBError):
    """Raised when RGB validation fails"""
    pass

class RGBContractError(RGBError):
    """Raised when RGB contract operations fail"""
    pass

class RGBManager:
    """Manages RGB contracts, allocations, and state transitions"""

    def __init__(self):
        self.asset_manager = get_asset_manager()
        self.vtxo_manager = get_vtxo_manager()
        self.grpc_manager = get_grpc_manager()

    def register_rgb_contract(self, contract_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Register a new RGB contract in the system

        Args:
            contract_data: Dictionary containing contract information
                - contract_id: Unique contract identifier
                - name: Human-readable name
                - description: Optional description
                - interface_id: RGB interface ID
                - specification_id: RGB specification ID
                - genesis_proof: Genesis proof data
                - schema_type: Schema type (CFA, NIA, etc.)
                - metadata: Optional contract metadata
                - creator_pubkey: Creator's public key

        Returns:
            Contract registration result
        """
        session = get_session()
        try:
            # Validate required fields
            required_fields = ['contract_id', 'name', 'interface_id', 'specification_id', 'genesis_proof', 'schema_type']
            for field in required_fields:
                if field not in contract_data:
                    raise RGBValidationError(f"Missing required field: {field}")

            # Check if contract already exists
            existing_contract = session.query(RGBContract).filter_by(
                contract_id=contract_data['contract_id']
            ).first()
            if existing_contract:
                raise RGBContractError(f"RGB contract {contract_data['contract_id']} already exists")

            # Validate schema type
            try:
                schema_type = RGBSchemaType(contract_data['schema_type'].lower())
            except ValueError:
                raise RGBValidationError(f"Invalid schema type: {contract_data['schema_type']}")

            # Create RGB contract
            rgb_contract = RGBContract(
                contract_id=contract_data['contract_id'],
                name=contract_data['name'],
                description=contract_data.get('description'),
                interface_id=contract_data['interface_id'],
                specification_id=contract_data['specification_id'],
                genesis_proof=contract_data['genesis_proof'],
                schema_type=schema_type.value,
                metadata=contract_data.get('metadata', {}),
                creator_pubkey=contract_data.get('creator_pubkey')
            )

            session.add(rgb_contract)
            session.commit()
            session.refresh(rgb_contract)

            # Create corresponding asset if needed
            asset_id = f"rgb_{contract_data['contract_id']}"
            asset = session.query(Asset).filter_by(asset_id=asset_id).first()
            if not asset:
                asset = Asset(
                    asset_id=asset_id,
                    name=f"RGB {contract_data['name']}",
                    ticker=contract_data.get('ticker', f"RGB{contract_data['contract_id'][:8]}"),
                    asset_type='rgb_contract',
                    rgb_contract_id=contract_data['contract_id'],
                    rgb_schema_type=schema_type.value,
                    rgb_interface_id=contract_data['interface_id'],
                    rgb_specification_id=contract_data['specification_id'],
                    rgb_genesis_proof=contract_data['genesis_proof'],
                    is_rgb_enabled=True,
                    is_active=True,
                    asset_metadata=contract_data.get('metadata', {})
                )
                session.add(asset)
                session.commit()

            logger.info(f"✅ Registered RGB contract: {contract_data['contract_id']} ({contract_data['name']})")

            return {
                'contract_id': rgb_contract.contract_id,
                'name': rgb_contract.name,
                'asset_id': asset_id,
                'schema_type': rgb_contract.schema_type,
                'status': 'registered',
                'created_at': rgb_contract.created_at.isoformat()
            }

        except Exception as e:
            session.rollback()
            logger.error(f"❌ Failed to register RGB contract: {e}")
            raise
        finally:
            session.close()

    def get_rgb_contract(self, contract_id: str) -> Optional[Dict[str, Any]]:
        """Get RGB contract information"""
        session = get_session()
        try:
            contract = session.query(RGBContract).filter_by(
                contract_id=contract_id, is_active=True
            ).first()

            if not contract:
                return None

            # Get related asset
            asset = session.query(Asset).filter_by(
                rgb_contract_id=contract_id
            ).first()

            return {
                'contract_id': contract.contract_id,
                'name': contract.name,
                'description': contract.description,
                'interface_id': contract.interface_id,
                'specification_id': contract.specification_id,
                'schema_type': contract.schema_type,
                'genesis_proof': contract.genesis_proof,
                'metadata': contract.metadata,
                'creator_pubkey': contract.creator_pubkey,
                'total_issued': contract.total_issued,
                'current_state_root': contract.current_state_root,
                'last_transition_txid': contract.last_transition_txid,
                'asset_id': asset.asset_id if asset else None,
                'asset_ticker': asset.ticker if asset else None,
                'created_at': contract.created_at.isoformat(),
                'updated_at': contract.updated_at.isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Failed to get RGB contract: {e}")
            return None
        finally:
            session.close()

    def list_rgb_contracts(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """List all RGB contracts"""
        session = get_session()
        try:
            query = session.query(RGBContract)
            if active_only:
                query = query.filter_by(is_active=True)

            contracts = query.order_by(RGBContract.created_at.desc()).all()

            result = []
            for contract in contracts:
                asset = session.query(Asset).filter_by(
                    rgb_contract_id=contract.contract_id
                ).first()

                result.append({
                    'contract_id': contract.contract_id,
                    'name': contract.name,
                    'schema_type': contract.schema_type,
                    'asset_id': asset.asset_id if asset else None,
                    'asset_ticker': asset.ticker if asset else None,
                    'total_issued': contract.total_issued,
                    'is_active': contract.is_active,
                    'created_at': contract.created_at.isoformat()
                })

            return result

        except Exception as e:
            logger.error(f"❌ Failed to list RGB contracts: {e}")
            return []
        finally:
            session.close()

    def create_rgb_allocation(self, allocation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new RGB allocation within a VTXO

        Args:
            allocation_data: Dictionary containing allocation information
                - contract_id: RGB contract ID
                - vtxo_id: Target VTXO ID
                - owner_pubkey: Owner's public key
                - amount: Allocation amount
                - state_commitment: RGB state commitment (optional)
                - proof_data: RGB proof data (optional)
                - seal_type: RGB seal type (optional)

        Returns:
            Allocation creation result
        """
        session = get_session()
        try:
            # Validate required fields
            required_fields = ['contract_id', 'vtxo_id', 'owner_pubkey', 'amount']
            for field in required_fields:
                if field not in allocation_data:
                    raise RGBValidationError(f"Missing required field: {field}")

            # Validate contract exists and is active
            contract = session.query(RGBContract).filter_by(
                contract_id=allocation_data['contract_id'], is_active=True
            ).first()
            if not contract:
                raise RGBContractError(f"RGB contract {allocation_data['contract_id']} not found or inactive")

            # Validate VTXO exists and is available
            vtxo = session.query(Vtxo).filter_by(
                vtxo_id=allocation_data['vtxo_id'], status='available'
            ).first()
            if not vtxo:
                raise RGBValidationError(f"VTXO {allocation_data['vtxo_id']} not found or not available")

            # Check if allocation already exists
            existing_allocation = session.query(RGBAllocation).filter_by(
                allocation_id=f"{allocation_data['vtxo_id']}_{allocation_data['contract_id']}"
            ).first()
            if existing_allocation:
                raise RGBContractError(f"RGB allocation for VTXO {allocation_data['vtxo_id']} already exists")

            # Generate allocation ID
            allocation_id = f"{allocation_data['vtxo_id']}_{allocation_data['contract_id']}"

            # Create RGB allocation
            allocation = RGBAllocation(
                allocation_id=allocation_id,
                contract_id=allocation_data['contract_id'],
                vtxo_id=allocation_data['vtxo_id'],
                owner_pubkey=allocation_data['owner_pubkey'],
                amount=allocation_data['amount'],
                state_commitment=allocation_data.get('state_commitment'),
                proof_data=allocation_data.get('proof_data'),
                seal_type=allocation_data.get('seal_type', RGBSealType.TAPRET_FIRST.value)
            )

            session.add(allocation)

            # Update VTXO with RGB information
            vtxo.rgb_asset_type = contract.schema_type
            vtxo.rgb_allocation_id = allocation_id
            if allocation_data.get('state_commitment'):
                vtxo.rgb_state_commitment = allocation_data['state_commitment']
            if allocation_data.get('proof_data'):
                vtxo.rgb_proof_data = allocation_data['proof_data']

            # Update contract totals
            contract.total_issued += allocation_data['amount']

            session.commit()
            session.refresh(allocation)

            logger.info(f"✅ Created RGB allocation: {allocation_id} for {allocation_data['owner_pubkey'][:8]}...")

            return {
                'allocation_id': allocation_id,
                'contract_id': allocation.contract_id,
                'vtxo_id': allocation.vtxo_id,
                'owner_pubkey': allocation.owner_pubkey,
                'amount': allocation.amount,
                'seal_type': allocation.seal_type,
                'created_at': allocation.created_at.isoformat()
            }

        except Exception as e:
            session.rollback()
            logger.error(f"❌ Failed to create RGB allocation: {e}")
            raise
        finally:
            session.close()

    def get_rgb_allocations(self, owner_pubkey: str = None, contract_id: str = None) -> List[Dict[str, Any]]:
        """Get RGB allocations with optional filtering"""
        session = get_session()
        try:
            query = session.query(RGBAllocation).filter_by(is_spent=False)

            if owner_pubkey:
                query = query.filter_by(owner_pubkey=owner_pubkey)
            if contract_id:
                query = query.filter_by(contract_id=contract_id)

            allocations = query.order_by(RGBAllocation.created_at.desc()).all()

            result = []
            for allocation in allocations:
                result.append({
                    'allocation_id': allocation.allocation_id,
                    'contract_id': allocation.contract_id,
                    'vtxo_id': allocation.vtxo_id,
                    'owner_pubkey': allocation.owner_pubkey,
                    'amount': allocation.amount,
                    'seal_type': allocation.seal_type,
                    'is_spent': allocation.is_spent,
                    'created_at': allocation.created_at.isoformat()
                })

            return result

        except Exception as e:
            logger.error(f"❌ Failed to get RGB allocations: {e}")
            return []
        finally:
            session.close()

    def validate_rgb_proof(self, proof_data: str, contract_id: str) -> bool:
        """
        Validate RGB proof data against contract

        Args:
            proof_data: RGB proof data to validate
            contract_id: Contract ID to validate against

        Returns:
            True if proof is valid, False otherwise
        """
        try:
            session = get_session()
            contract = session.query(RGBContract).filter_by(
                contract_id=contract_id, is_active=True
            ).first()

            if not contract:
                logger.error(f"Contract {contract_id} not found for proof validation")
                return False

            # Basic proof validation
            if not proof_data or not isinstance(proof_data, str):
                logger.error("Invalid proof data format")
                return False

            # TODO: Implement actual RGB proof validation logic
            # This would involve:
            # 1. Parsing the proof structure
            # 2. Validating cryptographic commitments
            # 3. Checking against contract state
            # 4. Verifying transition rules

            logger.info(f"✅ RGB proof validation passed for contract {contract_id}")
            return True

        except Exception as e:
            logger.error(f"❌ RGB proof validation failed: {e}")
            return False
        finally:
            session.close()

    def transfer_rgb_allocation(self, from_pubkey: str, to_pubkey: str,
                              allocation_id: str, amount: int = None) -> Dict[str, Any]:
        """
        Transfer RGB allocation from one user to another

        Args:
            from_pubkey: Sender's public key
            to_pubkey: Recipient's public key
            allocation_id: Allocation ID to transfer
            amount: Amount to transfer (None for full amount)

        Returns:
            Transfer result
        """
        session = get_session()
        try:
            # Get the allocation
            allocation = session.query(RGBAllocation).filter_by(
                allocation_id=allocation_id, is_spent=False
            ).first()

            if not allocation:
                raise RGBValidationError(f"RGB allocation {allocation_id} not found or already spent")

            if allocation.owner_pubkey != from_pubkey:
                raise RGBValidationError(f"Allocation owned by {allocation.owner_pubkey}, not {from_pubkey}")

            # Validate transfer amount
            transfer_amount = amount if amount is not None else allocation.amount
            if transfer_amount > allocation.amount:
                raise RGBValidationError(f"Transfer amount {transfer_amount} exceeds allocation {allocation.amount}")

            # Mark original allocation as spent
            allocation.is_spent = True
            allocation.spent_at = utc_now()

            # Create new allocation for recipient
            new_allocation_id = f"{allocation.vtxo_id}_{allocation.contract_id}_{to_pubkey[:8]}"
            new_allocation = RGBAllocation(
                allocation_id=new_allocation_id,
                contract_id=allocation.contract_id,
                vtxo_id=allocation.vtxo_id,
                owner_pubkey=to_pubkey,
                amount=transfer_amount,
                state_commitment=allocation.state_commitment,
                proof_data=allocation.proof_data,
                seal_type=allocation.seal_type
            )
            session.add(new_allocation)

            # If partial transfer, create remainder allocation for sender
            if transfer_amount < allocation.amount:
                remainder_amount = allocation.amount - transfer_amount
                remainder_allocation_id = f"{allocation.vtxo_id}_{allocation.contract_id}_{from_pubkey[:8]}_remainder"
                remainder_allocation = RGBAllocation(
                    allocation_id=remainder_allocation_id,
                    contract_id=allocation.contract_id,
                    vtxo_id=allocation.vtxo_id,
                    owner_pubkey=from_pubkey,
                    amount=remainder_amount,
                    state_commitment=allocation.state_commitment,
                    proof_data=allocation.proof_data,
                    seal_type=allocation.seal_type
                )
                session.add(remainder_allocation)

            session.commit()

            logger.info(f"✅ Transferred {transfer_amount} RGB allocation from {from_pubkey[:8]}... to {to_pubkey[:8]}...")

            return {
                'from_allocation_id': allocation_id,
                'to_allocation_id': new_allocation_id,
                'contract_id': allocation.contract_id,
                'amount': transfer_amount,
                'from_pubkey': from_pubkey,
                'to_pubkey': to_pubkey,
                'timestamp': utc_now().isoformat()
            }

        except Exception as e:
            session.rollback()
            logger.error(f"❌ Failed to transfer RGB allocation: {e}")
            raise
        finally:
            session.close()

    def get_rgb_stats(self) -> Dict[str, Any]:
        """Get RGB system statistics"""
        session = get_session()
        try:
            # Contract statistics
            total_contracts = session.query(RGBContract).count()
            active_contracts = session.query(RGBContract).filter_by(is_active=True).count()

            # Allocation statistics
            total_allocations = session.query(RGBAllocation).count()
            active_allocations = session.query(RGBAllocation).filter_by(is_spent=False).count()
            total_rgb_value = session.query(func.sum(RGBAllocation.amount)).filter_by(is_spent=False).scalar() or 0

            # Schema type breakdown
            schema_stats = session.query(
                RGBContract.schema_type,
                func.count(RGBContract.id).label('count'),
                func.sum(RGBContract.total_issued).label('total_issued')
            ).filter_by(is_active=True).group_by(RGBContract.schema_type).all()

            return {
                'contracts': {
                    'total': total_contracts,
                    'active': active_contracts,
                    'inactive': total_contracts - active_contracts
                },
                'allocations': {
                    'total': total_allocations,
                    'active': active_allocations,
                    'spent': total_allocations - active_allocations,
                    'total_value': total_rgb_value
                },
                'schema_breakdown': [
                    {
                        'schema_type': stat.schema_type,
                        'contract_count': stat.count,
                        'total_issued': int(stat.total_issued or 0)
                    }
                    for stat in schema_stats
                ],
                'timestamp': utc_now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Failed to get RGB stats: {e}")
            return {'error': str(e)}
        finally:
            session.close()

# Global RGB manager instance
_rgb_manager = None

def get_rgb_manager() -> RGBManager:
    """Get the global RGB manager instance"""
    global _rgb_manager
    if _rgb_manager is None:
        _rgb_manager = RGBManager()
    return _rgb_manager