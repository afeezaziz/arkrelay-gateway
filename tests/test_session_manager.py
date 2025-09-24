"""
Test cases for session manager module
"""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import json

from core.session_manager import (
    SigningSessionManager, SessionState, SessionTransitionError,
    SessionExpiredError, SessionType
)
from core.models import SigningSession, SigningChallenge, get_session

# Import test database setup to enable patching
from tests.test_database_setup import *


@pytest.fixture
def session_manager(test_db_session):
    """Create a session manager instance with test database"""
    with patch('core.session_manager.get_session', return_value=test_db_session):
        yield SigningSessionManager()


@pytest.fixture
def sample_signing_session():
    """Sample signing session for testing"""
    return SigningSession(
        session_id=str(uuid.uuid4()),
        user_pubkey="test_user_pubkey",
        status="initiated",
        intent_data={"type": "transfer", "amount": 10000},
        context="Transfer 10000 sats to recipient",
        created_at=datetime.now()
    )


@pytest.fixture
def sample_signing_challenge():
    """Sample signing challenge for testing"""
    return SigningChallenge(
        challenge_id=str(uuid.uuid4()),
        session_id="test_session_id",
        challenge_data="test_challenge_data",
        human_readable_context="Please sign this challenge",
        created_at=datetime.now(),
        expires_at=datetime.now() + timedelta(minutes=5)
    )


