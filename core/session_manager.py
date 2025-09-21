import uuid
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
from enum import Enum
import logging
from core.models import SigningSession, SigningChallenge, get_session
from sqlalchemy import and_, or_

logger = logging.getLogger(__name__)

class SessionState(Enum):
    INITIATED = 'initiated'
    CHALLENGE_SENT = 'challenge_sent'
    AWAITING_SIGNATURE = 'awaiting_signature'
    SIGNING = 'signing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    EXPIRED = 'expired'

class SessionType(Enum):
    P2P_TRANSFER = 'p2p_transfer'
    LIGHTNING_LIFT = 'lightning_lift'
    LIGHTNING_LAND = 'lightning_land'

class SessionTransitionError(Exception):
    """Raised when invalid state transition is attempted"""
    pass

class SessionExpiredError(Exception):
    """Raised when session operation is attempted on expired session"""
    pass

class SigningSessionManager:
    """Manages signing sessions with state machine logic"""

    # Valid state transitions
    VALID_TRANSITIONS = {
        SessionState.INITIATED: [SessionState.CHALLENGE_SENT, SessionState.FAILED, SessionState.EXPIRED],
        SessionState.CHALLENGE_SENT: [SessionState.AWAITING_SIGNATURE, SessionState.FAILED, SessionState.EXPIRED],
        SessionState.AWAITING_SIGNATURE: [SessionState.SIGNING, SessionState.FAILED, SessionState.EXPIRED],
        SessionState.SIGNING: [SessionState.COMPLETED, SessionState.FAILED, SessionState.EXPIRED],
        SessionState.COMPLETED: [],  # Terminal state
        SessionState.FAILED: [],     # Terminal state
        SessionState.EXPIRED: []     # Terminal state
    }

    def __init__(self, session_timeout: int = 300, challenge_timeout: int = 180):
        """
        Initialize session manager

        Args:
            session_timeout: Default session timeout in seconds (5 minutes)
            challenge_timeout: Default challenge timeout in seconds (3 minutes)
        """
        self.session_timeout = session_timeout
        self.challenge_timeout = challenge_timeout

    def create_session(self, user_pubkey: str, session_type: str, intent_data: Dict[str, Any]) -> SigningSession:
        """
        Create a new signing session

        Args:
            user_pubkey: User's public key
            session_type: Type of session (p2p_transfer, lightning_lift, lightning_land)
            intent_data: Original intent data

        Returns:
            SigningSession object
        """
        session = get_session()
        try:
            # Generate unique session ID
            session_id = self._generate_session_id(user_pubkey, session_type, intent_data)

            # Calculate expiration time
            expires_at = datetime.utcnow() + timedelta(seconds=self.session_timeout)

            # Create session
            new_session = SigningSession(
                session_id=session_id,
                user_pubkey=user_pubkey,
                session_type=session_type,
                status=SessionState.INITIATED.value,
                intent_data=intent_data,
                expires_at=expires_at
            )

            session.add(new_session)
            session.commit()
            session.refresh(new_session)

            logger.info(f"Created session {session_id} for user {user_pubkey[:8]}...")
            return new_session

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create session: {e}")
            raise
        finally:
            session.close()

    def get_session(self, session_id: str) -> Optional[SigningSession]:
        """Get session by ID, checking for expiration"""
        db_session = get_session()
        try:
            session = db_session.query(SigningSession).filter_by(session_id=session_id).first()

            if not session:
                return None

            # Check if session is expired
            if session.expires_at < datetime.utcnow() and session.status not in ['completed', 'failed', 'expired']:
                self._update_session_status(session, SessionState.EXPIRED.value, "Session expired")
                session = db_session.query(SigningSession).filter_by(session_id=session_id).first()

            return session

        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None
        finally:
            db_session.close()

    def update_session_status(self, session_id: str, new_status: str, message: str = None) -> bool:
        """
        Update session status with state transition validation

        Args:
            session_id: Session ID
            new_status: New status to transition to
            message: Optional message for the transition

        Returns:
            True if successful, False otherwise
        """
        session = get_session()
        try:
            db_session_obj = session.query(SigningSession).filter_by(session_id=session_id).first()
            if not db_session_obj:
                logger.error(f"Session {session_id} not found")
                return False

            # Check if session is expired
            if db_session_obj.expires_at < datetime.utcnow():
                self._update_session_status(db_session_obj, SessionState.EXPIRED.value, "Session expired")
                session.commit()
                return False

            # Validate state transition
            if not self._is_valid_transition(db_session_obj.status, new_status):
                raise SessionTransitionError(
                    f"Invalid transition from {db_session_obj.status} to {new_status}"
                )

            # Update status
            self._update_session_status(db_session_obj, new_status, message)
            session.commit()

            logger.info(f"Session {session_id} transitioned to {new_status}")
            return True

        except SessionTransitionError as e:
            logger.error(f"Invalid state transition for session {session_id}: {e}")
            session.rollback()
            return False
        except Exception as e:
            logger.error(f"Error updating session {session_id}: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def create_challenge(self, session_id: str, challenge_data: bytes, context: str) -> SigningChallenge:
        """
        Create a signing challenge for a session

        Args:
            session_id: Session ID
            challenge_data: Binary challenge data
            context: Human-readable context

        Returns:
            SigningChallenge object
        """
        session = get_session()
        try:
            # Get the session
            db_session = session.query(SigningSession).filter_by(session_id=session_id).first()
            if not db_session:
                raise ValueError(f"Session {session_id} not found")

            # Check session state
            if db_session.status != SessionState.INITIATED.value:
                raise SessionTransitionError(f"Cannot create challenge for session in state {db_session.status}")

            # Generate challenge ID
            challenge_id = self._generate_challenge_id(session_id, challenge_data)

            # Calculate expiration
            expires_at = datetime.utcnow() + timedelta(seconds=self.challenge_timeout)

            # Create challenge
            challenge = SigningChallenge(
                challenge_id=challenge_id,
                session_id=session_id,
                challenge_data=challenge_data,
                context=context,
                expires_at=expires_at
            )

            # Update session
            db_session.challenge_id = challenge_id
            db_session.context = context
            self._update_session_status(db_session, SessionState.CHALLENGE_SENT.value)

            session.add(challenge)
            session.commit()
            session.refresh(challenge)

            logger.info(f"Created challenge {challenge_id} for session {session_id}")
            return challenge

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create challenge: {e}")
            raise
        finally:
            session.close()

    def validate_challenge_response(self, session_id: str, signature: bytes) -> bool:
        """
        Validate a challenge response (signature)

        Args:
            session_id: Session ID
            signature: User's signature

        Returns:
            True if valid, False otherwise
        """
        session = get_session()
        try:
            db_session = session.query(SigningSession).filter_by(session_id=session_id).first()
            if not db_session or not db_session.challenge_id:
                return False

            challenge = session.query(SigningChallenge).filter_by(challenge_id=db_session.challenge_id).first()
            if not challenge:
                return False

            # Check if challenge is expired
            if challenge.expires_at < datetime.utcnow():
                self._update_session_status(db_session, SessionState.EXPIRED.value, "Challenge expired")
                session.commit()
                return False

            # Check if already used
            if challenge.is_used:
                return False

            # Store signature and mark as used
            challenge.signature = signature
            challenge.is_used = True

            # Update session status
            self._update_session_status(db_session, SessionState.AWAITING_SIGNATURE.value)
            session.commit()

            logger.info(f"Validated challenge response for session {session_id}")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Error validating challenge response: {e}")
            return False
        finally:
            session.close()

    def complete_session(self, session_id: str, result_data: Dict[str, Any], signed_tx: str = None) -> bool:
        """
        Mark session as completed with result data

        Args:
            session_id: Session ID
            result_data: Final transaction details
            signed_tx: Optional signed transaction hex

        Returns:
            True if successful, False otherwise
        """
        return self.update_session_status(
            session_id,
            SessionState.COMPLETED.value,
            "Session completed successfully"
        ) and self._update_session_result(session_id, result_data, signed_tx)

    def fail_session(self, session_id: str, error_message: str) -> bool:
        """
        Mark session as failed with error message

        Args:
            session_id: Session ID
            error_message: Error description

        Returns:
            True if successful, False otherwise
        """
        return self.update_session_status(session_id, SessionState.FAILED.value, error_message)

    def get_active_sessions(self, user_pubkey: str = None) -> List[SigningSession]:
        """
        Get active sessions for a user or all users

        Args:
            user_pubkey: Optional user pubkey to filter by

        Returns:
            List of active sessions
        """
        session = get_session()
        try:
            query = session.query(SigningSession).filter(
                SigningSession.status.in_([
                    SessionState.INITIATED.value,
                    SessionState.CHALLENGE_SENT.value,
                    SessionState.AWAITING_SIGNATURE.value,
                    SessionState.SIGNING.value
                ]),
                SigningSession.expires_at > datetime.utcnow()
            )

            if user_pubkey:
                query = query.filter(SigningSession.user_pubkey == user_pubkey)

            return query.order_by(SigningSession.created_at.desc()).all()

        except Exception as e:
            logger.error(f"Error getting active sessions: {e}")
            return []
        finally:
            session.close()

    def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions

        Returns:
            Number of sessions cleaned up
        """
        session = get_session()
        try:
            # Find expired sessions that aren't already marked as expired
            expired_sessions = session.query(SigningSession).filter(
                SigningSession.expires_at < datetime.utcnow(),
                ~SigningSession.status.in_(['completed', 'failed', 'expired'])
            ).all()

            count = 0
            for sess in expired_sessions:
                self._update_session_status(sess, SessionState.EXPIRED.value, "Session expired")
                count += 1

            session.commit()

            if count > 0:
                logger.info(f"Cleaned up {count} expired sessions")

            return count

        except Exception as e:
            session.rollback()
            logger.error(f"Error cleaning up expired sessions: {e}")
            return 0
        finally:
            session.close()

    def _generate_session_id(self, user_pubkey: str, session_type: str, intent_data: Dict[str, Any]) -> str:
        """Generate unique session ID"""
        data = f"{user_pubkey}{session_type}{json.dumps(intent_data, sort_keys=True)}{datetime.utcnow().isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()

    def _generate_challenge_id(self, session_id: str, challenge_data: bytes) -> str:
        """Generate unique challenge ID"""
        data = f"{session_id}{challenge_data.hex()}{datetime.utcnow().isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()

    def _is_valid_transition(self, current_status: str, new_status: str) -> bool:
        """Check if state transition is valid"""
        try:
            current_state = SessionState(current_status)
            new_state = SessionState(new_status)
            return new_state in self.VALID_TRANSITIONS[current_state]
        except ValueError:
            return False

    def _update_session_status(self, session_obj: SigningSession, new_status: str, message: str = None):
        """Update session status and message"""
        session_obj.status = new_status
        session_obj.updated_at = datetime.utcnow()
        if message:
            session_obj.error_message = message

    def _update_session_result(self, session_id: str, result_data: Dict[str, Any], signed_tx: str = None) -> bool:
        """Update session result data"""
        session = get_session()
        try:
            db_session = session.query(SigningSession).filter_by(session_id=session_id).first()
            if not db_session:
                return False

            db_session.result_data = result_data
            db_session.signed_tx = signed_tx
            db_session.updated_at = datetime.utcnow()

            session.commit()
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Error updating session result: {e}")
            return False
        finally:
            session.close()

# Global session manager instance
session_manager = SigningSessionManager()

def get_session_manager() -> SigningSessionManager:
    """Get the global session manager instance"""
    return session_manager