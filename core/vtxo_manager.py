"""
VTXO Management System for Ark Relay Gateway

This module implements the complete VTXO lifecycle management including:
- Inventory monitoring and replenishment
- VTXO assignment and tracking
- Fee estimation
- Batch creation
- Expiration handling
- L1 settlement operations
"""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from sqlalchemy import func, and_, or_
from core.models import Vtxo, Asset, AssetBalance, Transaction, SigningSession, RGBAllocation, get_session
from grpc_clients import get_grpc_manager, ServiceType
from core.asset_manager import get_asset_manager
from core.rgb_manager import get_rgb_manager

logger = logging.getLogger(__name__)

def utc_now() -> datetime:
    """Return current UTC time as a naive datetime (UTC) without deprecation warnings."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

class VtxoInventoryMonitor:
    """Monitors VTXO inventory levels and triggers replenishment"""

    def __init__(self):
        self.min_vtxos_per_asset = 10  # Minimum VTXOs to maintain per asset
        self.max_vtxos_per_asset = 100  # Maximum VTXOs to create in one batch
        self.replenishment_threshold = 0.3  # Trigger replenishment at 30% capacity
        self.monitoring_interval = 300  # Check every 5 minutes
        self.running = False

    def start_monitoring(self):
        """Start the inventory monitoring thread"""
        self.running = True
        monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor_thread.start()
        logger.info("🔄 VTXO inventory monitoring started")

    def stop_monitoring(self):
        """Stop the inventory monitoring thread"""
        self.running = False
        logger.info("⏹️  VTXO inventory monitoring stopped")

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                self.check_inventory_levels()
                time.sleep(self.monitoring_interval)
            except Exception as e:
                logger.error(f"❌ Inventory monitoring error: {e}")
                time.sleep(60)  # Wait before retrying

    def check_inventory_levels(self):
        """Check VTXO inventory levels for all assets"""
        session = get_session()
        try:
            # Get all active assets
            assets = session.query(Asset).filter(Asset.is_active == True).all()

            for asset in assets:
                inventory_status = self.get_asset_inventory_status(session, asset.asset_id)

                if inventory_status['needs_replenishment']:
                    logger.info(f"📦 Asset {asset.ticker} needs VTXO replenishment. "
                              f"Available: {inventory_status['available_vtxos']}, "
                              f"Assigned: {inventory_status['assigned_vtxos']}")

                    # Trigger replenishment
                    replenishment_needed = self.calculate_replenishment_amount(inventory_status)
                    if replenishment_needed > 0:
                        self.trigger_replenishment(asset.asset_id, replenishment_needed)

        finally:
            session.close()

    def get_asset_inventory_status(self, session, asset_id: str) -> Dict:
        """Get current inventory status for an asset"""
        # Count VTXOs by status
        available_count = session.query(func.count(Vtxo.id)).filter(
            and_(Vtxo.asset_id == asset_id, Vtxo.status == 'available')
        ).scalar() or 0

        assigned_count = session.query(func.count(Vtxo.id)).filter(
            and_(Vtxo.asset_id == asset_id, Vtxo.status == 'assigned')
        ).scalar() or 0

        total_count = session.query(func.count(Vtxo.id)).filter(
            Vtxo.asset_id == asset_id
        ).scalar() or 0

        # Calculate utilization
        utilization = assigned_count / total_count if total_count > 0 else 0

        # Determine if replenishment is needed
        needs_replenishment = (
            available_count < self.min_vtxos_per_asset or
            utilization > self.replenishment_threshold or
            total_count < self.min_vtxos_per_asset
        )

        return {
            'asset_id': asset_id,
            'available_vtxos': available_count,
            'assigned_vtxos': assigned_count,
            'total_vtxos': total_count,
            'utilization': utilization,
            'needs_replenishment': needs_replenishment
        }

    def calculate_replenishment_amount(self, inventory_status: Dict) -> int:
        """Calculate how many VTXOs to create"""
        available = inventory_status['available_vtxos']
        total = inventory_status['total_vtxos']

        # Calculate deficit to reach minimum
        deficit_to_min = max(0, self.min_vtxos_per_asset - available)

        # Calculate additional needed based on utilization
        if total > 0:
            additional_needed = int(total * 0.2)  # 20% buffer
        else:
            additional_needed = self.min_vtxos_per_asset

        return min(deficit_to_min + additional_needed, self.max_vtxos_per_asset)

    def trigger_replenishment(self, asset_id: str, count: int):
        """Trigger VTXO replenishment process"""
        try:
            logger.info(f"🔄 Triggering VTXO replenishment for asset {asset_id}: {count} VTXOs")

            # Enqueue replenishment job
            from core.tasks import enqueue_vtxo_replenishment
            enqueue_vtxo_replenishment(asset_id, count)

        except Exception as e:
            logger.error(f"❌ Failed to trigger VTXO replenishment: {e}")


class VtxoManager:
    """Main VTXO management class"""

    def __init__(self):
        self.inventory_monitor = VtxoInventoryMonitor()
        self.default_vtxo_amount = 100000  # 100k sats default VTXO size
        self.vtxo_expiry_hours = 24  # VTXOs expire after 24 hours
        self.dust_limit_sats = 1  # VTXOs are off-chain, so dust limit is 1 satoshi

    def start_services(self):
        """Start all VTXO management services"""
        self.inventory_monitor.start_monitoring()
        logger.info("✅ VTXO management services started")

    def stop_services(self):
        """Stop all VTXO management services"""
        self.inventory_monitor.stop_monitoring()
        logger.info("⏹️  VTXO management services stopped")

    def create_vtxo_batch(self, asset_id: str, count: int, amount_sats: Optional[int] = None) -> bool:
        """Create a batch of new VTXOs"""
        if amount_sats is None:
            amount_sats = self.default_vtxo_amount

        session = get_session()
        try:
            # Verify asset exists
            asset = session.query(Asset).filter(Asset.asset_id == asset_id).first()
            if not asset:
                logger.error(f"Asset {asset_id} not found")
                return False

            # Estimate fees for batch creation
            fee_estimate = self.estimate_batch_creation_fees(count, amount_sats)
            logger.info(f"💰 Estimated batch creation fees: {fee_estimate} sats")

            # Create VTXOs using ARKD
            grpc_manager = get_grpc_manager()
            arkd_client = grpc_manager.get_client(ServiceType.ARKD)

            if not arkd_client:
                logger.error("ARKD client not available")
                return False

            # Create the VTXO batch
            vtxo_batch = arkd_client.create_vtxo_batch(
                asset_id=asset_id,
                count=count,
                amount_sats=amount_sats,
                fee_sats=fee_estimate
            )

            if not vtxo_batch:
                logger.error("Failed to create VTXO batch")
                return False

            # Store VTXOs in database
            self._store_vtxo_batch(session, vtxo_batch, asset_id, amount_sats)

            logger.info(f"✅ Created {count} VTXOs for asset {asset_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to create VTXO batch: {e}")
            return False
        finally:
            session.close()

    def _store_vtxo_batch(self, session, vtxo_batch: Dict, asset_id: str, amount_sats: int):
        """Store created VTXOs in database"""
        expiry_time = utc_now() + timedelta(hours=self.vtxo_expiry_hours)

        for vtxo_data in vtxo_batch.get('vtxos', []):
            vtxo = Vtxo(
                vtxo_id=vtxo_data['vtxo_id'],
                txid=vtxo_data['txid'],
                vout=vtxo_data['vout'],
                amount_sats=amount_sats,
                script_pubkey=bytes.fromhex(vtxo_data['script_pubkey']),
                asset_id=asset_id,
                user_pubkey='',  # Unassigned initially
                status='available',
                expires_at=expiry_time
            )
            session.add(vtxo)

        session.commit()

    def estimate_batch_creation_fees(self, count: int, amount_sats: int) -> int:
        """Estimate fees for creating a batch of VTXOs"""
        # Basic fee estimation based on transaction size
        # In practice, this would query the fee estimator
        base_fee = 1000  # Base transaction fee
        per_vtxo_fee = 500  # Additional fee per VTXO

        return base_fee + (count * per_vtxo_fee)

    def assign_vtxo_to_user(self, user_pubkey: str, asset_id: str, amount_needed: int) -> Optional[Vtxo]:
        """Assign an available VTXO to a user"""
        session = get_session()
        try:
            # Find an available VTXO for the asset
            vtxo = session.query(Vtxo).filter(
                and_(
                    Vtxo.asset_id == asset_id,
                    Vtxo.status == 'available',
                    Vtxo.amount_sats >= amount_needed,
                    Vtxo.expires_at > utc_now()
                )
            ).order_by(Vtxo.amount_sats.asc()).first()

            if not vtxo:
                logger.warning(f"No available VTXO for user {user_pubkey[:8]}... asset {asset_id}")
                return None

            # Assign VTXO to user
            vtxo.user_pubkey = user_pubkey
            vtxo.status = 'assigned'
            session.commit()

            logger.info(f"✅ Assigned VTXO {vtxo.vtxo_id} to user {user_pubkey[:8]}...")
            return vtxo

        except Exception as e:
            logger.error(f"❌ Failed to assign VTXO: {e}")
            session.rollback()
            return None
        finally:
            session.close()

    def mark_vtxo_spent(self, vtxo_id: str, spending_txid: str):
        """Mark a VTXO as spent"""
        session = get_session()
        try:
            vtxo = session.query(Vtxo).filter(Vtxo.vtxo_id == vtxo_id).first()
            if vtxo:
                vtxo.status = 'spent'
                vtxo.spending_txid = spending_txid
                session.commit()
                logger.info(f"✅ Marked VTXO {vtxo_id} as spent")
            else:
                logger.warning(f"VTXO {vtxo_id} not found")
        except Exception as e:
            logger.error(f"❌ Failed to mark VTXO as spent: {e}")
            session.rollback()
        finally:
            session.close()

    def get_user_vtxos(self, user_pubkey: str, asset_id: Optional[str] = None) -> List[Vtxo]:
        """Get all VTXOs assigned to a user"""
        session = get_session()
        try:
            query = session.query(Vtxo).filter(Vtxo.user_pubkey == user_pubkey)

            if asset_id:
                query = query.filter(Vtxo.asset_id == asset_id)

            vtxos = query.filter(Vtxo.status == 'assigned').all()
            return vtxos

        except Exception as e:
            logger.error(f"❌ Failed to get user VTXOs: {e}")
            return []
        finally:
            session.close()

    def cleanup_expired_vtxos(self):
        """Clean up expired VTXOs"""
        session = get_session()
        try:
            expired_vtxos = session.query(Vtxo).filter(
                and_(
                    Vtxo.expires_at <= utc_now(),
                    Vtxo.status == 'available'
                )
            ).all()

            count = len(expired_vtxos)
            for vtxo in expired_vtxos:
                vtxo.status = 'expired'

            session.commit()

            if count > 0:
                logger.info(f"🧹 Cleaned up {count} expired VTXOs")

            return count

        except Exception as e:
            logger.error(f"❌ Failed to cleanup expired VTXOs: {e}")
            session.rollback()
            return 0
        finally:
            session.close()

    # RGB-specific VTXO operations

    def create_rgb_vtxo(self, user_pubkey: str, asset_id: str, amount_sats: int,
                       rgb_contract_id: str, rgb_allocation_data: Dict = None) -> Optional[Vtxo]:
        """
        Create a VTXO specifically for RGB allocations

        Args:
            user_pubkey: User's public key
            asset_id: Asset ID
            amount_sats: Amount in satoshis
            rgb_contract_id: RGB contract ID
            rgb_allocation_data: Optional RGB allocation data

        Returns:
            Created VTXO or None if failed
        """
        session = get_session()
        try:
            # Validate RGB contract exists
            rgb_manager = get_rgb_manager()
            contract = rgb_manager.get_rgb_contract(rgb_contract_id)
            if not contract:
                logger.error(f"RGB contract {rgb_contract_id} not found")
                return None

            # Create the VTXO
            vtxo = self.assign_vtxo_to_user(user_pubkey, asset_id, amount_sats)
            if not vtxo:
                logger.error(f"Failed to assign VTXO for RGB allocation")
                return None

            # Update VTXO with RGB information
            vtxo.rgb_asset_type = contract['schema_type']
            vtxo.rgb_contract_state = rgb_allocation_data or {}

            session.commit()

            # Create RGB allocation
            allocation_data = {
                'contract_id': rgb_contract_id,
                'vtxo_id': vtxo.vtxo_id,
                'owner_pubkey': user_pubkey,
                'amount': amount_sats,
                'state_commitment': vtxo.rgb_state_commitment,
                'proof_data': vtxo.rgb_proof_data
            }

            allocation = rgb_manager.create_rgb_allocation(allocation_data)
            if allocation:
                logger.info(f"✅ Created RGB VTXO {vtxo.vtxo_id} for contract {rgb_contract_id}")
                return vtxo
            else:
                logger.error(f"Failed to create RGB allocation for VTXO {vtxo.vtxo_id}")
                return None

        except Exception as e:
            session.rollback()
            logger.error(f"❌ Failed to create RGB VTXO: {e}")
            return None
        finally:
            session.close()

    def split_rgb_vtxo(self, vtxo_id: str, split_amounts: List[int],
                      rgb_allocation_splits: List[Dict] = None) -> bool:
        """
        Split an RGB VTXO into multiple VTXOs with corresponding allocations

        Args:
            vtxo_id: VTXO ID to split
            split_amounts: List of amounts for each split
            rgb_allocation_splits: List of RGB allocation data for each split

        Returns:
            True if successful, False otherwise
        """
        session = get_session()
        try:
            # Get the original VTXO
            vtxo = session.query(Vtxo).filter_by(vtxo_id=vtxo_id).first()
            if not vtxo or vtxo.status != 'assigned':
                logger.error(f"VTXO {vtxo_id} not found or not assigned")
                return False

            # Validate RGB allocation data
            if rgb_allocation_splits and len(rgb_allocation_splits) != len(split_amounts):
                logger.error("RGB allocation splits must match split amounts")
                return False

            # Perform the split using existing VTXO logic
            split_result = self._perform_vtxo_split(vtxo, split_amounts)
            if not split_result:
                logger.error(f"Failed to split VTXO {vtxo_id}")
                return False

            # Create RGB allocations for each new VTXO
            if rgb_allocation_splits and vtxo.rgb_allocation_id:
                rgb_manager = get_rgb_manager()
                for i, (new_vtxo_id, allocation_data) in enumerate(zip(split_result['new_vtxo_ids'], rgb_allocation_splits)):
                    allocation_data.update({
                        'vtxo_id': new_vtxo_id,
                        'contract_id': allocation_data.get('contract_id'),
                        'owner_pubkey': vtxo.user_pubkey,
                        'amount': split_amounts[i]
                    })

                    try:
                        rgb_manager.create_rgb_allocation(allocation_data)
                    except Exception as e:
                        logger.error(f"Failed to create RGB allocation for split VTXO {new_vtxo_id}: {e}")
                        return False

            # Mark original VTXO as spent
            vtxo.status = 'spent'
            session.commit()

            logger.info(f"✅ Split RGB VTXO {vtxo_id} into {len(split_amounts)} VTXOs")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"❌ Failed to split RGB VTXO: {e}")
            return False
        finally:
            session.close()

    def get_user_rgb_vtxos(self, user_pubkey: str, contract_id: str = None) -> List[Vtxo]:
        """
        Get all RGB VTXOs for a user, optionally filtered by contract

        Args:
            user_pubkey: User's public key
            contract_id: Optional RGB contract ID filter

        Returns:
            List of RGB VTXOs
        """
        session = get_session()
        try:
            query = session.query(Vtxo).filter(
                and_(
                    Vtxo.user_pubkey == user_pubkey,
                    Vtxo.rgb_asset_type.isnot(None),
                    Vtxo.status == 'assigned'
                )
            )

            if contract_id:
                # Join with RGB allocation to filter by contract
                query = query.join(RGBAllocation).filter(
                    RGBAllocation.contract_id == contract_id,
                    RGBAllocation.is_spent == False
                )

            vtxos = query.order_by(Vtxo.created_at.desc()).all()
            return vtxos

        except Exception as e:
            logger.error(f"❌ Failed to get user RGB VTXOs: {e}")
            return []
        finally:
            session.close()

    def validate_rgb_vtxo_state(self, vtxo_id: str) -> Dict[str, Any]:
        """
        Validate the RGB state of a VTXO

        Args:
            vtxo_id: VTXO ID to validate

        Returns:
            Validation result with details
        """
        session = get_session()
        try:
            # Get the VTXO
            vtxo = session.query(Vtxo).filter_by(vtxo_id=vtxo_id).first()
            if not vtxo:
                return {'error': 'VTXO not found', 'valid': False}

            if not vtxo.rgb_asset_type:
                return {'error': 'VTXO is not RGB-enabled', 'valid': False}

            # Get RGB allocation
            allocation = session.query(RGBAllocation).filter_by(
                vtxo_id=vtxo_id, is_spent=False
            ).first()

            if not allocation:
                return {'error': 'RGB allocation not found', 'valid': False}

            # Validate RGB proof if present
            proof_valid = True
            if vtxo.rgb_proof_data:
                rgb_manager = get_rgb_manager()
                proof_valid = rgb_manager.validate_rgb_proof(vtxo.rgb_proof_data, allocation.contract_id)

            # Check state consistency
            state_consistent = True
            if vtxo.rgb_state_commitment and allocation.state_commitment:
                state_consistent = vtxo.rgb_state_commitment == allocation.state_commitment

            return {
                'valid': proof_valid and state_consistent,
                'vtxo_id': vtxo_id,
                'contract_id': allocation.contract_id,
                'amount': allocation.amount,
                'rgb_asset_type': vtxo.rgb_asset_type,
                'proof_valid': proof_valid,
                'state_consistent': state_consistent,
                'allocation_id': allocation.allocation_id,
                'owner_pubkey': allocation.owner_pubkey
            }

        except Exception as e:
            logger.error(f"❌ Failed to validate RGB VTXO state: {e}")
            return {'error': str(e), 'valid': False}
        finally:
            session.close()

    def _perform_vtxo_split(self, vtxo: Vtxo, split_amounts: List[int]) -> Optional[Dict]:
        """
        Internal method to perform the actual VTXO split

        Args:
            vtxo: VTXO to split
            split_amounts: Amounts for each split

        Returns:
            Split result with new VTXO IDs
        """
        try:
            # Validate split amounts
            total_split = sum(split_amounts)
            if total_split > vtxo.amount_sats:
                logger.error(f"Split amounts ({total_split}) exceed VTXO amount ({vtxo.amount_sats})")
                return None

            # Create new VTXOs
            new_vtxo_ids = []
            for i, amount in enumerate(split_amounts):
                new_vtxo = Vtxo(
                    vtxo_id=f"{vtxo.vtxo_id}_split_{i}",
                    txid=vtxo.txid,
                    vout=vtxo.vout + i,  # Simulate new vout
                    amount_sats=amount,
                    script_pubkey=vtxo.script_pubkey,
                    asset_id=vtxo.asset_id,
                    user_pubkey=vtxo.user_pubkey,
                    status='available',
                    expires_at=vtxo.expires_at,
                    rgb_asset_type=vtxo.rgb_asset_type
                )
                session = get_session()
                session.add(new_vtxo)
                new_vtxo_ids.append(new_vtxo.vtxo_id)
                session.commit()

            # Create change VTXO if needed
            change_amount = vtxo.amount_sats - total_split
            if change_amount > 0:
                change_vtxo = Vtxo(
                    vtxo_id=f"{vtxo.vtxo_id}_change",
                    txid=vtxo.txid,
                    vout=vtxo.vout + len(split_amounts),
                    amount_sats=change_amount,
                    script_pubkey=vtxo.script_pubkey,
                    asset_id=vtxo.asset_id,
                    user_pubkey=vtxo.user_pubkey,
                    status='available',
                    expires_at=vtxo.expires_at,
                    rgb_asset_type=vtxo.rgb_asset_type
                )
                session = get_session()
                session.add(change_vtxo)
                session.commit()

            return {
                'new_vtxo_ids': new_vtxo_ids,
                'change_amount': change_amount,
                'total_split': total_split
            }

        except Exception as e:
            logger.error(f"❌ Failed to perform VTXO split: {e}")
            return None


class VtxoSettlementManager:
    """Manages L1 settlement operations for VTXOs"""

    def __init__(self):
        self.settlement_interval = 3600  # 1 hour
        self.running = False

    def start_settlement_service(self):
        """Start the settlement service"""
        self.running = True
        settlement_thread = threading.Thread(target=self._settlement_loop, daemon=True)
        settlement_thread.start()
        logger.info("⚖️  VTXO settlement service started")

    def stop_settlement_service(self):
        """Stop the settlement service"""
        self.running = False
        logger.info("⏹️  VTXO settlement service stopped")

    def _settlement_loop(self):
        """Main settlement loop"""
        while self.running:
            try:
                self.process_hourly_settlement()
                time.sleep(self.settlement_interval)
            except Exception as e:
                logger.error(f"❌ Settlement loop error: {e}")
                time.sleep(60)

    def process_hourly_settlement(self):
        """Process hourly L1 settlement"""
        logger.info("⚖️  Starting hourly VTXO settlement")

        session = get_session()
        try:
            # Get all spent VTXOs that need settlement
            spent_vtxos = session.query(Vtxo).filter(
                and_(
                    Vtxo.status == 'spent',
                    Vtxo.spending_txid.isnot(None)
                )
            ).all()

            if not spent_vtxos:
                logger.info("ℹ️  No VTXOs to settle")
                return

            # Group by asset for batch settlement
            asset_groups = {}
            for vtxo in spent_vtxos:
                if vtxo.asset_id not in asset_groups:
                    asset_groups[vtxo.asset_id] = []
                asset_groups[vtxo.asset_id].append(vtxo)

            # Process settlement for each asset group
            for asset_id, vtxos in asset_groups.items():
                self.process_asset_settlement(session, asset_id, vtxos)

        except Exception as e:
            logger.error(f"❌ Settlement processing error: {e}")
        finally:
            session.close()

    def process_asset_settlement(self, session, asset_id: str, vtxos: List[Vtxo]):
        """Process settlement for a group of VTXOs"""
        try:
            logger.info(f"⚖️  Processing settlement for asset {asset_id} with {len(vtxos)} VTXOs")

            # Create Merkle tree for the VTXOs
            merkle_root = self.create_merkle_tree(vtxos)

            # Create commitment transaction
            commitment_tx = self.create_commitment_transaction(session, asset_id, vtxos, merkle_root)

            if not commitment_tx:
                logger.error(f"Failed to create commitment transaction for asset {asset_id}")
                return

            # Broadcast the settlement transaction
            broadcast_success = self.broadcast_settlement_transaction(commitment_tx)

            if broadcast_success:
                logger.info(f"✅ Settlement broadcast for asset {asset_id}: {commitment_tx['txid']}")

                # Update transaction status
                self.update_settlement_status(session, vtxos, commitment_tx['txid'])
            else:
                logger.error(f"❌ Failed to broadcast settlement for asset {asset_id}")

        except Exception as e:
            logger.error(f"❌ Asset settlement error: {e}")

    def create_merkle_tree(self, vtxos: List[Vtxo]) -> str:
        """Create a Merkle tree from VTXOs"""
        # Simple Merkle tree implementation
        # In practice, use a proper cryptographic Merkle tree

        if len(vtxos) == 1:
            return vtxos[0].vtxo_id

        # Hash VTXO IDs and build tree
        import hashlib
        hashes = [hashlib.sha256(v.vtxo_id.encode()).hexdigest() for v in vtxos]

        while len(hashes) > 1:
            new_hashes = []
            for i in range(0, len(hashes), 2):
                if i + 1 < len(hashes):
                    combined = hashes[i] + hashes[i + 1]
                    new_hash = hashlib.sha256(combined.encode()).hexdigest()
                else:
                    new_hash = hashes[i]  # Odd number, duplicate last
                new_hashes.append(new_hash)
            hashes = new_hashes

        return hashes[0]

    def create_commitment_transaction(self, session, asset_id: str, vtxos: List[Vtxo], merkle_root: str) -> Optional[Dict]:
        """Create a commitment transaction for settlement"""
        try:
            grpc_manager = get_grpc_manager()
            arkd_client = grpc_manager.get_client(ServiceType.ARKD)

            if not arkd_client:
                logger.error("ARKD client not available for commitment transaction")
                return None

            # Calculate total amount and fees
            total_amount = sum(v.amount_sats for v in vtxos)
            fee_estimate = self.estimate_settlement_fees(len(vtxos))

            # Create commitment transaction
            commitment_data = arkd_client.create_commitment_transaction(
                asset_id=asset_id,
                vtxo_ids=[v.vtxo_id for v in vtxos],
                merkle_root=merkle_root,
                total_amount=total_amount,
                fee_sats=fee_estimate
            )

            if not commitment_data:
                logger.error("Failed to create commitment transaction")
                return None

            # Store transaction in database
            transaction = Transaction(
                txid=commitment_data['txid'],
                tx_type='settlement_tx',
                raw_tx=commitment_data['raw_tx'],
                status='pending',
                amount_sats=total_amount,
                fee_sats=fee_estimate
            )
            session.add(transaction)
            session.commit()

            return commitment_data

        except Exception as e:
            logger.error(f"❌ Failed to create commitment transaction: {e}")
            return None

    def estimate_settlement_fees(self, vtxo_count: int) -> int:
        """Estimate fees for settlement transaction"""
        base_fee = 2000  # Base settlement fee
        per_vtxo_fee = 100  # Additional fee per VTXO

        return base_fee + (vtxo_count * per_vtxo_fee)

    def broadcast_settlement_transaction(self, commitment_tx: Dict) -> bool:
        """Broadcast settlement transaction to the network"""
        try:
            grpc_manager = get_grpc_manager()
            arkd_client = grpc_manager.get_client(ServiceType.ARKD)

            if not arkd_client:
                logger.error("ARKD client not available for broadcasting")
                return False

            # Broadcast the transaction
            success = arkd_client.broadcast_transaction(commitment_tx['raw_tx'])

            if success:
                logger.info(f"✅ Settlement transaction broadcast: {commitment_tx['txid']}")
                return True
            else:
                logger.error("Failed to broadcast settlement transaction")
                return False

        except Exception as e:
            logger.error(f"❌ Failed to broadcast settlement transaction: {e}")
            return False

    def update_settlement_status(self, session, vtxos: List[Vtxo], settlement_txid: str):
        """Update VTXO status after settlement"""
        try:
            # Update VTXO status to settled
            for vtxo in vtxos:
                vtxo.status = 'settled'

            session.commit()
            logger.info(f"✅ Updated {len(vtxos)} VTXOs to settled status")

        except Exception as e:
            logger.error(f"❌ Failed to update settlement status: {e}")
            session.rollback()

    def monitor_settlement_confirmation(self, settlement_txid: str):
        """Monitor settlement transaction confirmation"""
        # This would monitor the blockchain for confirmation
        # and update transaction status accordingly
        pass


# Global instances
_vtxo_manager = None
_settlement_manager = None

def get_vtxo_manager() -> VtxoManager:
    """Get the global VTXO manager instance"""
    global _vtxo_manager
    if _vtxo_manager is None:
        _vtxo_manager = VtxoManager()
    return _vtxo_manager

def get_settlement_manager() -> VtxoSettlementManager:
    """Get the global settlement manager instance"""
    global _settlement_manager
    if _settlement_manager is None:
        _settlement_manager = VtxoSettlementManager()
    return _settlement_manager

def initialize_vtxo_services():
    """Initialize all VTXO services"""
    try:
        vtxo_manager = get_vtxo_manager()
        settlement_manager = get_settlement_manager()

        vtxo_manager.start_services()
        settlement_manager.start_settlement_service()

        logger.info("✅ VTXO services initialized successfully")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to initialize VTXO services: {e}")
        return False

def shutdown_vtxo_services():
    """Shutdown all VTXO services"""
    try:
        vtxo_manager = get_vtxo_manager()
        settlement_manager = get_settlement_manager()

        if vtxo_manager:
            vtxo_manager.stop_services()

        if settlement_manager:
            settlement_manager.stop_settlement_service()

        logger.info("✅ VTXO services shutdown successfully")

    except Exception as e:
        logger.error(f"❌ Failed to shutdown VTXO services: {e}")