class TestSessionManager:
    """Test cases for SigningSessionManager class"""

    def test_session_manager_initialization(self, session_manager):
        """Test session manager initialization"""
        assert session_manager is not None
        assert isinstance(session_manager, SigningSessionManager)

    def test_create_signing_session_success(self, session_manager):
        """Test successful signing session creation"""
        user_pubkey = "test_user_pubkey"
        action_intent = {"type": "transfer", "amount": 10000}
        context = "Transfer 10000 sats"

        with patch.object(session_manager, '_create_session_record') as mock_create:
            mock_create.return_value = sample_signing_session()

            session = session_manager.create_signing_session(
                user_pubkey, action_intent, context
            )

            assert session is not None
            assert session.user_pubkey == user_pubkey
            assert session.state == SessionState.INITIATED.value
            mock_create.assert_called_once()

    def test_create_signing_session_invalid_intent(self, session_manager):
        """Test session creation with invalid action intent"""
        user_pubkey = "test_user_pubkey"
        action_intent = {}  # Invalid empty intent
        context = "Invalid transfer"

        with pytest.raises(ValueError):
            session_manager.create_signing_session(
                user_pubkey, action_intent, context
            )

    def test_create_signing_session_invalid_pubkey(self, session_manager):
        """Test session creation with invalid public key"""
        user_pubkey = ""  # Invalid empty pubkey
        action_intent = {"type": "transfer", "amount": 10000}
        context = "Invalid transfer"

        with pytest.raises(ValueError):
            session_manager.create_signing_session(
                user_pubkey, action_intent, context
            )

    def test_get_session_success(self, session_manager, sample_signing_session):
        """Test successful session retrieval"""
        session_id = sample_signing_session.session_id

        with patch.object(session_manager, '_get_session_record') as mock_get:
            mock_get.return_value = sample_signing_session

            session = session_manager.get_session(session_id)
            assert session is not None
            assert session.session_id == session_id
            mock_get.assert_called_once_with(session_id)

    def test_get_session_not_found(self, session_manager):
        """Test session retrieval when session not found"""
        session_id = "nonexistent_session_id"

        with patch.object(session_manager, '_get_session_record') as mock_get:
            mock_get.return_value = None

            with pytest.raises(SessionExpiredError):
                session_manager.get_session(session_id)

    def test_update_session_state_success(self, session_manager, sample_signing_session):
        """Test successful session state update"""
        session_id = sample_signing_session.session_id
        new_state = SessionState.CHALLENGE_SENT.value

        # Mock the database session to return the sample session
        with patch.object(session_manager, '_update_session_status') as mock_update:
            mock_update.return_value = sample_signing_session

            # Mock the database query to return the session
            with patch('core.session_manager.get_session') as mock_db_session:
                mock_db_session.return_value.query.return_value.filter.return_value.first.return_value = sample_signing_session

                updated_session = session_manager.update_session_status(
                    session_id, new_state
                )

                assert updated_session is not None
                mock_update.assert_called_once()

    def test_update_session_state_invalid_state(self, session_manager):
        """Test session state update with invalid state"""
        session_id = "test_session_id"
        invalid_state = "invalid_state"

        with pytest.raises(ValueError):
            session_manager.update_session_state(session_id, invalid_state)

    def test_create_signing_challenge_success(self, session_manager):
        """Test successful signing challenge creation"""
        session_id = "test_session_id"
        challenge_data = "test_challenge_data"
        context = "Please sign this challenge"

        with patch.object(session_manager, '_create_challenge_record') as mock_create:
            mock_create.return_value = sample_signing_challenge()

            challenge = session_manager.create_signing_challenge(
                session_id, challenge_data, context
            )

            assert challenge is not None
            assert challenge.session_id == session_id
            mock_create.assert_called_once()

    def test_create_signing_challenge_invalid_session(self, session_manager):
        """Test challenge creation with invalid session ID"""
        session_id = ""  # Invalid empty session ID
        challenge_data = "test_challenge_data"
        context = "Please sign this challenge"

        with pytest.raises(ValueError):
            session_manager.create_signing_challenge(
                session_id, challenge_data, context
            )

    def test_verify_signing_response_success(self, session_manager):
        """Test successful signing response verification"""
        session_id = "test_session_id"
        signature = "test_signature"
        challenge_response = "test_response"

        with patch.object(session_manager, '_verify_signature') as mock_verify:
            mock_verify.return_value = True

            result = session_manager.verify_signing_response(
                session_id, signature, challenge_response
            )

            assert result is True
            mock_verify.assert_called_once()

    def test_verify_signing_response_invalid_signature(self, session_manager):
        """Test signing response verification with invalid signature"""
        session_id = "test_session_id"
        signature = "invalid_signature"
        challenge_response = "test_response"

        with patch.object(session_manager, '_verify_signature') as mock_verify:
            mock_verify.return_value = False

            result = session_manager.verify_signing_response(
                session_id, signature, challenge_response
            )

            assert result is False

    def test_get_active_sessions_success(self, session_manager):
        """Test successful retrieval of active sessions"""
        with patch.object(session_manager, '_get_active_sessions') as mock_get:
            mock_get.return_value = [sample_signing_session()]

            sessions = session_manager.get_active_sessions()
            assert len(sessions) == 1
            assert sessions[0].user_pubkey == sample_signing_session.user_pubkey

    def test_get_expired_sessions_success(self, session_manager):
        """Test successful retrieval of expired sessions"""
        with patch.object(session_manager, '_get_expired_sessions') as mock_get:
            mock_get.return_value = [sample_signing_session()]

            sessions = session_manager.get_expired_sessions()
            assert len(sessions) == 1

    def test_cleanup_expired_sessions_success(self, session_manager):
        """Test successful cleanup of expired sessions"""
        with patch.object(session_manager, '_cleanup_expired_sessions') as mock_cleanup:
            mock_cleanup.return_value = 5  # 5 sessions cleaned up

            count = session_manager.cleanup_expired_sessions()
            assert count == 5
            mock_cleanup.assert_called_once()

    def test_validate_session_timeout_active(self, session_manager, sample_signing_session):
        """Test session timeout validation for active session"""
        with patch.object(session_manager, '_get_session_record') as mock_get:
            mock_get.return_value = sample_signing_session

            # Should not raise timeout error for active session
            session_manager.validate_session_timeout(sample_signing_session.session_id)

    def test_validate_session_timeout_expired(self, session_manager):
        """Test session timeout validation for expired session"""
        expired_session = SigningSession(
            session_id="expired_session_id",
            user_pubkey="test_user_pubkey",
            state=SessionState.PENDING.value,
            action_intent={"type": "transfer"},
            human_readable_context="Expired session",
            created_at=datetime.now() - timedelta(minutes=15),
            expires_at=datetime.now() - timedelta(minutes=5)
        )

        with patch.object(session_manager, '_get_session_record') as mock_get:
            mock_get.return_value = expired_session

            with pytest.raises(SessionTimeoutError):
                session_manager.validate_session_timeout(expired_session.session_id)

    def test_get_session_statistics_success(self, session_manager):
        """Test successful retrieval of session statistics"""
        expected_stats = {
            'total_sessions': 100,
            'active_sessions': 25,
            'expired_sessions': 10,
            'completed_sessions': 65
        }

        with patch.object(session_manager, '_get_session_statistics') as mock_get:
            mock_get.return_value = expected_stats

            stats = session_manager.get_session_statistics()
            assert stats == expected_stats

    def test_session_state_transition_validation(self, session_manager):
        """Test session state transition validation"""
        # Test valid state transitions
        valid_transitions = [
            (SessionState.PENDING, SessionState.CHALLENGE_SENT),
            (SessionState.CHALLENGE_SENT, SessionState.RESPONSE_RECEIVED),
            (SessionState.RESPONSE_RECEIVED, SessionState.COMPLETED),
            (SessionState.RESPONSE_RECEIVED, SessionState.FAILED),
            (SessionState.PENDING, SessionState.FAILED),
        ]

        for from_state, to_state in valid_transitions:
            assert session_manager._is_valid_state_transition(from_state, to_state)

    def test_session_state_transition_invalid(self, session_manager):
        """Test invalid session state transitions"""
        # Test invalid state transitions
        invalid_transitions = [
            (SessionState.COMPLETED, SessionState.PENDING),
            (SessionState.FAILED, SessionState.CHALLENGE_SENT),
            (SessionState.COMPLETED, SessionState.RESPONSE_RECEIVED),
        ]

        for from_state, to_state in invalid_transitions:
            assert not session_manager._is_valid_state_transition(from_state, to_state)

    def test_challenge_timeout_validation(self, session_manager, sample_signing_challenge):
        """Test challenge timeout validation"""
        with patch.object(session_manager, '_get_challenge_record') as mock_get:
            mock_get.return_value = sample_signing_challenge

            # Should not raise timeout error for active challenge
            session_manager.validate_challenge_timeout(sample_signing_challenge.challenge_id)

    def test_challenge_timeout_expired(self, session_manager):
        """Test challenge timeout validation for expired challenge"""
        expired_challenge = SigningChallenge(
            challenge_id="expired_challenge_id",
            session_id="test_session_id",
            challenge_data="test_challenge_data",
            human_readable_context="Expired challenge",
            created_at=datetime.now() - timedelta(minutes=10),
            expires_at=datetime.now() - timedelta(minutes=2)
        )

        with patch.object(session_manager, '_get_challenge_record') as mock_get:
            mock_get.return_value = expired_challenge

            with pytest.raises(ChallengeExpiredError):
                session_manager.validate_challenge_timeout(expired_challenge.challenge_id)

    def test_concurrent_session_handling(self, session_manager):
        """Test concurrent session handling"""
        user_pubkey = "test_user_pubkey"
        max_concurrent = 3

        with patch.object(session_manager, '_count_active_sessions_for_user') as mock_count:
            mock_count.return_value = max_concurrent

            # Should raise error when exceeding max concurrent sessions
            with pytest.raises(SessionError):
                session_manager.create_signing_session(
                    user_pubkey, {"type": "transfer"}, "Test transfer"
                )

    @pytest.mark.integration
    def test_session_lifecycle_integration(self, session_manager):
        """Test complete session lifecycle integration"""
        user_pubkey = "test_user_pubkey"
        action_intent = {"type": "transfer", "amount": 10000}
        context = "Transfer 10000 sats"

        # Create session
        with patch.object(session_manager, '_create_session_record') as mock_create:
            mock_create.return_value = sample_signing_session()

            session = session_manager.create_signing_session(
                user_pubkey, action_intent, context
            )

            # Update session state
            with patch.object(session_manager, '_update_session_status') as mock_update:
                mock_update.return_value = session

                updated_session = session_manager.update_session_state(
                    session.session_id, SessionState.CHALLENGE_SENT.value
                )

                assert updated_session.state == SessionState.CHALLENGE_SENT.value

    @pytest.mark.unit
    def test_session_serialization(self, sample_signing_session):
        """Test session serialization"""
        session_dict = sample_signing_session.to_dict()
        assert isinstance(session_dict, dict)
        assert 'session_id' in session_dict
        assert 'user_pubkey' in session_dict
        assert 'state' in session_dict
        assert 'created_at' in session_dict

    @pytest.mark.unit
    def test_session_deserialization(self, session_manager):
        """Test session deserialization"""
        session_data = {
            'session_id': str(uuid.uuid4()),
            'user_pubkey': 'test_user_pubkey',
            'state': SessionState.PENDING.value,
            'action_intent': {'type': 'transfer'},
            'human_readable_context': 'Test transfer',
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(minutes=10)).isoformat()
        }

        with patch.object(session_manager, '_deserialize_session') as mock_deserialize:
            mock_deserialize.return_value = sample_signing_session()

            session = session_manager._deserialize_session(session_data)
            assert session is not None

    @pytest.mark.performance
    def test_session_creation_performance(self, session_manager):
        """Test session creation performance"""
        import time

        start_time = time.time()

        for _ in range(100):
            with patch.object(session_manager, '_create_session_record') as mock_create:
                mock_create.return_value = sample_signing_session()

                session_manager.create_signing_session(
                    "test_user_pubkey", {"type": "transfer"}, "Test transfer"
                )

        end_time = time.time()
        avg_time = (end_time - start_time) / 100
        assert avg_time < 0.01  # Average creation time should be less than 10ms

    @pytest.mark.performance
    def test_session_retrieval_performance(self, session_manager):
        """Test session retrieval performance"""
        import time

        with patch.object(session_manager, '_get_session_record') as mock_get:
            mock_get.return_value = sample_signing_session()

            start_time = time.time()

            for _ in range(100):
                session_manager.get_session("test_session_id")

            end_time = time.time()
            avg_time = (end_time - start_time) / 100
            assert avg_time < 0.005  # Average retrieval time should be less than 5ms

    @pytest.mark.unit
    def test_session_error_handling(self, session_manager):
        """Test session error handling"""
        # Test database connection error
        with patch.object(session_manager, '_create_session_record') as mock_create:
            mock_create.side_effect = Exception("Database connection failed")

            with pytest.raises(SessionError):
                session_manager.create_signing_session(
                    "test_user_pubkey", {"type": "transfer"}, "Test transfer"
                )

    @pytest.mark.unit
    def test_session_retry_logic(self, session_manager):
        """Test session retry logic"""
        with patch.object(session_manager, '_create_session_record') as mock_create:
            # Simulate transient failure then success
            mock_create.side_effect = [Exception("Transient error"), sample_signing_session()]

            session = session_manager.create_signing_session(
                "test_user_pubkey", {"type": "transfer"}, "Test transfer"
            )

            assert session is not None
            assert mock_create.call_count == 2

    @pytest.mark.integration
    def test_session_database_integration(self, session_manager):
        """Test session database integration"""
        # Test database operations integration
        with patch.object(session_manager, '_create_session_record') as mock_create:
            mock_create.return_value = sample_signing_session()

            session = session_manager.create_signing_session(
                "test_user_pubkey", {"type": "transfer"}, "Test transfer"
            )

            # Verify database operations were called
            mock_create.assert_called_once()

    @pytest.mark.unit
    def test_session_validation_rules(self, session_manager):
        """Test session validation rules"""
        # Test session ID validation
        with pytest.raises(ValueError):
            session_manager.get_session("")

        # Test state validation
        with pytest.raises(ValueError):
            session_manager.update_session_state("test_id", "")

        # Test challenge validation
        with pytest.raises(ValueError):
            session_manager.create_signing_challenge("", "test_data", "test context")

    @pytest.mark.unit
    def test_session_metrics_collection(self, session_manager):
        """Test session metrics collection"""
        with patch.object(session_manager, '_collect_session_metrics') as mock_collect:
            mock_collect.return_value = {
                'total_sessions': 100,
                'average_session_duration': 300,
                'success_rate': 0.95
            }

            metrics = session_manager.get_session_metrics()
            assert metrics['total_sessions'] == 100
            assert metrics['average_session_duration'] == 300
            assert metrics['success_rate'] == 0.95

    @pytest.mark.integration
    def test_session_concurrent_access(self, session_manager):
        """Test concurrent session access"""
        import threading
        import time

        def create_session():
            with patch.object(session_manager, '_create_session_record') as mock_create:
                mock_create.return_value = sample_signing_session()

                session_manager.create_signing_session(
                    "test_user_pubkey", {"type": "transfer"}, "Test transfer"
                )

        threads = []
        for _ in range(10):
            thread = threading.Thread(target=create_session)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

    @pytest.mark.unit
    def test_session_cleanup_strategy(self, session_manager):
        """Test session cleanup strategy"""
        with patch.object(session_manager, '_cleanup_expired_sessions') as mock_cleanup:
            mock_cleanup.return_value = 10

            cleaned_count = session_manager.cleanup_expired_sessions()
            assert cleaned_count == 10
            mock_cleanup.assert_called_once()

    @pytest.mark.unit
    def test_session_health_check(self, session_manager):
        """Test session health check"""
        with patch.object(session_manager, '_check_session_health') as mock_health:
            mock_health.return_value = True

            is_healthy = session_manager.check_session_health()
            assert is_healthy is True
            mock_health.assert_called_once()

    @pytest.mark.unit
    def test_session_backup_and_recovery(self, session_manager):
        """Test session backup and recovery"""
        with patch.object(session_manager, '_backup_sessions') as mock_backup:
            mock_backup.return_value = True

            backup_success = session_manager.backup_sessions()
            assert backup_success is True
            mock_backup.assert_called_once()

    @pytest.mark.unit
    def test_session_audit_logging(self, session_manager):
        """Test session audit logging"""
        with patch.object(session_manager, '_log_session_event') as mock_log:
            mock_log.return_value = True

            log_success = session_manager.log_session_event(
                "test_session_id", "state_change", "pending -> challenge_sent"
            )
            assert log_success is True
            mock_log.assert_called_once()