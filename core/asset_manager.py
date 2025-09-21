import uuid
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List, Tuple
from enum import Enum
import logging
from core.models import Asset, AssetBalance, Vtxo, get_session
from grpc_clients import get_grpc_manager, ServiceType
from sqlalchemy import and_, or_, func

logger = logging.getLogger(__name__)

class AssetType(Enum):
    NORMAL = 'normal'
    COLLECTIBLE = 'collectible'

class AssetStatus(Enum):
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    FROZEN = 'frozen'

class VtxoStatus(Enum):
    AVAILABLE = 'available'
    ASSIGNED = 'assigned'
    SPENT = 'spent'
    EXPIRED = 'expired'

class AssetError(Exception):
    """Raised when asset operations fail"""
    pass

class InsufficientAssetError(AssetError):
    """Raised when insufficient assets are available"""
    pass

class AssetManager:
    """Manages assets, balances, and VTXOs for the Ark Relay Gateway"""

    def __init__(self, reserve_ratio: float = 0.1, vtxo_expiry_hours: int = 24):
        """
        Initialize asset manager

        Args:
            reserve_ratio: Ratio of assets to keep in reserve (default 10%)
            vtxo_expiry_hours: VTXO expiry time in hours (default 24)
        """
        self.reserve_ratio = reserve_ratio
        self.vtxo_expiry_hours = vtxo_expiry_hours
        self.grpc_manager = get_grpc_manager()

    def create_asset(self, asset_id: str, name: str, ticker: str,
                    asset_type: str = 'normal', decimal_places: int = 8,
                    total_supply: int = 0, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create a new asset in the system

        Args:
            asset_id: Unique asset identifier
            name: Asset name
            ticker: Asset ticker symbol
            asset_type: Asset type (normal/collectible)
            decimal_places: Number of decimal places
            total_supply: Total supply (0 for unlimited)
            metadata: Additional metadata

        Returns:
            Asset creation result
        """
        session = get_session()
        try:
            # Check if asset already exists
            existing_asset = session.query(Asset).filter_by(asset_id=asset_id).first()
            if existing_asset:
                raise AssetError(f"Asset {asset_id} already exists")

            # Create new asset
            new_asset = Asset(
                asset_id=asset_id,
                name=name,
                ticker=ticker,
                asset_type=asset_type,
                decimal_places=decimal_places,
                total_supply=total_supply,
                is_active=True,
                asset_metadata=metadata or {}
            )

            session.add(new_asset)
            session.commit()
            session.refresh(new_asset)

            logger.info(f"Created new asset: {asset_id} ({ticker})")

            return {
                'asset_id': asset_id,
                'name': name,
                'ticker': ticker,
                'asset_type': asset_type,
                'decimal_places': decimal_places,
                'total_supply': total_supply,
                'is_active': True,
                'asset_metadata': metadata or {},
                'created_at': new_asset.created_at.isoformat()
            }

        except Exception as e:
            session.rollback()
            logger.error(f"Error creating asset: {e}")
            raise
        finally:
            session.close()

    def get_asset_info(self, asset_id: str) -> Dict[str, Any]:
        """
        Get information about an asset

        Args:
            asset_id: Asset ID

        Returns:
            Asset information
        """
        session = get_session()
        try:
            asset = session.query(Asset).filter_by(asset_id=asset_id).first()
            if not asset:
                return {'error': 'Asset not found'}

            # Get circulation info
            total_balance = session.query(func.sum(AssetBalance.balance)).filter_by(asset_id=asset_id).scalar() or 0
            total_reserved = session.query(func.sum(AssetBalance.reserved_balance)).filter_by(asset_id=asset_id).scalar() or 0

            return {
                'asset_id': asset.asset_id,
                'name': asset.name,
                'ticker': asset.ticker,
                'asset_type': asset.asset_type,
                'decimal_places': asset.decimal_places,
                'total_supply': asset.total_supply,
                'is_active': asset.is_active,
                'total_circulating': total_balance,
                'total_reserved': total_reserved,
                'available_supply': asset.total_supply - total_balance if asset.total_supply > 0 else None,
                'created_at': asset.created_at.isoformat(),
                'metadata': asset.asset_metadata
            }

        except Exception as e:
            logger.error(f"Error getting asset info: {e}")
            return {'error': str(e)}
        finally:
            session.close()

    def list_assets(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        List all assets in the system

        Args:
            active_only: Only return active assets

        Returns:
            List of asset information
        """
        session = get_session()
        try:
            query = session.query(Asset)
            if active_only:
                query = query.filter_by(is_active=True)

            assets = query.order_by(Asset.created_at.desc()).all()

            result = []
            for asset in assets:
                # Get circulation info
                total_balance = session.query(func.sum(AssetBalance.balance)).filter_by(asset_id=asset.asset_id).scalar() or 0

                result.append({
                    'asset_id': asset.asset_id,
                    'name': asset.name,
                    'ticker': asset.ticker,
                    'asset_type': asset.asset_type,
                    'decimal_places': asset.decimal_places,
                    'total_supply': asset.total_supply,
                    'is_active': asset.is_active,
                    'total_circulating': total_balance,
                    'created_at': asset.created_at.isoformat()
                })

            return result

        except Exception as e:
            logger.error(f"Error listing assets: {e}")
            return []
        finally:
            session.close()

    def get_user_balance(self, user_pubkey: str, asset_id: str) -> Dict[str, Any]:
        """
        Get user's balance for a specific asset

        Args:
            user_pubkey: User's public key
            asset_id: Asset ID

        Returns:
            Balance information
        """
        session = get_session()
        try:
            balance = session.query(AssetBalance).filter_by(
                user_pubkey=user_pubkey,
                asset_id=asset_id
            ).first()

            if not balance:
                return {
                    'user_pubkey': user_pubkey,
                    'asset_id': asset_id,
                    'balance': 0,
                    'reserved_balance': 0,
                    'available_balance': 0
                }

            available_balance = balance.balance - balance.reserved_balance

            return {
                'user_pubkey': user_pubkey,
                'asset_id': asset_id,
                'balance': balance.balance,
                'reserved_balance': balance.reserved_balance,
                'available_balance': max(0, available_balance),
                'last_updated': balance.last_updated.isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting user balance: {e}")
            return {'error': str(e)}
        finally:
            session.close()

    def get_user_balances(self, user_pubkey: str) -> List[Dict[str, Any]]:
        """
        Get all balances for a user

        Args:
            user_pubkey: User's public key

        Returns:
            List of balance information
        """
        session = get_session()
        try:
            balances = session.query(AssetBalance).filter_by(user_pubkey=user_pubkey).all()

            result = []
            for balance in balances:
                available_balance = balance.balance - balance.reserved_balance

                result.append({
                    'asset_id': balance.asset_id,
                    'balance': balance.balance,
                    'reserved_balance': balance.reserved_balance,
                    'available_balance': max(0, available_balance),
                    'last_updated': balance.last_updated.isoformat()
                })

            return result

        except Exception as e:
            logger.error(f"Error getting user balances: {e}")
            return []
        finally:
            session.close()

    def mint_assets(self, user_pubkey: str, asset_id: str, amount: int,
                   reserve_amount: int = 0) -> Dict[str, Any]:
        """
        Mint new assets to a user's balance

        Args:
            user_pubkey: User's public key
            asset_id: Asset ID
            amount: Amount to mint
            reserve_amount: Amount to reserve (optional)

        Returns:
            Minting result
        """
        session = get_session()
        try:
            # Validate asset exists and is active
            asset = session.query(Asset).filter_by(asset_id=asset_id, is_active=True).first()
            if not asset:
                raise AssetError(f"Asset {asset_id} not found or inactive")

            # Check supply limit
            if asset.total_supply > 0:
                current_supply = session.query(func.sum(AssetBalance.balance)).filter_by(asset_id=asset_id).scalar() or 0
                if current_supply + amount > asset.total_supply:
                    raise AssetError(f"Minting would exceed total supply limit")

            # Update or create balance
            balance = session.query(AssetBalance).filter_by(
                user_pubkey=user_pubkey,
                asset_id=asset_id
            ).first()

            if balance:
                balance.balance += amount
                balance.reserved_balance += reserve_amount
            else:
                balance = AssetBalance(
                    user_pubkey=user_pubkey,
                    asset_id=asset_id,
                    balance=amount,
                    reserved_balance=reserve_amount
                )
                session.add(balance)

            session.commit()

            logger.info(f"Minted {amount} {asset_id} to {user_pubkey[:8]}...")

            return {
                'asset_id': asset_id,
                'user_pubkey': user_pubkey[:8] + '...',
                'amount_minted': amount,
                'reserve_amount': reserve_amount,
                'new_balance': balance.balance,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            session.rollback()
            logger.error(f"Error minting assets: {e}")
            raise
        finally:
            session.close()

    def transfer_assets(self, sender_pubkey: str, recipient_pubkey: str,
                       asset_id: str, amount: int) -> Dict[str, Any]:
        """
        Transfer assets between users

        Args:
            sender_pubkey: Sender's public key
            recipient_pubkey: Recipient's public key
            asset_id: Asset ID
            amount: Amount to transfer

        Returns:
            Transfer result
        """
        session = get_session()
        try:
            # Validate asset exists
            asset = session.query(Asset).filter_by(asset_id=asset_id, is_active=True).first()
            if not asset:
                raise AssetError(f"Asset {asset_id} not found or inactive")

            # Get sender balance
            sender_balance = session.query(AssetBalance).filter_by(
                user_pubkey=sender_pubkey,
                asset_id=asset_id
            ).first()

            if not sender_balance or sender_balance.balance < amount:
                raise InsufficientAssetError(f"Insufficient balance. Required: {amount}, Available: {sender_balance.balance if sender_balance else 0}")

            available_balance = sender_balance.balance - sender_balance.reserved_balance
            if available_balance < amount:
                raise InsufficientAssetError(f"Insufficient available balance. Required: {amount}, Available: {available_balance}")

            # Update sender balance
            sender_balance.balance -= amount

            # Update recipient balance
            recipient_balance = session.query(AssetBalance).filter_by(
                user_pubkey=recipient_pubkey,
                asset_id=asset_id
            ).first()

            if recipient_balance:
                recipient_balance.balance += amount
            else:
                recipient_balance = AssetBalance(
                    user_pubkey=recipient_pubkey,
                    asset_id=asset_id,
                    balance=amount
                )
                session.add(recipient_balance)

            session.commit()

            logger.info(f"Transferred {amount} {asset_id} from {sender_pubkey[:8]} to {recipient_pubkey[:8]}")

            return {
                'asset_id': asset_id,
                'sender': sender_pubkey[:8] + '...',
                'recipient': recipient_pubkey[:8] + '...',
                'amount': amount,
                'sender_balance': sender_balance.balance,
                'recipient_balance': recipient_balance.balance,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            session.rollback()
            logger.error(f"Error transferring assets: {e}")
            raise
        finally:
            session.close()

    def manage_vtxos(self, user_pubkey: str, asset_id: str = None,
                    action: str = 'list', **kwargs) -> Dict[str, Any]:
        """
        Manage VTXOs for users

        Args:
            user_pubkey: User's public key
            asset_id: Asset ID (optional)
            action: Action to perform (list, create, assign, spend)
            **kwargs: Additional parameters based on action

        Returns:
            VTXO management result
        """
        session = get_session()
        try:
            if action == 'list':
                return self._list_vtxos(session, user_pubkey, asset_id)
            elif action == 'create':
                return self._create_vtxo(session, user_pubkey, asset_id, **kwargs)
            elif action == 'assign':
                return self._assign_vtxo(session, user_pubkey, **kwargs)
            elif action == 'spend':
                return self._spend_vtxo(session, user_pubkey, **kwargs)
            else:
                raise AssetError(f"Unknown VTXO action: {action}")

        except Exception as e:
            session.rollback()
            logger.error(f"Error managing VTXOs: {e}")
            raise
        finally:
            session.close()

    def _list_vtxos(self, session, user_pubkey: str, asset_id: str = None) -> Dict[str, Any]:
        """List VTXOs for a user"""
        query = session.query(Vtxo).filter_by(user_pubkey=user_pubkey)
        if asset_id:
            query = query.filter_by(asset_id=asset_id)

        # Filter out expired and spent VTXOs
        now = datetime.utcnow()
        query = query.filter(
            Vtxo.expires_at > now,
            Vtxo.status != VtxoStatus.SPENT.value
        )

        vtxos = query.order_by(Vtxo.created_at.desc()).all()

        result = {
            'user_pubkey': user_pubkey[:8] + '...',
            'vtxos': [],
            'total_available': 0,
            'total_assigned': 0
        }

        for vtxo in vtxos:
            vtxo_info = {
                'vtxo_id': vtxo.vtxo_id,
                'txid': vtxo.txid,
                'vout': vtxo.vout,
                'amount_sats': vtxo.amount_sats,
                'asset_id': vtxo.asset_id,
                'status': vtxo.status,
                'expires_at': vtxo.expires_at.isoformat()
            }
            result['vtxos'].append(vtxo_info)

            if vtxo.status == VtxoStatus.AVAILABLE.value:
                result['total_available'] += vtxo.amount_sats
            elif vtxo.status == VtxoStatus.ASSIGNED.value:
                result['total_assigned'] += vtxo.amount_sats

        return result

    def _create_vtxo(self, session, user_pubkey: str, asset_id: str,
                    amount_sats: int, txid: str = None, vout: int = None) -> Dict[str, Any]:
        """Create a new VTXO"""
        # Generate VTXO ID
        vtxo_id = self._generate_vtxo_id(user_pubkey, amount_sats)

        # Calculate expiry
        expires_at = datetime.utcnow() + timedelta(hours=self.vtxo_expiry_hours)

        # Create VTXO
        vtxo = Vtxo(
            vtxo_id=vtxo_id,
            txid=txid or f"pending_{uuid.uuid4().hex}",
            vout=vout or 0,
            amount_sats=amount_sats,
            script_pubkey=self._generate_script_pubkey(user_pubkey),
            asset_id=asset_id,
            user_pubkey=user_pubkey,
            status=VtxoStatus.AVAILABLE.value,
            expires_at=expires_at
        )

        session.add(vtxo)
        session.commit()
        session.refresh(vtxo)

        logger.info(f"Created VTXO {vtxo_id} for {user_pubkey[:8]}...")

        return {
            'vtxo_id': vtxo_id,
            'txid': vtxo.txid,
            'vout': vtxo.vout,
            'amount_sats': amount_sats,
            'asset_id': asset_id,
            'status': vtxo.status,
            'expires_at': expires_at.isoformat(),
            'created_at': vtxo.created_at.isoformat()
        }

    def _assign_vtxo(self, session, user_pubkey: str, vtxo_id: str,
                   session_id: str = None) -> Dict[str, Any]:
        """Assign a VTXO to a session"""
        vtxo = session.query(Vtxo).filter_by(vtxo_id=vtxo_id, user_pubkey=user_pubkey).first()
        if not vtxo:
            raise AssetError(f"VTXO {vtxo_id} not found")

        if vtxo.status != VtxoStatus.AVAILABLE.value:
            raise AssetError(f"VTXO {vtxo_id} is not available")

        # Check expiry
        if vtxo.expires_at < datetime.utcnow():
            vtxo.status = VtxoStatus.EXPIRED.value
            session.commit()
            raise AssetError(f"VTXO {vtxo_id} has expired")

        vtxo.status = VtxoStatus.ASSIGNED.value
        session.commit()

        logger.info(f"Assigned VTXO {vtxo_id} for session {session_id or 'unknown'}")

        return {
            'vtxo_id': vtxo_id,
            'status': 'assigned',
            'session_id': session_id,
            'timestamp': datetime.utcnow().isoformat()
        }

    def _spend_vtxo(self, session, user_pubkey: str, vtxo_id: str,
                   spending_txid: str) -> Dict[str, Any]:
        """Mark a VTXO as spent"""
        vtxo = session.query(Vtxo).filter_by(vtxo_id=vtxo_id, user_pubkey=user_pubkey).first()
        if not vtxo:
            raise AssetError(f"VTXO {vtxo_id} not found")

        if vtxo.status == VtxoStatus.SPENT.value:
            raise AssetError(f"VTXO {vtxo_id} is already spent")

        vtxo.status = VtxoStatus.SPENT.value
        vtxo.spending_txid = spending_txid
        session.commit()

        logger.info(f"Spent VTXO {vtxo_id} in transaction {spending_txid}")

        return {
            'vtxo_id': vtxo_id,
            'status': 'spent',
            'spending_txid': spending_txid,
            'timestamp': datetime.utcnow().isoformat()
        }

    def get_asset_stats(self) -> Dict[str, Any]:
        """Get overall asset statistics"""
        session = get_session()
        try:
            # Get asset counts
            total_assets = session.query(Asset).count()
            active_assets = session.query(Asset).filter_by(is_active=True).count()

            # Get balance statistics
            total_balances = session.query(AssetBalance).count()
            total_balance_sum = session.query(func.sum(AssetBalance.balance)).scalar() or 0
            total_reserved_sum = session.query(func.sum(AssetBalance.reserved_balance)).scalar() or 0

            # Get VTXO statistics
            total_vtxos = session.query(Vtxo).count()
            available_vtxos = session.query(Vtxo).filter_by(status=VtxoStatus.AVAILABLE.value).count()
            assigned_vtxos = session.query(Vtxo).filter_by(status=VtxoStatus.ASSIGNED.value).count()
            spent_vtxos = session.query(Vtxo).filter_by(status=VtxoStatus.SPENT.value).count()

            # Get top assets by circulation
            top_assets = session.query(
                Asset.asset_id,
                Asset.name,
                Asset.ticker,
                func.sum(AssetBalance.balance).label('total_circulation')
            ).join(AssetBalance).filter(
                Asset.is_active == True
            ).group_by(Asset.asset_id, Asset.name, Asset.ticker).order_by(
                func.sum(AssetBalance.balance).desc()
            ).limit(10).all()

            return {
                'assets': {
                    'total': total_assets,
                    'active': active_assets,
                    'inactive': total_assets - active_assets
                },
                'balances': {
                    'total_balances': total_balances,
                    'total_balance_sum': total_balance_sum,
                    'total_reserved_sum': total_reserved_sum,
                    'total_available_sum': total_balance_sum - total_reserved_sum
                },
                'vtxos': {
                    'total': total_vtxos,
                    'available': available_vtxos,
                    'assigned': assigned_vtxos,
                    'spent': spent_vtxos,
                    'expired': total_vtxos - available_vtxos - assigned_vtxos - spent_vtxos
                },
                'top_assets': [
                    {
                        'asset_id': asset.asset_id,
                        'name': asset.name,
                        'ticker': asset.ticker,
                        'total_circulation': int(asset.total_circulation)
                    }
                    for asset in top_assets
                ],
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting asset stats: {e}")
            return {'error': str(e)}
        finally:
            session.close()

    def cleanup_expired_vtxos(self) -> Dict[str, Any]:
        """Clean up expired VTXOs"""
        session = get_session()
        try:
            now = datetime.utcnow()

            # Find expired VTXOs
            expired_vtxos = session.query(Vtxo).filter(
                Vtxo.expires_at < now,
                Vtxo.status != VtxoStatus.SPENT.value
            ).all()

            count = len(expired_vtxos)
            total_amount = 0

            for vtxo in expired_vtxos:
                vtxo.status = VtxoStatus.EXPIRED.value
                total_amount += vtxo.amount_sats

            session.commit()

            logger.info(f"Cleaned up {count} expired VTXOs with total amount {total_amount}")

            return {
                'cleaned_vtxos': count,
                'total_amount_sats': total_amount,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            session.rollback()
            logger.error(f"Error cleaning up expired VTXOs: {e}")
            return {'error': str(e)}
        finally:
            session.close()

    def _generate_vtxo_id(self, user_pubkey: str, amount_sats: int) -> str:
        """Generate a unique VTXO ID"""
        data = f"{user_pubkey}{amount_sats}{datetime.utcnow().isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()

    def _generate_script_pubkey(self, user_pubkey: str) -> bytes:
        """Generate script pubkey for a user"""
        # This is a simplified implementation
        # In reality, you'd generate a proper Bitcoin script pubkey
        return hashlib.sha256(user_pubkey.encode()).digest()

    def get_reserve_requirements(self, asset_id: str) -> Dict[str, Any]:
        """Calculate reserve requirements for an asset"""
        session = get_session()
        try:
            # Get total circulation
            total_circulation = session.query(func.sum(AssetBalance.balance)).filter_by(asset_id=asset_id).scalar() or 0
            total_reserved = session.query(func.sum(AssetBalance.reserved_balance)).filter_by(asset_id=asset_id).scalar() or 0

            # Calculate required reserves
            required_reserve = int(total_circulation * self.reserve_ratio)
            current_reserve = total_reserved
            reserve_deficit = max(0, required_reserve - current_reserve)

            return {
                'asset_id': asset_id,
                'total_circulation': total_circulation,
                'current_reserve': current_reserve,
                'required_reserve': required_reserve,
                'reserve_ratio': self.reserve_ratio,
                'reserve_deficit': reserve_deficit,
                'reserve_health': 'good' if reserve_deficit == 0 else 'deficient'
            }

        except Exception as e:
            logger.error(f"Error calculating reserve requirements: {e}")
            return {'error': str(e)}
        finally:
            session.close()

# Global asset manager instance
asset_manager = AssetManager()

def get_asset_manager() -> AssetManager:
    """Get the global asset manager instance"""
    return asset_manager