import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from core.models import Asset, AssetBalance, Vtxo, get_session
from core.asset_manager import AssetManager, AssetError, InsufficientAssetError
from sqlalchemy import func
from grpc_clients import ServiceType
from tests.test_database_setup import (
    test_db_session, test_engine, test_tables, create_test_asset, create_test_balance, create_test_vtxo,
    sample_asset_data, sample_balance_data, sample_vtxo_data
)

# Import the test database setup fixtures
from tests.test_database_setup import test_tables as setup_test_tables

# Import the patch_get_session fixture
from tests.test_database_setup import patch_get_session

class TestAssetManager:
    """Test cases for AssetManager"""

    @pytest.fixture
    def asset_manager(self):
        """Create an asset manager instance"""
        return AssetManager()

    @pytest.fixture
    def sample_asset(self):
        """Create a sample asset"""
        from core.models import get_session
        from tests.test_database_setup import sample_asset_data
        session = get_session()
        return create_test_asset(session, sample_asset_data('BTC'))

    @pytest.fixture
    def sample_balance(self, sample_asset):
        """Create a sample asset balance"""
        from core.models import get_session
        session = get_session()
        return create_test_balance(session)

    @pytest.fixture
    def sample_vtxo(self, sample_asset):
        """Create a sample VTXO"""
        from core.models import get_session
        session = get_session()
        return create_test_vtxo(session)

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
        from core.models import get_session
        session = get_session()
        asset = session.query(Asset).filter_by(asset_id="TEST_UNIT").first()
        assert asset is not None
        assert asset.name == "Test Asset Unit"

    def test_create_asset_already_exists(self, asset_manager, sample_asset):
        """Test creating asset that already exists"""
        with pytest.raises(AssetError, match="already exists"):
            asset_manager.create_asset(
                asset_id="BTC",  # Already exists
                name="Bitcoin",
                ticker="BTC"
            )

    def test_get_asset_info_success(self, asset_manager, sample_asset, test_db_session):
        """Test getting asset information"""
        info = asset_manager.get_asset_info("BTC")

        assert info['asset_id'] == "BTC"
        assert info['name'] == "Bitcoin"
        assert info['ticker'] == "BTC"
        assert info['asset_type'] == "normal"
        assert info['decimal_places'] == 8
        assert info['total_supply'] == 2100000000000000
        assert info['is_active'] is True

    def test_get_asset_info_not_found(self, asset_manager, test_db_session):
        """Test getting info for non-existent asset"""
        info = asset_manager.get_asset_info("NONEXISTENT")
        assert 'error' in info
        assert 'not found' in info['error']

    def test_list_assets_all(self, asset_manager, sample_asset, test_db_session):
        """Test listing all assets"""
        # Create another asset
        asset_manager.create_asset("ETH", "Ethereum", "ETH")

        assets = asset_manager.list_assets(active_only=False)

        assert len(assets) >= 2
        asset_ids = [asset['asset_id'] for asset in assets]
        assert "BTC" in asset_ids
        assert "ETH" in asset_ids

    def test_list_assets_active_only(self, asset_manager, sample_asset, test_db_session):
        """Test listing only active assets"""
        # Create inactive asset
        inactive_asset = Asset(
            asset_id="INACTIVE",
            name="Inactive Asset",
            ticker="INACTIVE",
            is_active=False
        )
        test_db_session.add(inactive_asset)
        test_db_session.commit()

        assets = asset_manager.list_assets(active_only=True)

        asset_ids = [asset['asset_id'] for asset in assets]
        assert "BTC" in asset_ids
        assert "INACTIVE" not in asset_ids

    def test_get_user_balance_success(self, asset_manager, sample_asset, sample_balance, test_db_session):
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

    def test_get_user_balance_not_found(self, asset_manager, sample_asset, test_db_session):
        """Test getting balance for user with no balance"""
        balance = asset_manager.get_user_balance(
            "nonexistent_user_pubkey",
            "BTC"
        )

        assert balance['balance'] == 0
        assert balance['reserved_balance'] == 0
        assert balance['available_balance'] == 0

    def test_get_user_balances(self, asset_manager, sample_asset, sample_balance, test_db_session):
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

    def test_mint_assets_success(self, asset_manager, sample_asset, test_db_session):
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

    def test_mint_assets_existing_balance(self, asset_manager, sample_asset, sample_balance, test_db_session):
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

    def test_mint_assets_asset_not_found(self, asset_manager, test_db_session):
        """Test minting assets for non-existent asset"""
        with pytest.raises(AssetError, match="not found or inactive"):
            asset_manager.mint_assets(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                "NONEXISTENT",
                1000
            )

    def test_mint_assets_exceeds_supply_limit(self, asset_manager, sample_asset, test_db_session):
        """Test minting assets that would exceed supply limit"""
        # Create asset with limited supply
        asset_manager.create_asset("LIMITED", "Limited Asset", "LIMITED", total_supply=1000)

        with pytest.raises(AssetError, match="would exceed total supply limit"):
            asset_manager.mint_assets(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                "LIMITED",
                1500  # More than total supply
            )

    def test_transfer_assets_success(self, asset_manager, sample_asset, sample_balance, test_db_session):
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

    def test_transfer_assets_insufficient_balance(self, asset_manager, sample_asset, sample_balance, test_db_session):
        """Test transferring with insufficient balance"""
        with pytest.raises(InsufficientAssetError, match="Insufficient balance"):
            asset_manager.transfer_assets(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
                "BTC",
                10000  # More than available balance
            )

    def test_transfer_assets_insufficient_available_balance(self, asset_manager, sample_asset, sample_balance, test_db_session):
        """Test transferring with insufficient available balance"""
        # All balance is reserved (5000 balance, 5000 reserved = 0 available)
        balance = test_db_session.query(AssetBalance).filter_by(
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            asset_id="BTC"
        ).first()
        balance.reserved_balance = 5000
        test_db_session.commit()

        with pytest.raises(InsufficientAssetError, match="Insufficient available balance"):
            asset_manager.transfer_assets(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
                "BTC",
                1000
            )

    def test_transfer_assets_create_recipient_balance(self, asset_manager, sample_asset, sample_balance, test_db_session):
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

    def test_manage_vtxos_list(self, asset_manager, sample_asset, sample_vtxo, test_db_session):
        """Test listing VTXOs for a user"""
        result = asset_manager.manage_vtxos(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            action="list"
        )

        assert 'vtxos' in result
        assert len(result['vtxos']) > 0
        assert result['total_available'] > 0
        assert result['user_pubkey'] == "test_user_..."

    def test_manage_vtxos_list_with_asset_filter(self, asset_manager, sample_asset, sample_vtxo, test_db_session):
        """Test listing VTXOs with asset filter"""
        result = asset_manager.manage_vtxos(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            asset_id="BTC",
            action="list"
        )

        assert len(result['vtxos']) > 0
        for vtxo in result['vtxos']:
            assert vtxo['asset_id'] == "BTC"

    def test_manage_vtxos_create(self, asset_manager, sample_asset, test_db_session):
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

    def test_manage_vtxos_assign(self, asset_manager, sample_asset, sample_vtxo, test_db_session):
        """Test assigning a VTXO"""
        result = asset_manager.manage_vtxos(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            action="assign",
            vtxo_id="test_vtxo_id"
        )

        assert result['status'] == "assigned"
        assert result['vtxo_id'] == "test_vtxo_id"

        # Verify VTXO status was updated
        vtxo = test_db_session.query(Vtxo).filter_by(vtxo_id="test_vtxo_id").first()
        assert vtxo.status == "assigned"

    def test_manage_vtxos_assign_not_found(self, asset_manager, test_db_session):
        """Test assigning non-existent VTXO"""
        with pytest.raises(AssetError, match="not found"):
            asset_manager.manage_vtxos(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                action="assign",
                vtxo_id="nonexistent_vtxo_id"
            )

    def test_manage_vtxos_assign_not_available(self, asset_manager, sample_asset, sample_vtxo, test_db_session):
        """Test assigning VTXO that's not available"""
        # Mark VTXO as spent
        vtxo = test_db_session.query(Vtxo).filter_by(vtxo_id="test_vtxo_id").first()
        vtxo.status = "spent"
        test_db_session.commit()

        with pytest.raises(AssetError, match="is not available"):
            asset_manager.manage_vtxos(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                action="assign",
                vtxo_id="test_vtxo_id"
            )

    def test_manage_vtxos_spend(self, asset_manager, sample_asset, sample_vtxo, test_db_session):
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
        vtxo = test_db_session.query(Vtxo).filter_by(vtxo_id="test_vtxo_id").first()
        assert vtxo.status == "spent"
        assert vtxo.spending_txid == "test_spending_txid"

    def test_get_asset_stats(self, asset_manager, sample_asset, sample_balance, test_db_session):
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

    def test_cleanup_expired_vtxos(self, asset_manager, sample_asset, test_db_session):
        """Test cleaning up expired VTXOs"""
        # Create expired VTXO
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
        test_db_session.add(expired_vtxo)
        test_db_session.commit()

        result = asset_manager.cleanup_expired_vtxos()

        assert result['cleaned_vtxos'] > 0
        assert result['total_amount_sats'] > 0

        # Verify VTXO was marked as expired
        vtxo = test_db_session.query(Vtxo).filter_by(vtxo_id="expired_vtxo_id").first()
        assert vtxo.status == "expired"

    def test_get_reserve_requirements(self, asset_manager, sample_asset, sample_balance, test_db_session):
        """Test getting reserve requirements"""
        reserve = asset_manager.get_reserve_requirements("BTC")

        assert reserve['asset_id'] == "BTC"
        assert reserve['total_circulation'] == 5000
        assert reserve['current_reserve'] == 1000
        assert reserve['required_reserve'] == 500  # 10% of 5000
        assert reserve['reserve_ratio'] == 0.1
        assert reserve['reserve_deficit'] == 0  # No deficit (1000 >= 500)
        assert reserve['reserve_health'] == "good"

    def test_get_reserve_requirements_deficit(self, asset_manager, sample_asset, test_db_session):
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

    def test_get_reserve_requirements_asset_not_found(self, asset_manager, test_db_session):
        """Test reserve requirements for non-existent asset"""
        reserve = asset_manager.get_reserve_requirements("NONEXISTENT")
        assert 'error' in reserve

    def test_unknown_vtxo_action(self, asset_manager, test_db_session):
        """Test unknown VTXO action"""
        with pytest.raises(AssetError, match="Unknown VTXO action"):
            asset_manager.manage_vtxos(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                action="unknown_action"
            )

    def test_initialization_with_custom_settings(self):
        """Test asset manager initialization with custom settings"""
        manager = AssetManager(reserve_ratio=0.2, vtxo_expiry_hours=48)
        assert manager.reserve_ratio == 0.2
        assert manager.vtxo_expiry_hours == 48

    def test_asset_manager_initialization_default(self):
        """Test asset manager initialization with default settings"""
        manager = AssetManager()
        assert manager.reserve_ratio == 0.1
        assert manager.vtxo_expiry_hours == 24
        assert manager.grpc_manager is not None

    def test_grpc_manager_integration(self):
        """Test gRPC manager integration"""
        manager = AssetManager()
        assert manager.grpc_manager is not None
        # Test that we can access gRPC clients
        arkd_client = manager.grpc_manager.get_client(ServiceType.ARKD)
        # Note: This may be None in test environment
        assert arkd_client is None or hasattr(arkd_client, 'health_check')

    def test_database_session_management(self, asset_manager, sample_asset, test_db_session):
        """Test proper database session management"""
        # Test that sessions are properly closed
        with patch('core.asset_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_get_session.return_value = mock_session

            asset_manager.get_asset_info("BTC")

            # Session should be closed
            mock_session.close.assert_called_once()

    def test_transaction_rollback_on_error(self, asset_manager, test_db_session):
        """Test transaction rollback on error"""
        # Mock session that raises exception during commit
        with patch('core.asset_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.query.return_value.filter_by.return_value.first.return_value = None
            mock_session.commit.side_effect = Exception("Database error")
            mock_get_session.return_value = mock_session

            with pytest.raises(Exception, match="Database error"):
                asset_manager.create_asset("TEST", "Test", "TEST")

            # Rollback should be called
            mock_session.rollback.assert_called_once()
            # Session should be closed
            mock_session.close.assert_called_once()

    def test_concurrent_operations(self, asset_manager, sample_asset, test_db_session):
        """Test concurrent asset operations"""
        import threading
        import time

        results = []
        errors = []

        def mint_assets():
            try:
                result = asset_manager.mint_assets(
                    f"user_{threading.current_thread().ident}",
                    "BTC",
                    100
                )
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=mint_assets)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All operations should succeed
        assert len(errors) == 0
        assert len(results) == 5

    def test_asset_validation(self, asset_manager, test_db_session):
        """Test asset input validation"""
        # Test invalid asset types
        with pytest.raises(Exception):
            asset_manager.create_asset("TEST", "Test", "TEST", asset_type="invalid_type")

        # Test invalid decimal places
        with pytest.raises(Exception):
            asset_manager.create_asset("TEST", "Test", "TEST", decimal_places=-1)

    def test_balance_validation(self, asset_manager, sample_asset, test_db_session):
        """Test balance validation"""
        # Test negative amounts
        with pytest.raises(Exception):
            asset_manager.mint_assets("test_user", "BTC", -100)

        # Test negative transfers
        with pytest.raises(Exception):
            asset_manager.transfer_assets("user1", "user2", "BTC", -100)

    def test_vtxo_expiry_handling(self, asset_manager, sample_asset, test_db_session):
        """Test VTXO expiry handling"""
        # Create VTXO that's about to expire
        almost_expired_vtxo = Vtxo(
            vtxo_id="almost_expired_vtxo_id",
            txid="almost_expired_txid",
            vout=0,
            amount_sats=1000,
            script_pubkey=b"test_script",
            asset_id="BTC",
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            status="available",
            expires_at=datetime.utcnow() + timedelta(seconds=1)  # Almost expired
        )
        test_db_session.add(almost_expired_vtxo)
        test_db_session.commit()

        # Wait for expiry
        import time
        time.sleep(2)

        # Try to assign expired VTXO
        with pytest.raises(AssetError, match="has expired"):
            asset_manager.manage_vtxos(
                "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                action="assign",
                vtxo_id="almost_expired_vtxo_id"
            )

    def test_asset_metadata_handling(self, asset_manager, test_db_session):
        """Test asset metadata handling"""
        metadata = {
            "description": "Test asset",
            "icon_url": "https://example.com/icon.png",
            "website": "https://example.com",
            "custom_fields": {"field1": "value1", "field2": "value2"}
        }

        result = asset_manager.create_asset(
            "METADATA",
            "Metadata Asset",
            "META",
            metadata=metadata
        )

        assert result['asset_metadata'] == metadata

        # Retrieve asset and verify metadata
        info = asset_manager.get_asset_info("METADATA")
        assert info['metadata'] == metadata

    def test_large_amount_handling(self, asset_manager, sample_asset, test_db_session):
        """Test handling of large amounts"""
        # Test with very large numbers
        large_amount = 10**18  # 1 billion BTC

        result = asset_manager.mint_assets(
            "whale_user",
            "BTC",
            large_amount
        )

        assert result['amount_minted'] == large_amount
        assert result['new_balance'] == large_amount

        # Verify balance can handle large amounts
        balance = asset_manager.get_user_balance("whale_user", "BTC")
        assert balance['balance'] == large_amount

    def test_edge_case_empty_strings(self, asset_manager, test_db_session):
        """Test edge cases with empty strings"""
        # Test empty asset ID
        with pytest.raises(Exception):
            asset_manager.create_asset("", "Empty", "EMPTY")

        # Test empty user pubkey
        with pytest.raises(Exception):
            asset_manager.get_user_balance("", "BTC")

    def test_edge_case_zero_amounts(self, asset_manager, sample_asset, test_db_session):
        """Test edge cases with zero amounts"""
        # Test minting zero amount
        result = asset_manager.mint_assets("test_user", "BTC", 0)
        assert result['amount_minted'] == 0
        assert result['new_balance'] == 0

        # Test transferring zero amount
        with pytest.raises(InsufficientAssetError):
            asset_manager.transfer_assets("user1", "user2", "BTC", 0)

    def test_vtxo_id_uniqueness(self, asset_manager, sample_asset, test_db_session):
        """Test VTXO ID uniqueness"""
        # Create multiple VTXOs with same parameters
        result1 = asset_manager.manage_vtxos(
            "test_user",
            asset_id="BTC",
            action="create",
            amount_sats=1000
        )

        result2 = asset_manager.manage_vtxos(
            "test_user",
            asset_id="BTC",
            action="create",
            amount_sats=1000
        )

        # VTXO IDs should be different due to timestamp
        assert result1['vtxo_id'] != result2['vtxo_id']

    def test_asset_stats_comprehensive(self, asset_manager, test_db_session):
        """Test comprehensive asset statistics"""
        # Create multiple assets and balances
        asset_manager.create_asset("STATS1", "Stats Asset 1", "S1")
        asset_manager.create_asset("STATS2", "Stats Asset 2", "S2")
        asset_manager.create_asset("STATS3", "Stats Asset 3", "S3")

        # Mint various amounts
        users = [f"user_{i}" for i in range(10)]
        for user in users:
            asset_manager.mint_assets(user, "STATS1", 1000)
            asset_manager.mint_assets(user, "STATS2", 2000)
            asset_manager.mint_assets(user, "STATS3", 3000)

        stats = asset_manager.get_asset_stats()

        assert stats['assets']['total'] >= 3
        assert stats['assets']['active'] >= 3
        assert stats['balances']['total_balances'] >= 30  # 10 users * 3 assets
        assert stats['balances']['total_balance_sum'] >= 60000  # 10 * (1000 + 2000 + 3000)
        assert len(stats['top_assets']) <= 10  # Should return top 10

    def test_cleanup_performance(self, asset_manager, sample_asset, test_db_session):
        """Test cleanup performance with many expired VTXOs"""
        import time

        # Create many expired VTXOs
        for i in range(100):
            expired_vtxo = Vtxo(
                vtxo_id=f"expired_vtxo_{i}",
                txid=f"expired_txid_{i}",
                vout=0,
                amount_sats=100,
                script_pubkey=f"script_{i}".encode(),
                asset_id="BTC",
                user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                status="available",
                expires_at=datetime.utcnow() - timedelta(hours=1)
            )
            test_db_session.add(expired_vtxo)
        test_db_session.commit()

        # Measure cleanup time
        start_time = time.time()
        result = asset_manager.cleanup_expired_vtxos()
        end_time = time.time()

        assert result['cleaned_vtxos'] == 100
        assert result['total_amount_sats'] == 10000
        # Should complete quickly (less than 5 seconds)
        assert end_time - start_time < 5.0

    @pytest.mark.slow
    def test_large_dataset_performance(self, asset_manager, test_db_session):
        """Test performance with large dataset"""
        import time

        # Create many assets and balances
        num_assets = 50
        num_users = 1000

        # Create assets
        for i in range(num_assets):
            asset_manager.create_asset(f"ASSET_{i}", f"Asset {i}", f"A{i}")

        # Mint balances for many users
        start_time = time.time()
        for i in range(num_users):
            for j in range(min(10, num_assets)):  # Each user gets 10 assets
                asset_manager.mint_assets(f"user_{i}", f"ASSET_{j}", 1000)

        mint_time = time.time() - start_time

        # Test list performance
        start_time = time.time()
        assets = asset_manager.list_assets()
        list_time = time.time() - start_time

        # Test stats performance
        start_time = time.time()
        stats = asset_manager.get_asset_stats()
        stats_time = time.time() - start_time

        assert len(assets) >= num_assets
        assert stats['assets']['total'] >= num_assets
        assert stats['balances']['total_balances'] >= num_users * 10

        # Performance assertions (should complete in reasonable time)
        assert mint_time < 30.0  # Should complete in less than 30 seconds
        assert list_time < 1.0    # Should complete in less than 1 second
        assert stats_time < 5.0   # Should complete in less than 5 seconds

    def test_generate_vtxo_id(self, asset_manager, test_db_session):
        """Test VTXO ID generation"""
        vtxo_id = asset_manager._generate_vtxo_id(
            "test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            1000
        )

        assert isinstance(vtxo_id, str)
        assert len(vtxo_id) == 64  # SHA256 hash length

    def test_generate_script_pubkey(self, asset_manager, test_db_session):
        """Test script pubkey generation"""
        script_pubkey = asset_manager._generate_script_pubkey("test_user_pubkey")

        assert isinstance(script_pubkey, bytes)
        assert len(script_pubkey) > 0