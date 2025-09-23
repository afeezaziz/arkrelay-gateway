import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.models import Transaction, SigningSession, AssetBalance, Asset, Base
from core.transaction_processor import TransactionProcessor, TransactionError, InsufficientFundsError, InvalidTransactionError
from core.session_manager import get_session_manager

# Test database setup
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DATABASE_URL)
TestSession = sessionmaker(bind=test_engine)

# Import test database setup to enable patching
from tests.test_database_setup import *

def setup_test_db():
    """Setup test database"""
    Base.metadata.create_all(test_engine)
    return TestSession()

def teardown_test_db():
    """Teardown test database"""
    Base.metadata.drop_all(test_engine)

class TestTransactionProcessor:
    """Test cases for TransactionProcessor"""

    @pytest.fixture
    def test_db(self):
        """Setup test database"""
        setup_test_db()
        yield
        teardown_test_db()

    @pytest.fixture
    def processor(self):
        """Create a transaction processor instance"""
        return TransactionProcessor()

    @pytest.fixture
    def test_session(self):
        """Create a test database session"""
        return TestSession()

    @pytest.fixture
    def sample_asset(self, test_session):
        """Create a sample asset"""
        asset = Asset(
            asset_id="BTC",
            name="Bitcoin",
            ticker="BTC",
            asset_type="normal",
            decimal_places=8,
            total_supply=2100000000000000,
            is_active=True
        )
        test_session.add(asset)
        test_session.commit()
        test_session.refresh(asset)
        return asset

    @pytest.fixture
    def sample_balance(self, test_session, sample_asset):
        """Create a sample asset balance"""
        balance = AssetBalance(
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            asset_id="BTC",
            balance=5000,
            reserved_balance=0
        )
        test_session.add(balance)
        test_session.commit()
        test_session.refresh(balance)
        return balance

    @pytest.fixture
    def sample_session(self, test_session):
        """Create a sample signing session"""
        session = SigningSession(
            session_id="test_session_id_1234567890abcdef1234567890abcdef12345678",
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            session_type="p2p_transfer",
            status="pending",
            intent_data={
                "recipient_pubkey": "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
                "amount": 1000,
                "asset_id": "BTC"
            },
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        test_session.add(session)
        test_session.commit()
        test_session.refresh(session)
        return session

    def test_process_p2p_transfer_success(self, processor, sample_session, sample_balance, test_session):
        """Test successful P2P transfer processing"""
        result = processor.process_p2p_transfer(sample_session.session_id)

        assert result['txid'] is not None
        assert result['amount'] == 1000
        assert result['asset_id'] == 'BTC'
        assert result['sender'] == 'test_user_...'
        assert result['recipient'] == 'test_rec...'
        assert result['status'] == 'pending_signatures'

        # Verify transaction was created
        tx = test_session.query(Transaction).filter_by(session_id=sample_session.session_id).first()
        assert tx is not None
        assert tx.tx_type == 'p2p_transfer'
        assert tx.amount_sats == 1000
        assert tx.status == 'pending'

    def test_process_p2p_transfer_insufficient_funds(self, processor, sample_session):
        """Test P2P transfer with insufficient funds"""
        # Create a balance with insufficient funds
        db_session = get_session()
        try:
            balance = AssetBalance(
                user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                asset_id="BTC",
                balance=500,  # Less than transfer amount
                reserved_balance=0
            )
            db_session.add(balance)
            db_session.commit()
        finally:
            db_session.close()

        with pytest.raises(InsufficientFundsError):
            processor.process_p2p_transfer(sample_session.session_id)

    def test_process_p2p_transfer_invalid_session(self, processor):
        """Test P2P transfer with invalid session"""
        with pytest.raises(TransactionError, match="Session not found"):
            processor.process_p2p_transfer("invalid_session_id")

    def test_process_p2p_transfer_invalid_session_type(self, processor):
        """Test P2P transfer with wrong session type"""
        session_manager = get_session_manager()
        session = session_manager.create_session(
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            session_type="lightning_lift",  # Wrong type
            intent_data={"amount": 1000, "asset_id": "BTC"}
        )

        with pytest.raises(TransactionError, match="is not a P2P transfer"):
            processor.process_p2p_transfer(session.session_id)

    def test_calculate_transaction_fee(self, processor):
        """Test transaction fee calculation"""
        # Mock ARKD client
        with patch.object(processor, 'grpc_manager') as mock_grpc:
            mock_arkd = Mock()
            mock_arkd.get_fee_rate.return_value = 10
            mock_grpc.get_client.return_value = mock_arkd

            fee = processor.calculate_transaction_fee("0100000000010100000000000000")

            assert fee >= processor.min_fee_sats
            mock_arkd.get_fee_rate.assert_called_once()

    def test_calculate_transaction_fee_no_grpc(self, processor):
        """Test transaction fee calculation without gRPC client"""
        with patch.object(processor, 'grpc_manager') as mock_grpc:
            mock_grpc.get_client.return_value = None

            fee = processor.calculate_transaction_fee("0100000000010100000000000000")

            assert fee == processor.min_fee_sats

    def test_validate_transaction_valid(self, processor):
        """Test transaction validation with valid transaction"""
        # Create a mock transaction
        raw_tx = "0100000000010100000000000000010000000000000000000000000000000000000000000000000000000000000000000000"
        recipient_pubkey = "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678"

        # Mock the parsing to return a valid output
        with patch.object(processor, '_parse_transaction_outputs') as mock_parse:
            mock_parse.return_value = [{'amount': 1000, 'script': 'valid_script'}]
            with patch.object(processor, '_verify_output_script', return_value=True):
                result = processor.validate_transaction(raw_tx, 1000, recipient_pubkey)
                assert result is True

    def test_validate_transaction_invalid(self, processor):
        """Test transaction validation with invalid transaction"""
        raw_tx = "invalid_tx"

        result = processor.validate_transaction(raw_tx, 1000, "test_pubkey")
        assert result is False

    @patch('transaction_processor.datetime')
    def test_get_transaction_status_broadcast(self, mock_datetime, processor):
        """Test getting transaction status for broadcast transaction"""
        # Setup mock time
        mock_now = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = mock_now

        # Create a transaction
        db_session = get_session()
        try:
            tx = Transaction(
                txid="test_txid",
                session_id="test_session",
                tx_type="p2p_transfer",
                status="broadcast",
                amount_sats=1000,
                fee_sats=100
            )
            db_session.add(tx)
            db_session.commit()
            db_session.refresh(tx)

            # Mock ARKD client
            with patch.object(processor, 'grpc_manager') as mock_grpc:
                mock_arkd = Mock()
                mock_arkd.get_transaction_status.return_value = {
                    'confirmations': 1,
                    'confirmed': True,
                    'block_height': 800000
                }
                mock_grpc.get_client.return_value = mock_arkd

                status = processor.get_transaction_status("test_txid")

                assert status['status'] == 'confirmed'
                assert status['confirmed_at'] is not None
                assert status['block_height'] == 800000

        finally:
            db_session.close()

    def test_get_transaction_status_not_found(self, processor):
        """Test getting transaction status for non-existent transaction"""
        status = processor.get_transaction_status("nonexistent_txid")
        assert 'error' in status
        assert 'not found' in status['error']

    def test_get_user_transactions(self, processor, sample_session, sample_balance):
        """Test getting user transactions"""
        # Process a transfer first
        processor.process_p2p_transfer(sample_session.session_id)

        user_pubkey = "test_user_pubkey_1234567890abcdef1234567890abcdef12345678"
        transactions = processor.get_user_transactions(user_pubkey)

        assert len(transactions) > 0
        assert all(tx['amount_sats'] > 0 for tx in transactions)
        assert all('created_at' in tx for tx in transactions)

    def test_get_user_transactions_limit(self, processor, sample_session, sample_balance):
        """Test getting user transactions with limit"""
        # Process a transfer first
        processor.process_p2p_transfer(sample_session.session_id)

        user_pubkey = "test_user_pubkey_1234567890abcdef1234567890abcdef12345678"
        transactions = processor.get_user_transactions(user_pubkey, limit=1)

        assert len(transactions) <= 1

    def test_broadcast_transaction_success(self, processor):
        """Test successful transaction broadcasting"""
        # Create a transaction
        db_session = get_session()
        try:
            tx = Transaction(
                txid="test_txid",
                session_id="test_session",
                tx_type="p2p_transfer",
                status="pending",
                amount_sats=1000,
                fee_sats=100,
                raw_tx="0100000000010100000000000000010000000000000000000000000000000000000000000000000000000000000000000000"
            )
            db_session.add(tx)
            db_session.commit()
            db_session.refresh(tx)

            # Mock ARKD client
            with patch.object(processor, 'grpc_manager') as mock_grpc:
                mock_arkd = Mock()
                mock_arkd.broadcast_transaction.return_value = {'success': True}
                mock_grpc.get_client.return_value = mock_arkd

                result = processor.broadcast_transaction("test_txid")

                assert result is True
                mock_arkd.broadcast_transaction.assert_called_once_with(tx.raw_tx)

                # Verify status was updated
                db_session.refresh(tx)
                assert tx.status == 'broadcast'

        finally:
            db_session.close()

    def test_broadcast_transaction_not_found(self, processor):
        """Test broadcasting non-existent transaction"""
        with pytest.raises(TransactionError, match="Transaction not found"):
            processor.broadcast_transaction("nonexistent_txid")

    def test_broadcast_transaction_no_raw_data(self, processor):
        """Test broadcasting transaction without raw data"""
        db_session = get_session()
        try:
            tx = Transaction(
                txid="test_txid",
                session_id="test_session",
                tx_type="p2p_transfer",
                status="pending",
                amount_sats=1000,
                fee_sats=100
                # No raw_tx
            )
            db_session.add(tx)
            db_session.commit()

            with pytest.raises(TransactionError, match="has no raw data"):
                processor.broadcast_transaction("test_txid")

        finally:
            db_session.close()

    def test_broadcast_transaction_no_grpc_client(self, processor):
        """Test broadcasting transaction without gRPC client"""
        # Create a transaction
        db_session = get_session()
        try:
            tx = Transaction(
                txid="test_txid",
                session_id="test_session",
                tx_type="p2p_transfer",
                status="pending",
                amount_sats=1000,
                fee_sats=100,
                raw_tx="0100000000010100000000000000010000000000000000000000000000000000000000000000000000000000000000000000"
            )
            db_session.add(tx)
            db_session.commit()

            # Mock gRPC manager to return None
            with patch.object(processor, 'grpc_manager') as mock_grpc:
                mock_grpc.get_client.return_value = None

                result = processor.broadcast_transaction("test_txid")

                assert result is False

        finally:
            db_session.close()

    def test_confirm_transaction_success(self, processor):
        """Test successful transaction confirmation"""
        # Create a transaction
        db_session = get_session()
        try:
            tx = Transaction(
                txid="test_txid",
                session_id="test_session",
                tx_type="p2p_transfer",
                status="broadcast",
                amount_sats=1000,
                fee_sats=100
            )
            db_session.add(tx)
            db_session.commit()
            db_session.refresh(tx)

            # Mock ARKD client
            with patch.object(processor, 'grpc_manager') as mock_grpc:
                mock_arkd = Mock()
                mock_arkd.get_transaction_status.return_value = {
                    'confirmations': 1,
                    'confirmed': True,
                    'block_height': 800000
                }
                mock_grpc.get_client.return_value = mock_arkd

                result = processor.confirm_transaction("test_txid")

                assert result is True

                # Verify status was updated
                db_session.refresh(tx)
                assert tx.status == 'confirmed'
                assert tx.confirmed_at is not None
                assert tx.block_height == 800000

        finally:
            db_session.close()

    def test_confirm_transaction_insufficient_confirmations(self, processor):
        """Test transaction confirmation with insufficient confirmations"""
        # Create a transaction
        db_session = get_session()
        try:
            tx = Transaction(
                txid="test_txid",
                session_id="test_session",
                tx_type="p2p_transfer",
                status="broadcast",
                amount_sats=1000,
                fee_sats=100
            )
            db_session.add(tx)
            db_session.commit()

            # Mock ARKD client
            with patch.object(processor, 'grpc_manager') as mock_grpc:
                mock_arkd = Mock()
                mock_arkd.get_transaction_status.return_value = {
                    'confirmations': 0,
                    'confirmed': False
                }
                mock_grpc.get_client.return_value = mock_arkd

                result = processor.confirm_transaction("test_txid", confirmations=1)

                assert result is False

                # Verify status wasn't updated
                db_session.refresh(tx)
                assert tx.status == 'broadcast'

        finally:
            db_session.close()

    def test_concurrent_transaction_processing(self, processor, sample_session, sample_balance):
        """Test concurrent transaction processing"""
        import threading
        results = []
        errors = []

        def process_transfer():
            try:
                result = processor.process_p2p_transfer(sample_session.session_id)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(3):
            thread = threading.Thread(target=process_transfer)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Only first transaction should succeed due to balance constraints
        assert len(results) <= 1
        assert len(errors) >= 2

    def test_transaction_validation_edge_cases(self, processor):
        """Test transaction validation edge cases"""
        # Test with empty transaction
        result = processor.validate_transaction("", 1000, "test_pubkey")
        assert result is False

        # Test with malformed hex
        result = processor.validate_transaction("invalid_hex", 1000, "test_pubkey")
        assert result is False

        # Test with zero amount
        raw_tx = "0100000000010100000000000000010000000000000000000000000000000000000000000000000000000000000000000000"
        with patch.object(processor, '_parse_transaction_outputs') as mock_parse:
            mock_parse.return_value = [{'amount': 0, 'script': 'valid_script'}]
            with patch.object(processor, '_verify_output_script', return_value=True):
                result = processor.validate_transaction(raw_tx, 0, "test_pubkey")
                assert result is True

    def test_fee_calculation_edge_cases(self, processor):
        """Test fee calculation edge cases"""
        # Test with empty transaction
        fee = processor.calculate_transaction_fee("")
        assert fee >= processor.min_fee_sats

        # Test with very large transaction
        large_tx = "01" * 10000
        fee = processor.calculate_transaction_fee(large_tx)
        assert fee > processor.min_fee_sats

        # Test with fee rate error
        with patch.object(processor, 'grpc_manager') as mock_grpc:
            mock_arkd = Mock()
            mock_arkd.get_fee_rate.side_effect = Exception("Fee rate error")
            mock_grpc.get_client.return_value = mock_arkd

            fee = processor.calculate_transaction_fee("0100000000010100000000000000")
            assert fee == processor.min_fee_sats

    def test_transaction_rollback_on_error(self, processor, sample_session, sample_balance):
        """Test transaction rollback on processing errors"""
        # Mock a failure during processing
        with patch.object(processor, '_create_transaction', side_effect=Exception("Processing failed")):
            initial_balance = sample_balance.balance

            with pytest.raises(Exception, match="Processing failed"):
                processor.process_p2p_transfer(sample_session.session_id)

            # Verify balance wasn't affected
            db_session = get_session()
            try:
                db_session.refresh(sample_balance)
                assert sample_balance.balance == initial_balance
            finally:
                db_session.close()

    def test_multiple_asset_transfers(self, processor):
        """Test transfers with different asset types"""
        session_manager = get_session_manager()

        # Create assets
        db_session = get_session()
        try:
            btc_asset = Asset(
                asset_id="BTC",
                name="Bitcoin",
                ticker="BTC",
                asset_type="normal",
                decimal_places=8,
                total_supply=2100000000000000,
                is_active=True
            )
            usdt_asset = Asset(
                asset_id="USDT",
                name="Tether",
                ticker="USDT",
                asset_type="normal",
                decimal_places=6,
                total_supply=100000000000000,
                is_active=True
            )
            db_session.add_all([btc_asset, usdt_asset])
            db_session.commit()
            db_session.refresh(btc_asset)
            db_session.refresh(usdt_asset)

            # Create balances
            btc_balance = AssetBalance(
                user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                asset_id="BTC",
                balance=5000,
                reserved_balance=0
            )
            usdt_balance = AssetBalance(
                user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                asset_id="USDT",
                balance=10000,
                reserved_balance=0
            )
            db_session.add_all([btc_balance, usdt_balance])
            db_session.commit()
        finally:
            db_session.close()

        # Test BTC transfer
        btc_session = session_manager.create_session(
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            session_type="p2p_transfer",
            intent_data={
                "recipient_pubkey": "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
                "amount": 1000,
                "asset_id": "BTC"
            }
        )

        result = processor.process_p2p_transfer(btc_session.session_id)
        assert result['asset_id'] == 'BTC'
        assert result['amount'] == 1000

        # Test USDT transfer
        usdt_session = session_manager.create_session(
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            session_type="p2p_transfer",
            intent_data={
                "recipient_pubkey": "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
                "amount": 500,
                "asset_id": "USDT"
            }
        )

        result = processor.process_p2p_transfer(usdt_session.session_id)
        assert result['asset_id'] == 'USDT'
        assert result['amount'] == 500

    def test_transaction_status_tracking(self, processor):
        """Test comprehensive transaction status tracking"""
        db_session = get_session()
        try:
            # Create transaction in each status
            pending_tx = Transaction(
                txid="pending_tx",
                session_id="session1",
                tx_type="p2p_transfer",
                status="pending",
                amount_sats=1000,
                fee_sats=100
            )
            broadcast_tx = Transaction(
                txid="broadcast_tx",
                session_id="session2",
                tx_type="p2p_transfer",
                status="broadcast",
                amount_sats=2000,
                fee_sats=200
            )
            confirmed_tx = Transaction(
                txid="confirmed_tx",
                session_id="session3",
                tx_type="p2p_transfer",
                status="confirmed",
                amount_sats=3000,
                fee_sats=300,
                confirmed_at=datetime.utcnow(),
                block_height=800000
            )
            failed_tx = Transaction(
                txid="failed_tx",
                session_id="session4",
                tx_type="p2p_transfer",
                status="failed",
                amount_sats=4000,
                fee_sats=400,
                error_message="Broadcast failed"
            )

            db_session.add_all([pending_tx, broadcast_tx, confirmed_tx, failed_tx])
            db_session.commit()

            # Test status retrieval for each
            pending_status = processor.get_transaction_status("pending_tx")
            assert pending_status['status'] == 'pending'

            broadcast_status = processor.get_transaction_status("broadcast_tx")
            assert broadcast_status['status'] == 'broadcast'

            confirmed_status = processor.get_transaction_status("confirmed_tx")
            assert confirmed_status['status'] == 'confirmed'
            assert confirmed_status['confirmed_at'] is not None

            failed_status = processor.get_transaction_status("failed_tx")
            assert failed_status['status'] == 'failed'
            assert failed_status['error_message'] == "Broadcast failed"

        finally:
            db_session.close()

    def test_broadcast_retry_logic(self, processor):
        """Test broadcast retry logic"""
        db_session = get_session()
        try:
            tx = Transaction(
                txid="retry_tx",
                session_id="session1",
                tx_type="p2p_transfer",
                status="pending",
                amount_sats=1000,
                fee_sats=100,
                raw_tx="0100000000010100000000000000010000000000000000000000000000000000000000000000000000000000000000000000"
            )
            db_session.add(tx)
            db_session.commit()

            # Mock gRPC client that fails first, then succeeds
            with patch.object(processor, 'grpc_manager') as mock_grpc:
                mock_arkd = Mock()
                mock_arkd.broadcast_transaction.side_effect = [
                    Exception("Network error"),
                    {'success': True}
                ]
                mock_grpc.get_client.return_value = mock_arkd

                # First attempt should fail
                result = processor.broadcast_transaction("retry_tx")
                assert result is False

                # Second attempt should succeed
                result = processor.broadcast_transaction("retry_tx")
                assert result is True

                # Verify status was updated
                db_session.refresh(tx)
                assert tx.status == 'broadcast'

        finally:
            db_session.close()

    def test_transaction_validation_comprehensive(self, processor):
        """Test comprehensive transaction validation"""
        # Test with various transaction formats
        test_cases = [
            ("0100000000010100000000000000010000000000000000000000000000000000000000000000000000000000000000000000", True),
            ("0100000001", False),  # Too short
            ("invalid_hex_string", False),  # Invalid hex
            ("", False),  # Empty
        ]

        for raw_tx, expected in test_cases:
            with patch.object(processor, '_parse_transaction_outputs') as mock_parse:
                mock_parse.return_value = [{'amount': 1000, 'script': 'valid_script'}]
                with patch.object(processor, '_verify_output_script', return_value=True):
                    result = processor.validate_transaction(raw_tx, 1000, "test_pubkey")
                    assert result == expected

    def test_user_transaction_filtering(self, processor, sample_session, sample_balance):
        """Test user transaction filtering and pagination"""
        # Create multiple transactions
        for i in range(5):
            session_manager = get_session_manager()
            session = session_manager.create_session(
                user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                session_type="p2p_transfer",
                intent_data={
                    "recipient_pubkey": f"test_recipient_pubkey_{i}",
                    "amount": 1000 + i,
                    "asset_id": "BTC"
                }
            )
            processor.process_p2p_transfer(session.session_id)

        user_pubkey = "test_user_pubkey_1234567890abcdef1234567890abcdef12345678"

        # Test pagination
        page1 = processor.get_user_transactions(user_pubkey, limit=2)
        assert len(page1) <= 2

        page2 = processor.get_user_transactions(user_pubkey, limit=2, offset=2)
        assert len(page2) <= 2

        # Test filtering by asset
        btc_txs = processor.get_user_transactions(user_pubkey, asset_id="BTC")
        assert all(tx['asset_id'] == 'BTC' for tx in btc_txs)

        # Test filtering by status
        pending_txs = processor.get_user_transactions(user_pubkey, status="pending")
        assert all(tx['status'] == 'pending' for tx in pending_txs)

    def test_error_handling_comprehensive(self, processor):
        """Test comprehensive error handling"""
        # Test with None inputs
        with pytest.raises(TransactionError):
            processor.process_p2p_transfer(None)

        with pytest.raises(TransactionError):
            processor.validate_transaction(None, 1000, "test_pubkey")

        with pytest.raises(TransactionError):
            processor.broadcast_transaction(None)

        with pytest.raises(TransactionError):
            processor.confirm_transaction(None)

        # Test with invalid session ID format
        with pytest.raises(TransactionError):
            processor.process_p2p_transfer("")

        with pytest.raises(TransactionError):
            processor.process_p2p_transfer("invalid_session_id_format")

        # Test with invalid transaction ID format
        with pytest.raises(TransactionError):
            processor.broadcast_transaction("")

        with pytest.raises(TransactionError):
            processor.confirm_transaction("")

    def test_performance_large_dataset(self, processor):
        """Test performance with large transaction datasets"""
        import time

        # Create many transactions
        db_session = get_session()
        try:
            transactions = []
            for i in range(100):
                tx = Transaction(
                    txid=f"tx_{i}",
                    session_id=f"session_{i}",
                    tx_type="p2p_transfer",
                    status="pending",
                    amount_sats=1000 + i,
                    fee_sats=100
                )
                transactions.append(tx)

            db_session.add_all(transactions)
            db_session.commit()

            # Test performance of user transaction retrieval
            start_time = time.time()
            user_txs = processor.get_user_transactions("test_user_pubkey_1234567890abcdef1234567890abcdef12345678")
            end_time = time.time()

            # Should complete within reasonable time
            assert end_time - start_time < 2.0

        finally:
            db_session.close()

    @pytest.mark.integration
    def test_integration_with_grpc_services(self, processor):
        """Test integration with gRPC services"""
        # Mock complete gRPC service interaction
        with patch.object(processor, 'grpc_manager') as mock_grpc:
            mock_arkd = Mock()
            mock_arkd.get_fee_rate.return_value = 10
            mock_arkd.broadcast_transaction.return_value = {'success': True}
            mock_arkd.get_transaction_status.return_value = {
                'confirmations': 1,
                'confirmed': True,
                'block_height': 800000
            }
            mock_grpc.get_client.return_value = mock_arkd

            # Test full flow
            fee = processor.calculate_transaction_fee("0100000000010100000000000000")
            assert fee > 0

            # Test transaction confirmation flow
            db_session = get_session()
            try:
                tx = Transaction(
                    txid="integration_tx",
                    session_id="integration_session",
                    tx_type="p2p_transfer",
                    status="broadcast",
                    amount_sats=1000,
                    fee_sats=fee
                )
                db_session.add(tx)
                db_session.commit()

                result = processor.confirm_transaction("integration_tx")
                assert result is True

                db_session.refresh(tx)
                assert tx.status == 'confirmed'
                assert tx.confirmed_at is not None

            finally:
                db_session.close()

    @pytest.mark.stress
    def test_stress_concurrent_transactions(self, processor):
        """Test stress testing with concurrent transactions"""
        import threading
        import time

        results = []
        errors = []

        def create_transaction():
            try:
                session_manager = get_session_manager()
                session = session_manager.create_session(
                    user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                    session_type="p2p_transfer",
                    intent_data={
                        "recipient_pubkey": "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
                        "amount": 100,
                        "asset_id": "BTC"
                    }
                )

                # Create balance
                db_session = get_session()
                try:
                    balance = AssetBalance(
                        user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                        asset_id="BTC",
                        balance=1000,
                        reserved_balance=0
                    )
                    db_session.add(balance)
                    db_session.commit()

                    result = processor.process_p2p_transfer(session.session_id)
                    results.append(result)

                finally:
                    db_session.close()

            except Exception as e:
                errors.append(e)

        start_time = time.time()
        threads = []
        for _ in range(20):
            thread = threading.Thread(target=create_transaction)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()
        end_time = time.time()

        # Should complete within reasonable time
        assert end_time - start_time < 10.0
        assert len(results) + len(errors) == 20

    def test_transaction_metadata_handling(self, processor):
        """Test transaction metadata handling"""
        session_manager = get_session_manager()
        session = session_manager.create_session(
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            session_type="p2p_transfer",
            intent_data={
                "recipient_pubkey": "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
                "amount": 1000,
                "asset_id": "BTC",
                "metadata": {
                    "description": "Test transfer",
                    "priority": "high",
                    "tags": ["test", "transfer"]
                }
            }
        )

        # Create balance
        db_session = get_session()
        try:
            balance = AssetBalance(
                user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
                asset_id="BTC",
                balance=5000,
                reserved_balance=0
            )
            db_session.add(balance)
            db_session.commit()

            result = processor.process_p2p_transfer(session.session_id)
            assert result['amount'] == 1000
            assert result['asset_id'] == 'BTC'

        finally:
            db_session.close()