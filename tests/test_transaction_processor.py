import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from models import Transaction, SigningSession, AssetBalance, Asset, get_session
from transaction_processor import TransactionProcessor, TransactionError, InsufficientFundsError, InvalidTransactionError
from session_manager import get_session_manager

class TestTransactionProcessor:
    """Test cases for TransactionProcessor"""

    @pytest.fixture
    def processor(self):
        """Create a transaction processor instance"""
        return TransactionProcessor()

    @pytest.fixture
    def sample_session(self):
        """Create a sample signing session"""
        session_manager = get_session_manager()
        return session_manager.create_session(
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            session_type="p2p_transfer",
            intent_data={
                "recipient_pubkey": "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
                "amount": 1000,
                "asset_id": "BTC"
            }
        )

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
                reserved_balance=0
            )
            db_session.add(balance)
            db_session.commit()
            db_session.refresh(balance)
            return balance
        finally:
            db_session.close()

    def test_process_p2p_transfer_success(self, processor, sample_session, sample_balance):
        """Test successful P2P transfer processing"""
        result = processor.process_p2p_transfer(sample_session.session_id)

        assert result['txid'] is not None
        assert result['amount'] == 1000
        assert result['asset_id'] == 'BTC'
        assert result['sender'] == 'test_user_...'
        assert result['recipient'] == 'test_rec...'
        assert result['status'] == 'pending_signatures'

        # Verify transaction was created
        db_session = get_session()
        try:
            tx = db_session.query(Transaction).filter_by(session_id=sample_session.session_id).first()
            assert tx is not None
            assert tx.tx_type == 'p2p_transfer'
            assert tx.amount_sats == 1000
            assert tx.status == 'pending'
        finally:
            db_session.close()

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