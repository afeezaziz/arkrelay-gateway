import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from core.models import SigningSession, SigningChallenge, Transaction, get_session
from core.signing_orchestrator import SigningOrchestrator, SigningCeremonyError, SigningTimeoutError, SigningStep
from core.session_manager import get_session_manager, SessionState
from core.challenge_manager import get_challenge_manager

class TestSigningOrchestrator:
    """Test cases for SigningOrchestrator"""

    @pytest.fixture
    def orchestrator(self):
        """Create a signing orchestrator instance"""
        return SigningOrchestrator()

    @pytest.fixture
    def sample_session(self):
        """Create a sample signing session ready for signing"""
        session_manager = get_session_manager()
        session = session_manager.create_session(
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            session_type="p2p_transfer",
            intent_data={
                "recipient_pubkey": "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678",
                "amount": 1000,
                "asset_id": "BTC"
            }
        )

        # Move to awaiting_signature state
        challenge_manager = get_challenge_manager()
        challenge = challenge_manager.create_and_store_challenge(
            session.session_id,
            {"session_id": session.session_id, "test": "data"}
        )

        # Simulate challenge response
        session_manager.validate_challenge_response(session.session_id, b"test_signature")

        return session

    @pytest.fixture
    def sample_challenge(self, sample_session):
        """Create a sample challenge"""
        challenge_manager = get_challenge_manager()
        return challenge_manager.create_and_store_challenge(
            sample_session.session_id,
            {"session_id": sample_session.session_id, "test": "data"}
        )

    def test_start_signing_ceremony_success(self, orchestrator, sample_session):
        """Test successful signing ceremony start"""
        result = orchestrator.start_signing_ceremony(sample_session.session_id)

        assert result['step'] == 1
        assert result['status'] == 'completed'
        assert result['session_type'] == 'p2p_transfer'
        assert result['intent_validated'] is True

        # Verify session was updated
        session_manager = get_session_manager()
        updated_session = session_manager.get_session(sample_session.session_id)
        assert updated_session.status == SessionState.SIGNING.value

    def test_start_signing_ceremony_invalid_session(self, orchestrator):
        """Test starting ceremony with invalid session"""
        with pytest.raises(SigningCeremonyError, match="Session not found"):
            orchestrator.start_signing_ceremony("invalid_session_id")

    def test_start_signing_ceremony_wrong_state(self, orchestrator):
        """Test starting ceremony with session in wrong state"""
        session_manager = get_session_manager()
        session = session_manager.create_session(
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            session_type="p2p_transfer",
            intent_data={"recipient_pubkey": "test_pubkey", "amount": 1000, "asset_id": "BTC"}
        )

        with pytest.raises(SigningCeremonyError, match="is not ready for signing"):
            orchestrator.start_signing_ceremony(session.session_id)

    def test_execute_signing_step_intent_verification_success(self, orchestrator, sample_session):
        """Test successful intent verification step"""
        ceremony_state = {
            'session_id': sample_session.session_id,
            'current_step': 1,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {},
            'transactions': {}
        }

        result = orchestrator._execute_signing_step(sample_session.session_id, SigningStep.INTENT_VERIFICATION, ceremony_state)

        assert result['step'] == 1
        assert result['status'] == 'completed'
        assert result['session_type'] == 'p2p_transfer'
        assert result['intent_validated'] is True

    def test_execute_signing_step_intent_verification_missing_fields(self, orchestrator):
        """Test intent verification with missing required fields"""
        session_manager = get_session_manager()
        session = session_manager.create_session(
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            session_type="p2p_transfer",
            intent_data={"recipient_pubkey": "test_pubkey"}  # Missing amount and asset_id
        )

        ceremony_state = {
            'session_id': session.session_id,
            'current_step': 1,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {},
            'transactions': {}
        }

        with pytest.raises(SigningCeremonyError, match="Missing required field"):
            orchestrator._execute_signing_step(session.session_id, SigningStep.INTENT_VERIFICATION, ceremony_state)

    def test_execute_signing_step_intent_verification_invalid_amount(self, orchestrator):
        """Test intent verification with invalid amount"""
        session_manager = get_session_manager()
        session = session_manager.create_session(
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            session_type="p2p_transfer",
            intent_data={"recipient_pubkey": "test_pubkey", "amount": -100, "asset_id": "BTC"}
        )

        ceremony_state = {
            'session_id': session.session_id,
            'current_step': 1,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {},
            'transactions': {}
        }

        with pytest.raises(SigningCeremonyError, match="Invalid amount"):
            orchestrator._execute_signing_step(session.session_id, SigningStep.INTENT_VERIFICATION, ceremony_state)

    @patch('signing_orchestrator.get_transaction_processor')
    def test_execute_signing_step_ark_transaction_prep_success(self, mock_get_tx_processor, orchestrator, sample_session):
        """Test successful ARK transaction preparation"""
        # Mock transaction processor
        mock_tx_processor = Mock()
        mock_tx_processor.process_p2p_transfer.return_value = {
            'txid': 'test_ark_tx_id',
            'amount': 1000,
            'asset_id': 'BTC'
        }
        mock_get_tx_processor.return_value = mock_tx_processor

        ceremony_state = {
            'session_id': sample_session.session_id,
            'current_step': 2,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {},
            'transactions': {}
        }

        result = orchestrator._execute_signing_step(sample_session.session_id, SigningStep.ARK_TRANSACTION_PREP, ceremony_state)

        assert result['step'] == 2
        assert result['status'] == 'completed'
        assert result['ark_tx_id'] == 'test_ark_tx_id'
        assert 'ark_tx_id' in ceremony_state['transactions']

    def test_execute_signing_step_ark_transaction_prep_non_p2p(self, orchestrator):
        """Test ARK transaction preparation for non-P2P session"""
        session_manager = get_session_manager()
        session = session_manager.create_session(
            user_pubkey="test_user_pubkey_1234567890abcdef1234567890abcdef12345678",
            session_type="lightning_lift",
            intent_data={"amount": 1000, "asset_id": "BTC"}
        )

        ceremony_state = {
            'session_id': session.session_id,
            'current_step': 2,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {},
            'transactions': {}
        }

        result = orchestrator._execute_signing_step(session.session_id, SigningStep.ARK_TRANSACTION_PREP, ceremony_state)

        assert result['step'] == 2
        assert result['status'] == 'completed'
        assert result['ark_tx_id'] is not None

    @patch('signing_orchestrator.get_grpc_manager')
    def test_execute_signing_step_checkpoint_transaction_prep_success(self, mock_get_grpc, orchestrator, sample_session):
        """Test successful checkpoint transaction preparation"""
        # Mock ARKD client
        mock_grpc_manager = Mock()
        mock_arkd = Mock()
        mock_arkd.create_checkpoint_transaction.return_value = {
            'success': True,
            'txid': 'test_checkpoint_tx_id'
        }
        mock_grpc_manager.get_client.return_value = mock_arkd
        mock_get_grpc.return_value = mock_grpc_manager

        ceremony_state = {
            'session_id': sample_session.session_id,
            'current_step': 3,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {},
            'transactions': {'ark_tx': 'test_ark_tx_id'}
        }

        result = orchestrator._execute_signing_step(sample_session.session_id, SigningStep.CHECKPOINT_TRANSACTION_PREP, ceremony_state)

        assert result['step'] == 3
        assert result['status'] == 'completed'
        assert result['checkpoint_tx_id'] == 'test_checkpoint_tx_id'
        assert 'checkpoint_tx' in ceremony_state['transactions']

    @patch('signing_orchestrator.get_grpc_manager')
    def test_execute_signing_step_checkpoint_transaction_prep_failure(self, mock_get_grpc, orchestrator, sample_session):
        """Test checkpoint transaction preparation failure"""
        # Mock ARKD client failure
        mock_grpc_manager = Mock()
        mock_arkd = Mock()
        mock_arkd.create_checkpoint_transaction.return_value = {
            'success': False,
            'error': 'Failed to create checkpoint'
        }
        mock_grpc_manager.get_client.return_value = mock_arkd
        mock_get_grpc.return_value = mock_grpc_manager

        ceremony_state = {
            'session_id': sample_session.session_id,
            'current_step': 3,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {},
            'transactions': {'ark_tx': 'test_ark_tx_id'}
        }

        with pytest.raises(SigningCeremonyError, match="Failed to create checkpoint transaction"):
            orchestrator._execute_signing_step(sample_session.session_id, SigningStep.CHECKPOINT_TRANSACTION_PREP, ceremony_state)

    def test_execute_signing_step_signature_collection_success(self, orchestrator, sample_session, sample_challenge):
        """Test successful signature collection"""
        ceremony_state = {
            'session_id': sample_session.session_id,
            'current_step': 4,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {},
            'transactions': {'ark_tx': 'test_ark_tx_id', 'checkpoint_tx': 'test_checkpoint_tx_id'}
        }

        # Mock challenge with signature
        sample_challenge.signature = b"test_signature"
        sample_challenge.is_used = True

        result = orchestrator._execute_signing_step(sample_session.session_id, SigningStep.SIGNATURE_COLLECTION, ceremony_state)

        assert result['step'] == 4
        assert result['status'] == 'completed'
        assert 'user' in result['signatures_collected']
        assert 'gateway' in ceremony_state['signatures_collected']

    @patch('signing_orchestrator.get_grpc_manager')
    def test_execute_signing_step_ark_protocol_execution_success(self, mock_get_grpc, orchestrator, sample_session):
        """Test successful Ark protocol execution"""
        # Mock ARKD client
        mock_grpc_manager = Mock()
        mock_arkd = Mock()
        mock_arkd.execute_ark_protocol.return_value = {
            'success': True,
            'message': 'Protocol executed successfully'
        }
        mock_grpc_manager.get_client.return_value = mock_arkd
        mock_get_grpc.return_value = mock_grpc_manager

        ceremony_state = {
            'session_id': sample_session.session_id,
            'current_step': 5,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {'user': 'test_signature', 'gateway': 'test_gateway_signature'},
            'transactions': {'ark_tx': 'test_ark_tx_id', 'checkpoint_tx': 'test_checkpoint_tx_id'}
        }

        result = orchestrator._execute_signing_step(sample_session.session_id, SigningStep.ARK_PROTOCOL_EXECUTION, ceremony_state)

        assert result['step'] == 5
        assert result['status'] == 'completed'
        assert result['protocol_result']['success'] is True

    @patch('signing_orchestrator.get_grpc_manager')
    def test_execute_signing_step_ark_protocol_execution_failure(self, mock_get_grpc, orchestrator, sample_session):
        """Test Ark protocol execution failure"""
        # Mock ARKD client failure
        mock_grpc_manager = Mock()
        mock_arkd = Mock()
        mock_arkd.execute_ark_protocol.return_value = {
            'success': False,
            'error': 'Protocol execution failed'
        }
        mock_grpc_manager.get_client.return_value = mock_arkd
        mock_get_grpc.return_value = mock_grpc_manager

        ceremony_state = {
            'session_id': sample_session.session_id,
            'current_step': 5,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {'user': 'test_signature', 'gateway': 'test_gateway_signature'},
            'transactions': {'ark_tx': 'test_ark_tx_id', 'checkpoint_tx': 'test_checkpoint_tx_id'}
        }

        with pytest.raises(SigningCeremonyError, match="Ark protocol execution failed"):
            orchestrator._execute_signing_step(sample_session.session_id, SigningStep.ARK_PROTOCOL_EXECUTION, ceremony_state)

    @patch('signing_orchestrator.get_transaction_processor')
    def test_execute_signing_step_finalization_success(self, mock_get_tx_processor, orchestrator, sample_session):
        """Test successful ceremony finalization"""
        # Mock transaction processor
        mock_tx_processor = Mock()
        mock_tx_processor.broadcast_transaction.return_value = True
        mock_get_tx_processor.return_value = mock_tx_processor

        ceremony_state = {
            'session_id': sample_session.session_id,
            'current_step': 6,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {'user': 'test_signature', 'gateway': 'test_gateway_signature'},
            'transactions': {'ark_tx': 'test_ark_tx_id', 'checkpoint_tx': 'test_checkpoint_tx_id'}
        }

        result = orchestrator._execute_signing_step(sample_session.session_id, SigningStep.FINALIZATION, ceremony_state)

        assert result['step'] == 6
        assert result['status'] == 'completed'
        assert result['txid'] == 'test_ark_tx_id'
        assert result['broadcast_success'] is True
        assert result['session_type'] == 'p2p_transfer'

    @patch('signing_orchestrator.get_transaction_processor')
    def test_execute_signing_step_finalization_broadcast_failure(self, mock_get_tx_processor, orchestrator, sample_session):
        """Test ceremony finalization with broadcast failure"""
        # Mock transaction processor with broadcast failure
        mock_tx_processor = Mock()
        mock_tx_processor.broadcast_transaction.return_value = False
        mock_get_tx_processor.return_value = mock_tx_processor

        ceremony_state = {
            'session_id': sample_session.session_id,
            'current_step': 6,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {'user': 'test_signature', 'gateway': 'test_gateway_signature'},
            'transactions': {'ark_tx': 'test_ark_tx_id', 'checkpoint_tx': 'test_checkpoint_tx_id'}
        }

        with pytest.raises(SigningCeremonyError, match="Failed to broadcast final transaction"):
            orchestrator._execute_signing_step(sample_session.session_id, SigningStep.FINALIZATION, ceremony_state)

    def test_execute_signing_step_finalization_no_transaction_id(self, orchestrator, sample_session):
        """Test ceremony finalization without transaction ID"""
        ceremony_state = {
            'session_id': sample_session.session_id,
            'current_step': 6,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {'user': 'test_signature', 'gateway': 'test_gateway_signature'},
            'transactions': {}  # No transaction ID
        }

        with pytest.raises(SigningCeremonyError, match="No final transaction ID available"):
            orchestrator._execute_signing_step(sample_session.session_id, SigningStep.FINALIZATION, ceremony_state)

    def test_get_ceremony_status_not_started(self, orchestrator, sample_session):
        """Test getting ceremony status for not started ceremony"""
        status = orchestrator.get_ceremony_status(sample_session.session_id)

        assert status['session_id'] == sample_session.session_id
        assert status['ceremony_status'] == 'not_started'
        assert status['current_step'] == 0
        assert status['completed_steps'] == []

    def test_get_ceremony_status_in_progress(self, orchestrator, sample_session):
        """Test getting ceremony status for in-progress ceremony"""
        # Start ceremony
        orchestrator.start_signing_ceremony(sample_session.session_id)

        status = orchestrator.get_ceremony_status(sample_session.session_id)

        assert status['session_id'] == sample_session.session_id
        assert status['ceremony_status'] == 'in_progress'
        assert status['current_step'] > 0
        assert 'time_elapsed' in status
        assert 'time_remaining' in status

    def test_get_ceremony_status_session_not_found(self, orchestrator):
        """Test getting ceremony status for non-existent session"""
        status = orchestrator.get_ceremony_status("nonexistent_session")

        assert 'error' in status
        assert 'not found' in status['error']

    def test_cancel_ceremony_success(self, orchestrator, sample_session):
        """Test successful ceremony cancellation"""
        # Start ceremony
        orchestrator.start_signing_ceremony(sample_session.session_id)

        result = orchestrator.cancel_ceremony(sample_session.session_id, "Test cancellation")

        assert result is True

        # Verify session was failed
        session_manager = get_session_manager()
        session = session_manager.get_session(sample_session.session_id)
        assert session.status == SessionState.FAILED.value
        assert "Test cancellation" in session.error_message

    def test_cancel_ceremony_session_not_found(self, orchestrator):
        """Test cancelling ceremony for non-existent session"""
        result = orchestrator.cancel_ceremony("nonexistent_session")

        assert result is False

    def test_validate_pubkey_valid(self, orchestrator):
        """Test valid public key validation"""
        valid_pubkey = "03a34b99f22c790c4e36b2b3c2c35a36db06226e41c692fc82b8b56ac1c540c5bd"  # 66 chars
        assert orchestrator._validate_pubkey(valid_pubkey) is True

        valid_pubkey_uncompressed = "04a34b99f22c790c4e36b2b3c2c35a36db06226e41c692fc82b8b56ac1c540c5bd" * 2  # 130 chars
        assert orchestrator._validate_pubkey(valid_pubkey_uncompressed) is True

    def test_validate_pubkey_invalid(self, orchestrator):
        """Test invalid public key validation"""
        invalid_pubkey = "invalid_pubkey"
        assert orchestrator._validate_pubkey(invalid_pubkey) is False

        wrong_length = "03a34b99f22c790c4e36b2b3c2c35a36db06226e41c692fc82b8b56ac1c540c5"  # 65 chars
        assert orchestrator._validate_pubkey(wrong_length) is False

    def test_is_ceremony_timed_out(self, orchestrator):
        """Test ceremony timeout detection"""
        # Create ceremony state that started 2 hours ago
        old_time = datetime.utcnow() - timedelta(hours=2)
        ceremony_state = {
            'start_time': old_time,
            'current_step': 1
        }

        # Set timeout to 1 hour
        orchestrator.total_timeout = 3600

        assert orchestrator._is_ceremony_timed_out(ceremony_state) is True

    def test_is_ceremony_not_timed_out(self, orchestrator):
        """Test ceremony not timed out"""
        # Create ceremony state that started 1 minute ago
        recent_time = datetime.utcnow() - timedelta(minutes=1)
        ceremony_state = {
            'start_time': recent_time,
            'current_step': 1
        }

        # Set timeout to 1 hour
        orchestrator.total_timeout = 3600

        assert orchestrator._is_ceremony_timed_out(ceremony_state) is False

    def test_is_ceremony_timed_out_no_start_time(self, orchestrator):
        """Test ceremony timeout with no start time"""
        ceremony_state = {'current_step': 1}

        assert orchestrator._is_ceremony_timed_out(ceremony_state) is False

    @patch('signing_orchestrator.get_grpc_manager')
    def test_execute_signing_step_checkpoint_transaction_no_grpc(self, mock_get_grpc, orchestrator, sample_session):
        """Test checkpoint transaction preparation without gRPC client"""
        # Mock gRPC manager to return None
        mock_grpc_manager = Mock()
        mock_grpc_manager.get_client.return_value = None
        mock_get_grpc.return_value = mock_grpc_manager

        ceremony_state = {
            'session_id': sample_session.session_id,
            'current_step': 3,
            'start_time': datetime.utcnow(),
            'step_start_time': datetime.utcnow(),
            'completed_steps': [],
            'signatures_collected': {},
            'transactions': {'ark_tx': 'test_ark_tx_id'}
        }

        with pytest.raises(SigningCeremonyError, match="ARKD client not available"):
            orchestrator._execute_signing_step(sample_session.session_id, SigningStep.CHECKPOINT_TRANSACTION_PREP, ceremony_state)