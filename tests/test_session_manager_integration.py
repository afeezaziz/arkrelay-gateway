"""
Integration tests for session manager
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import uuid
import hashlib
import json

from core.session_manager import SigningSessionManager, SessionState, SessionType, SessionTransitionError, SessionExpiredError
from core.models import SigningSession, SigningChallenge


class TestSessionManagerIntegration:
    """Integration tests for SigningSessionManager"""

    @pytest.fixture
    def session_manager(self):
        """Create session manager instance"""
        return SigningSessionManager(session_timeout=300, challenge_timeout=180)

    @pytest.fixture
    def test_user_pubkey(self):
        """Test user public key"""
        return "test_user_pubkey_1234567890abcdef1234567890abcdef12345678"

    @pytest.fixture
    def test_recipient_pubkey(self):
        """Test recipient public key"""
        return "test_recipient_pubkey_1234567890abcdef1234567890abcdef12345678"

    @pytest.fixture
    def sample_intent_data(self, test_recipient_pubkey):
        """Sample intent data"""
        return {
            "recipient_pubkey": test_recipient_pubkey,
            "amount": 1000,
            "asset_id": "BTC",
            "metadata": {
                "description": "Test transfer",
                "priority": "high"
            }
        }

    def test_session_manager_initialization(self, session_manager):
        """Test session manager initialization"""
        assert session_manager.session_timeout == 300
        assert session_manager.challenge_timeout == 180
        assert hasattr(session_manager, 'VALID_TRANSITIONS')
        assert SessionState.INITIATED in session_manager.VALID_TRANSITIONS

    def test_create_p2p_transfer_session(self, session_manager, test_user_pubkey, sample_intent_data):
        """Test creating P2P transfer session"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.add = Mock()
            mock_session.commit = Mock()
            mock_session.refresh = Mock()
            mock_session.rollback = Mock()
            mock_get_session.return_value = mock_session

            result = session_manager.create_session(
                user_pubkey=test_user_pubkey,
                session_type="p2p_transfer",
                intent_data=sample_intent_data
            )

            assert result is not None
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once()

            # Verify the session object was created correctly
            call_args = mock_session.add.call_args[0][0]
            assert call_args.user_pubkey == test_user_pubkey
            assert call_args.session_type == "p2p_transfer"
            assert call_args.status == SessionState.INITIATED.value
            assert call_args.intent_data == sample_intent_data

    def test_create_lightning_lift_session(self, session_manager, test_user_pubkey):
        """Test creating lightning lift session"""
        intent_data = {
            "amount": 2000,
            "asset_id": "BTC",
            "lightning_invoice": "lnbc1000n1p3..."
        }

        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.add = Mock()
            mock_session.commit = Mock()
            mock_session.refresh = Mock()
            mock_get_session.return_value = mock_session

            result = session_manager.create_session(
                user_pubkey=test_user_pubkey,
                session_type="lightning_lift",
                intent_data=intent_data
            )

            assert result is not None
            call_args = mock_session.add.call_args[0][0]
            assert call_args.session_type == "lightning_lift"
            assert call_args.intent_data == intent_data

    def test_create_lightning_land_session(self, session_manager, test_user_pubkey):
        """Test creating lightning land session"""
        intent_data = {
            "amount": 1500,
            "asset_id": "BTC",
            "vtxo_proof": "proof_data"
        }

        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.add = Mock()
            mock_session.commit = Mock()
            mock_session.refresh = Mock()
            mock_get_session.return_value = mock_session

            result = session_manager.create_session(
                user_pubkey=test_user_pubkey,
                session_type="lightning_land",
                intent_data=intent_data
            )

            assert result is not None
            call_args = mock_session.add.call_args[0][0]
            assert call_args.session_type == "lightning_land"
            assert call_args.intent_data == intent_data

    def test_create_session_error_handling(self, session_manager, test_user_pubkey, sample_intent_data):
        """Test error handling in session creation"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.add = Mock()
            mock_session.commit = Mock(side_effect=Exception("Database error"))
            mock_session.rollback = Mock()
            mock_get_session.return_value = mock_session

            result = session_manager.create_session(
                user_pubkey=test_user_pubkey,
                session_type="p2p_transfer",
                intent_data=sample_intent_data
            )

            assert result is None
            mock_session.rollback.assert_called_once()

    def test_session_id_generation(self, session_manager, test_user_pubkey, sample_intent_data):
        """Test session ID generation"""
        session_id = session_manager._generate_session_id(test_user_pubkey, "p2p_transfer", sample_intent_data)

        assert isinstance(session_id, str)
        assert len(session_id) == 64  # SHA256 hex digest length

        # Same inputs should generate same ID
        session_id2 = session_manager._generate_session_id(test_user_pubkey, "p2p_transfer", sample_intent_data)
        assert session_id == session_id2

        # Different inputs should generate different IDs
        different_intent = sample_intent_data.copy()
        different_intent["amount"] = 2000
        session_id3 = session_manager._generate_session_id(test_user_pubkey, "p2p_transfer", different_intent)
        assert session_id != session_id3

    def test_get_session_valid(self, session_manager, test_user_pubkey):
        """Test getting valid session"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_query = Mock()
            mock_filter = Mock()
            mock_first = Mock()

            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_filter
            mock_filter.first.return_value = Mock(
                session_id="test_session_id",
                user_pubkey=test_user_pubkey,
                status=SessionState.INITIATED.value,
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )

            mock_get_session.return_value = mock_session

            result = session_manager.get_session("test_session_id")

            assert result is not None
            assert result.session_id == "test_session_id"

    def test_get_session_expired(self, session_manager, test_user_pubkey):
        """Test getting expired session"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_query = Mock()
            mock_filter = Mock()
            mock_first = Mock()

            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_filter
            mock_filter.first.return_value = Mock(
                session_id="test_session_id",
                user_pubkey=test_user_pubkey,
                status=SessionState.INITIATED.value,
                expires_at=datetime.utcnow() - timedelta(hours=1)  # Expired
            )

            mock_get_session.return_value = mock_session

            with pytest.raises(SessionExpiredError):
                session_manager.get_session("test_session_id")

    def test_get_session_not_found(self, session_manager):
        """Test getting non-existent session"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_query = Mock()
            mock_filter = Mock()
            mock_first = Mock()

            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_filter
            mock_filter.first.return_value = None  # Not found

            mock_get_session.return_value = mock_session

            result = session_manager.get_session("nonexistent_session")

            assert result is None

    def test_validate_state_transition_valid(self, session_manager):
        """Test valid state transitions"""
        # Test valid transition: INITIATED -> CHALLENGE_SENT
        session_manager._validate_state_transition(SessionState.INITIATED, SessionState.CHALLENGE_SENT)

        # Test valid transition: CHALLENGE_SENT -> AWAITING_SIGNATURE
        session_manager._validate_state_transition(SessionState.CHALLENGE_SENT, SessionState.AWAITING_SIGNATURE)

        # Test valid transition: AWAITING_SIGNATURE -> SIGNING
        session_manager._validate_state_transition(SessionState.AWAITING_SIGNATURE, SessionState.SIGNING)

        # Test valid transition: SIGNING -> COMPLETED
        session_manager._validate_state_transition(SessionState.SIGNING, SessionState.COMPLETED)

    def test_validate_state_transition_invalid(self, session_manager):
        """Test invalid state transitions"""
        # Test invalid transition: INITIATED -> COMPLETED
        with pytest.raises(SessionTransitionError):
            session_manager._validate_state_transition(SessionState.INITIATED, SessionState.COMPLETED)

        # Test invalid transition: CHALLENGE_SENT -> SIGNING
        with pytest.raises(SessionTransitionError):
            session_manager._validate_state_transition(SessionState.CHALLENGE_SENT, SessionState.SIGNING)

        # Test invalid transition: COMPLETED -> SIGNING (terminal state)
        with pytest.raises(SessionTransitionError):
            session_manager._validate_state_transition(SessionState.COMPLETED, SessionState.SIGNING)

    def test_validate_state_transition_same_state(self, session_manager):
        """Test transition to same state"""
        # Should not raise exception for same state
        session_manager._validate_state_transition(SessionState.INITIATED, SessionState.INITIATED)

    def test_update_session_state_valid(self, session_manager, test_user_pubkey):
        """Test updating session state with valid transition"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_query = Mock()
            mock_filter = Mock()
            mock_first = Mock()
            mock_db_session = Mock()

            mock_db_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_filter
            mock_filter.first.return_value = Mock(
                session_id="test_session_id",
                user_pubkey=test_user_pubkey,
                status=SessionState.INITIATED.value,
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )

            mock_get_session.return_value = mock_db_session

            result = session_manager.update_session_state(
                "test_session_id",
                SessionState.CHALLENGE_SENT,
                "Challenge sent to user"
            )

            assert result is True
            # The session should be committed with new state

    def test_update_session_state_invalid_transition(self, session_manager, test_user_pubkey):
        """Test updating session state with invalid transition"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_query = Mock()
            mock_filter = Mock()
            mock_first = Mock()
            mock_db_session = Mock()

            mock_db_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_filter
            mock_filter.first.return_value = Mock(
                session_id="test_session_id",
                user_pubkey=test_user_pubkey,
                status=SessionState.INITIATED.value,
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )

            mock_get_session.return_value = mock_db_session

            with pytest.raises(SessionTransitionError):
                session_manager.update_session_state(
                    "test_session_id",
                    SessionState.COMPLETED,
                    "Invalid transition"
                )

    def test_update_session_state_not_found(self, session_manager):
        """Test updating state of non-existent session"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_query = Mock()
            mock_filter = Mock()
            mock_first = Mock()

            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_filter
            mock_filter.first.return_value = None  # Not found

            mock_get_session.return_value = mock_session

            result = session_manager.update_session_state(
                "nonexistent_session",
                SessionState.CHALLENGE_SENT,
                "Challenge sent"
            )

            assert result is False

    def test_cleanup_expired_sessions(self, session_manager):
        """Test cleanup of expired sessions"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_query = Mock()
            mock_filter = Mock()
            mock_delete = Mock()

            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_filter
            mock_filter.delete.return_value = 5  # 5 sessions deleted

            mock_get_session.return_value = mock_session

            result = session_manager.cleanup_expired_sessions()

            assert result == 5
            mock_filter.delete.assert_called_once()
            mock_session.commit.assert_called_once()

    def test_get_user_sessions(self, session_manager, test_user_pubkey):
        """Test getting user sessions"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_query = Mock()
            mock_filter = Mock()
            mock_order_by = Mock()
            mock_all = Mock()

            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_filter
            mock_filter.order_by.return_value = mock_order_by
            mock_order_by.all.return_value = [
                Mock(session_id="session1", user_pubkey=test_user_pubkey),
                Mock(session_id="session2", user_pubkey=test_user_pubkey)
            ]

            mock_get_session.return_value = mock_session

            result = session_manager.get_user_sessions(test_user_pubkey)

            assert len(result) == 2
            assert all(session.user_pubkey == test_user_pubkey for session in result)

    def test_get_user_sessions_with_status(self, session_manager, test_user_pubkey):
        """Test getting user sessions filtered by status"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_query = Mock()
            mock_filter = Mock()
            mock_order_by = Mock()
            mock_all = Mock()

            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_filter
            mock_filter.order_by.return_value = mock_order_by
            mock_order_by.all.return_value = [
                Mock(session_id="session1", user_pubkey=test_user_pubkey, status=SessionState.COMPLETED.value)
            ]

            mock_get_session.return_value = mock_session

            result = session_manager.get_user_sessions(
                test_user_pubkey,
                status_filter=SessionState.COMPLETED.value
            )

            assert len(result) == 1
            assert result[0].status == SessionState.COMPLETED.value

    def test_get_active_sessions(self, session_manager):
        """Test getting active sessions"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_query = Mock()
            mock_filter = Mock()
            mock_all = Mock()

            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_filter
            mock_filter.all.return_value = [
                Mock(session_id="session1", status=SessionState.INITIATED.value),
                Mock(session_id="session2", status=SessionState.CHALLENGE_SENT.value)
            ]

            mock_get_session.return_value = mock_session

            result = session_manager.get_active_sessions()

            assert len(result) == 2
            assert all(session.status in [SessionState.INITIATED.value, SessionState.CHALLENGE_SENT.value]
                      for session in result)

    def test_get_session_statistics(self, session_manager):
        """Test getting session statistics"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_query = Mock()
            mock_count = Mock()
            mock_group_by = Mock()
            mock_all = Mock()

            mock_session.query.return_value = mock_query
            mock_query.count.return_value = 100

            mock_query.group_by.return_value = mock_group_by
            mock_group_by.all.return_value = [
                (SessionState.INITIATED.value, 25),
                (SessionState.COMPLETED.value, 50),
                (SessionState.FAILED.value, 25)
            ]

            mock_get_session.return_value = mock_session

            result = session_manager.get_session_statistics()

            assert result['total_sessions'] == 100
            assert result['by_status'][SessionState.INITIATED.value] == 25
            assert result['by_status'][SessionState.COMPLETED.value] == 50
            assert result['by_status'][SessionState.FAILED.value] == 25

    def test_session_timeout_configuration(self):
        """Test session timeout configuration"""
        # Test custom timeout values
        manager1 = SigningSessionManager(session_timeout=600, challenge_timeout=300)
        assert manager1.session_timeout == 600
        assert manager1.challenge_timeout == 300

        # Test default timeout values
        manager2 = SigningSessionManager()
        assert manager2.session_timeout == 300
        assert manager2.challenge_timeout == 180

    def test_concurrent_session_creation(self, session_manager, test_user_pubkey, sample_intent_data):
        """Test concurrent session creation"""
        import threading
        results = []
        errors = []

        def create_session():
            try:
                with patch('core.session_manager.get_session') as mock_get_session:
                    mock_session = Mock()
                    mock_session.add = Mock()
                    mock_session.commit = Mock()
                    mock_session.refresh = Mock()
                    mock_session.rollback = Mock()
                    mock_get_session.return_value = mock_session

                    result = session_manager.create_session(
                        user_pubkey=test_user_pubkey,
                        session_type="p2p_transfer",
                        intent_data=sample_intent_data
                    )
                    results.append(result)
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(5):
            thread = threading.Thread(target=create_session)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert len(results) == 5
        assert len(errors) == 0

    def test_session_lifecycle_complete(self, session_manager, test_user_pubkey, sample_intent_data):
        """Test complete session lifecycle"""
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_query = Mock()
            mock_filter = Mock()
            mock_first = Mock()
            mock_db_session = Mock()

            mock_db_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_filter

            # Mock session creation
            mock_db_session.add = Mock()
            mock_db_session.commit = Mock()
            mock_db_session.refresh = Mock()

            mock_get_session.return_value = mock_db_session

            # Create session
            session = session_manager.create_session(
                user_pubkey=test_user_pubkey,
                session_type="p2p_transfer",
                intent_data=sample_intent_data
            )

            # Mock session retrieval for state transitions
            mock_filter.first.return_value = session

            # Transition through states
            session_manager.update_session_state(session.session_id, SessionState.CHALLENGE_SENT)
            session_manager.update_session_state(session.session_id, SessionState.AWAITING_SIGNATURE)
            session_manager.update_session_state(session.session_id, SessionState.SIGNING)
            session_manager.update_session_state(session.session_id, SessionState.COMPLETED)

            # Verify final state
            assert session.status == SessionState.COMPLETED.value

    @pytest.mark.integration
    def test_integration_with_database_operations(self, session_manager):
        """Test integration with database operations"""
        # This test verifies that the session manager properly integrates
        # with database operations through mocking
        with patch('core.session_manager.get_session') as mock_get_session:
            mock_session = Mock()
            mock_query = Mock()
            mock_filter = Mock()

            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_filter

            # Test database session handling
            mock_session.add = Mock()
            mock_session.commit = Mock()
            mock_session.rollback = Mock()
            mock_session.refresh = Mock()

            mock_get_session.return_value = mock_session

            # Verify database operations are called correctly
            session_manager.get_session("test_id")
            mock_session.query.assert_called()

    @pytest.mark.stress
    def test_stress_session_operations(self, session_manager, test_user_pubkey, sample_intent_data):
        """Test stress testing of session operations"""
        import time

        start_time = time.time()

        # Create many sessions
        for i in range(100):
            with patch('core.session_manager.get_session') as mock_get_session:
                mock_session = Mock()
                mock_session.add = Mock()
                mock_session.commit = Mock()
                mock_session.refresh = Mock()
                mock_get_session.return_value = mock_session

                session_manager.create_session(
                    user_pubkey=f"{test_user_pubkey}_{i}",
                    session_type="p2p_transfer",
                    intent_data=sample_intent_data
                )

        end_time = time.time()

        # Should complete within reasonable time
        assert end_time - start_time < 5.0

    def test_error_handling_comprehensive(self, session_manager):
        """Test comprehensive error handling"""
        # Test with invalid session ID formats
        invalid_ids = [None, "", "invalid_id"]

        for invalid_id in invalid_ids:
            with pytest.raises((TransactionError, ValueError)):
                session_manager.get_session(invalid_id)

            with pytest.raises((TransactionError, ValueError)):
                session_manager.update_session_state(invalid_id, SessionState.CHALLENGE_SENT)

        # Test with invalid state transitions
        with pytest.raises(SessionTransitionError):
            session_manager._validate_state_transition(None, SessionState.CHALLENGE_SENT)

        with pytest.raises(SessionTransitionError):
            session_manager._validate_state_transition(SessionState.INITIATED, None)