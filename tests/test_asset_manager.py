import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from models import Asset, AssetBalance, Vtxo, get_session
from asset_manager import AssetManager, AssetError, InsufficientAssetError
from sqlalchemy import func

class TestAssetManager:
    """Test cases for AssetManager"""

    @pytest.fixture
    def asset_manager(self):
        """Create an asset manager instance"""
        return AssetManager()

    @pytest.fixture
    def sample_asset(self):
        """Create a sample asset"""
        db_session = get_session()
        try:
            asset = Asset(
                asset_id="BTC",
                name="Bitcoin",
                ticker="BTC",
                asset_type="normal",
                decimal_places=8,
                total_supply=2100000000000000,
                is_active=True
            )
            db_session.add(asset)
            db_session.commit()
            db_session.refresh(asset)
            return asset
        finally:
            db_session.close()

    @pytest.fixture
    def sample_balance(self, sample_asset):
        """Create a sample asset balance"""
        db_session = get_session()
        try:
            balance = AssetBalance(
                user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                asset_id="BTC",
                balance=5000,
                reserved_balance=1000
            )
            db_session.add(balance)
            db_session.commit()
            db_session.refresh(balance)
            return balance
        finally:
            db_session.close()

    @pytest.fixture
    def sample_vtxo(self, sample_asset):
        """Create a sample VTXO"""
        db_session = get_session()
        try:
            vtxo = Vtxo(
                vtxo_id="test_vtxo_id",
                txid="test_txid",
                vout=0,
                amount_sats=1000,
                script_pubkey=b"test_script_pubkey",
                asset_id="BTC",
                user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                status="available",
                expires_at=datetime.utcnow() + timedelta(hours=24)
            )
            db_session.add(vtxo)
            db_session.commit()
            db_session.refresh(vtxo)
            return vtxo
        finally:
            db_session.close()

    def test_create_asset_success(self, asset_manager):
        """Test successful asset creation"""
        result = asset_manager.create_asset(
            asset_id="TEST_UNIT",
            name="Test Asset Unit",
            ticker="TSTU",
            asset_type="normal",
            decimal_places=8,
            total_supply=1000000,
            metadata={"description": "Test asset for unit testing"}
        )

        assert result['asset_id'] == "TEST_UNIT"
        assert result['name'] == "Test Asset Unit"
        assert result['ticker'] == "TSTU"
        assert result['asset_type'] == "normal"
        assert result['decimal_places'] == 8
        assert result['total_supply'] == 1000000
        assert result['is_active'] is True
        assert result['asset_metadata'] == {"description": "Test asset for unit testing"}

        # Verify asset was created in database
        db_session = get_session()
        try:
            asset = db_session.query(Asset).filter_by(asset_id="TEST").first()
            assert asset is not None
            assert asset.name == "Test Asset"
        finally:
            db_session.close()

    def test_create_asset_already_exists(self, asset_manager, sample_asset):
        """Test creating asset that already exists"""
        with pytest.raises(AssetError, match="already exists"):
            asset_manager.create_asset(
                asset_id="BTC",  # Already exists
                name="Bitcoin",
                ticker="BTC"
            )

    def test_get_asset_info_success(self, asset_manager, sample_asset):
        """Test getting asset information"""
        info = asset_manager.get_asset_info("BTC")

        assert info['asset_id'] == "BTC"
        assert info['name'] == "Bitcoin"
        assert info['ticker'] == "BTC"
        assert info['asset_type'] == "normal"
        assert info['decimal_places'] == 8
        assert info['total_supply'] == 2100000000000000
        assert info['is_active'] is True

    def test_get_asset_info_not_found(self, asset_manager):
        """Test getting info for non-existent asset"""
        info = asset_manager.get_asset_info("NONEXISTENT")
        assert 'error' in info
        assert 'not found' in info['error']

    def test_list_assets_all(self, asset_manager, sample_asset):
        """Test listing all assets"""
        # Create another asset
        asset_manager.create_asset("ETH", "Ethereum", "ETH")

        assets = asset_manager.list_assets(active_only=False)

        assert len(assets) >= 2
        asset_ids = [asset['asset_id'] for asset in assets]
        assert "BTC" in asset_ids
        assert "ETH" in asset_ids

    def test_list_assets_active_only(self, asset_manager, sample_asset):
        """Test listing only active assets"""
        # Create inactive asset
        db_session = get_session()
        try:
            inactive_asset = Asset(
                asset_id="INACTIVE",
                name="Inactive Asset",
                ticker="INACTIVE",
                is_active=False
            )
            db_session.add(inactive_asset)
            db_session.commit()
        finally:
            db_session.close()

        assets = asset_manager.list_assets(active_only=True)

        asset_ids = [asset['asset_id'] for asset in assets]
        assert "BTC" in asset_ids
        assert "INACTIVE" not in asset_ids

    def test_get_user_balance_success(self, asset_manager, sample_asset, sample_balance):
        """Test getting user balance for specific asset"""
        balance = asset_manager.get_user_balance(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            "BTC"
        )

        assert balance['user_pubkey'] == "test_user_pubkey_1234567890abcdef1234567890abcdef12345678"
        assert balance['asset_id'] == "BTC"
        assert balance['balance'] == 5000
        assert balance['reserved_balance'] == 1000
        assert balance['available_balance'] == 4000

    def test_get_user_balance_not_found(self, asset_manager, sample_asset):
        """Test getting balance for user with no balance"""
        balance = asset_manager.get_user_balance(
            "nonexistent_user_pubkey",
            "BTC"
        )

        assert balance['balance'] == 0
        assert balance['reserved_balance'] == 0
        assert balance['available_balance'] == 0

    def test_get_user_balances(self, asset_manager, sample_asset, sample_balance):
        """Test getting all balances for a user"""
        # Create another asset and balance
        asset_manager.create_asset("ETH", "Ethereum", "ETH")
        asset_manager.mint_assets(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            "ETH",
            2000
        )

        balances = asset_manager.get_user_balances(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678"
        )

        assert len(balances) >= 2
        balance_dict = {b['asset_id']: b for b in balances}
        assert "BTC" in balance_dict
        assert "ETH" in balance_dict
        assert balance_dict["BTC"]['balance'] == 5000
        assert balance_dict["ETH"]['balance'] == 2000

    def test_mint_assets_success(self, asset_manager, sample_asset):
        """Test successful asset minting"""
        result = asset_manager.mint_assets(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            "BTC",
            1000,
            500  # Reserve amount
        )

        assert result['asset_id'] == "BTC"
        assert result['user_pubkey'] == "test_user_..."
        assert result['amount_minted'] == 1000
        assert result['reserve_amount'] == 500
        assert result['new_balance'] == 1000

        # Verify balance was updated
        balance = asset_manager.get_user_balance(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            "BTC"
        )
        assert balance['balance'] == 1000
        assert balance['reserved_balance'] == 500

    def test_mint_assets_existing_balance(self, asset_manager, sample_asset, sample_balance):
        """Test minting assets to existing balance"""
        result = asset_manager.mint_assets(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            "BTC",
            2000,
            500
        )

        assert result['amount_minted'] == 2000
        assert result['new_balance'] == 7000  # 5000 + 2000

        # Verify balance was updated
        balance = asset_manager.get_user_balance(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            "BTC"
        )
        assert balance['balance'] == 7000
        assert balance['reserved_balance'] == 1500  # 1000 + 500

    def test_mint_assets_asset_not_found(self, asset_manager):
        """Test minting assets for non-existent asset"""
        with pytest.raises(AssetError, match="not found or inactive"):
            asset_manager.mint_assets(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                "NONEXISTENT",
                1000
            )

    def test_mint_assets_exceeds_supply_limit(self, asset_manager, sample_asset):
        """Test minting assets that would exceed supply limit"""
        # Create asset with limited supply
        asset_manager.create_asset("LIMITED", "Limited Asset", "LIMITED", total_supply=1000)

        with pytest.raises(AssetError, match="would exceed total supply limit"):
            asset_manager.mint_assets(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                "LIMITED",
                1500  # More than total supply
            )

    def test_transfer_assets_success(self, asset_manager, sample_asset, sample_balance):
        """Test successful asset transfer"""
        # Create recipient balance
        asset_manager.mint_assets(
            "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
            "BTC",
            1000
        )

        result = asset_manager.transfer_assets(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
            "BTC",
            2000
        )

        assert result['asset_id'] == "BTC"
        assert result['sender'] == "test_user_..."
        assert result['recipient'] == "test_recip..."
        assert result['amount'] == 2000
        assert result['sender_balance'] == 3000  # 5000 - 2000
        assert result['recipient_balance'] == 3000  # 1000 + 2000

    def test_transfer_assets_insufficient_balance(self, asset_manager, sample_asset, sample_balance):
        """Test transferring with insufficient balance"""
        with pytest.raises(InsufficientAssetError, match="Insufficient balance"):
            asset_manager.transfer_assets(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
                "BTC",
                10000  # More than available balance
            )

    def test_transfer_assets_insufficient_available_balance(self, asset_manager, sample_asset, sample_balance):
        """Test transferring with insufficient available balance"""
        # All balance is reserved (5000 balance, 5000 reserved = 0 available)
        db_session = get_session()
        try:
            balance = db_session.query(AssetBalance).filter_by(
                user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                asset_id="BTC"
            ).first()
            balance.reserved_balance = 5000
            db_session.commit()
        finally:
            db_session.close()

        with pytest.raises(InsufficientAssetError, match="Insufficient available balance"):
            asset_manager.transfer_assets(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
                "BTC",
                1000
            )

    def test_transfer_assets_create_recipient_balance(self, asset_manager, sample_asset, sample_balance):
        """Test transferring creates recipient balance if doesn't exist"""
        result = asset_manager.transfer_assets(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            "new_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
            "BTC",
            1500
        )

        assert result['recipient_balance'] == 1500

        # Verify recipient balance was created
        balance = asset_manager.get_user_balance(
            "new_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
            "BTC"
        )
        assert balance['balance'] == 1500

    def test_manage_vtxos_list(self, asset_manager, sample_asset, sample_vtxo):
        """Test listing VTXOs for a user"""
        result = asset_manager.manage_vtxos(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            action="list"
        )

        assert 'vtxos' in result
        assert len(result['vtxos']) > 0
        assert result['total_available'] > 0
        assert result['user_pubkey'] == "test_user_..."

    def test_manage_vtxos_list_with_asset_filter(self, asset_manager, sample_asset, sample_vtxo):
        """Test listing VTXOs with asset filter"""
        result = asset_manager.manage_vtxos(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            asset_id="BTC",
            action="list"
        )

        assert len(result['vtxos']) > 0
        for vtxo in result['vtxos']:
            assert vtxo['asset_id'] == "BTC"

    def test_manage_vtxos_create(self, asset_manager, sample_asset):
        """Test creating a VTXO"""
        result = asset_manager.manage_vtxos(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            asset_id="BTC",
            action="create",
            amount_sats=2000
        )

        assert 'vtxo_id' in result
        assert result['amount_sats'] == 2000
        assert result['asset_id'] == "BTC"
        assert result['status'] == "available"

    def test_manage_vtxos_assign(self, asset_manager, sample_asset, sample_vtxo):
        """Test assigning a VTXO"""
        result = asset_manager.manage_vtxos(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            action="assign",
            vtxo_id="test_vtxo_id"
        )

        assert result['status'] == "assigned"
        assert result['vtxo_id'] == "test_vtxo_id"

        # Verify VTXO status was updated
        db_session = get_session()
        try:
            vtxo = db_session.query(Vtxo).filter_by(vtxo_id="test_vtxo_id").first()
            assert vtxo.status == "assigned"
        finally:
            db_session.close()

    def test_manage_vtxos_assign_not_found(self, asset_manager):
        """Test assigning non-existent VTXO"""
        with pytest.raises(AssetError, match="not found"):
            asset_manager.manage_vtxos(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                action="assign",
                vtxo_id="nonexistent_vtxo_id"
            )

    def test_manage_vtxos_assign_not_available(self, asset_manager, sample_asset, sample_vtxo):
        """Test assigning VTXO that's not available"""
        # Mark VTXO as spent
        db_session = get_session()
        try:
            vtxo = db_session.query(Vtxo).filter_by(vtxo_id="test_vtxo_id").first()
            vtxo.status = "spent"
            db_session.commit()
        finally:
            db_session.close()

        with pytest.raises(AssetError, match="is not available"):
            asset_manager.manage_vtxos(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                action="assign",
                vtxo_id="test_vtxo_id"
            )

    def test_manage_vtxos_spend(self, asset_manager, sample_asset, sample_vtxo):
        """Test spending a VTXO"""
        result = asset_manager.manage_vtxos(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            action="spend",
            vtxo_id="test_vtxo_id",
            spending_txid="test_spending_txid"
        )

        assert result['status'] == "spent"
        assert result['spending_txid'] == "test_spending_txid"

        # Verify VTXO status was updated
        db_session = get_session()
        try:
            vtxo = db_session.query(Vtxo).filter_by(vtxo_id="test_vtxo_id").first()
            assert vtxo.status == "spent"
            assert vtxo.spending_txid == "test_spending_txid"
        finally:
            db_session.close()

    def test_get_asset_stats(self, asset_manager, sample_asset, sample_balance):
        """Test getting asset statistics"""
        # Create additional assets and balances for more comprehensive stats
        asset_manager.create_asset("ETH", "Ethereum", "ETH")
        asset_manager.mint_assets("user2", "ETH", 3000)

        stats = asset_manager.get_asset_stats()

        assert 'assets' in stats
        assert 'balances' in stats
        assert 'vtxos' in stats
        assert 'top_assets' in stats

        assert stats['assets']['total'] >= 2
        assert stats['assets']['active'] >= 1
        assert stats['balances']['total_balances'] >= 1
        assert stats['balances']['total_balance_sum'] >= 5000

    def test_cleanup_expired_vtxos(self, asset_manager, sample_asset):
        """Test cleaning up expired VTXOs"""
        # Create expired VTXO
        db_session = get_session()
        try:
            expired_vtxo = Vtxo(
                vtxo_id="expired_vtxo_id",
                txid="expired_txid",
                vout=0,
                amount_sats=500,
                script_pubkey=b"expired_script",
                asset_id="BTC",
                user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                status="available",
                expires_at=datetime.utcnow() - timedelta(hours=1)  # Expired
            )
            db_session.add(expired_vtxo)
            db_session.commit()
        finally:
            db_session.close()

        result = asset_manager.cleanup_expired_vtxos()

        assert result['cleaned_vtxos'] > 0
        assert result['total_amount_sats'] > 0

        # Verify VTXO was marked as expired
        db_session = get_session()
        try:
            vtxo = db_session.query(Vtxo).filter_by(vtxo_id="expired_vtxo_id").first()
            assert vtxo.status == "expired"
        finally:
            db_session.close()

    def test_get_reserve_requirements(self, asset_manager, sample_asset, sample_balance):
        """Test getting reserve requirements"""
        reserve = asset_manager.get_reserve_requirements("BTC")

        assert reserve['asset_id'] == "BTC"
        assert reserve['total_circulation'] == 5000
        assert reserve['current_reserve'] == 1000
        assert reserve['required_reserve'] == 500  # 10% of 5000
        assert reserve['reserve_ratio'] == 0.1
        assert reserve['reserve_deficit'] == 0  # No deficit (1000 >= 500)
        assert reserve['reserve_health'] == "good"

    def test_get_reserve_requirements_deficit(self, asset_manager, sample_asset):
        """Test reserve requirements with deficit"""
        # Create balance with insufficient reserves
        asset_manager.mint_assets(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            "BTC",
            10000,
            100  # Only 100 reserved
        )

        reserve = asset_manager.get_reserve_requirements("BTC")

        assert reserve['required_reserve'] == 1000  # 10% of 10000
        assert reserve['current_reserve'] == 100
        assert reserve['reserve_deficit'] == 900
        assert reserve['reserve_health'] == "deficient"

    def test_get_reserve_requirements_asset_not_found(self, asset_manager):
        """Test reserve requirements for non-existent asset"""
        reserve = asset_manager.get_reserve_requirements("NONEXISTENT")
        assert 'error' in reserve

    def test_unknown_vtxo_action(self, asset_manager):
        """Test unknown VTXO action"""
        with pytest.raises(AssetError, match="Unknown VTXO action"):
            asset_manager.manage_vtxos(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                action="unknown_action"
            )

    def test_sign_with_gateway_key(self, asset_manager):
        """Test gateway key signing"""
        signature = asset_manager._sign_with_gateway_key("test_session_id")

        assert isinstance(signature, str)
        assert len(signature) > 0

    def test_generate_vtxo_id(self, asset_manager):
        """Test VTXO ID generation"""
        vtxo_id = asset_manager._generate_vtxo_id(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            1000
        )

        assert isinstance(vtxo_id, str)
        assert len(vtxo_id) == 64  # SHA256 hash length

    def test_generate_script_pubkey(self, asset_manager):
        """Test script pubkey generation"""
        script_pubkey = asset_manager._generate_script_pubkey("test_user_pubkey")

        assert isinstance(script_pubkey, bytes)
        assert len(script_pubkey) > 0