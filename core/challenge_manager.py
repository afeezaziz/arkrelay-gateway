import hashlib
import json
import base64
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, Tuple
import logging
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from core.models import SigningChallenge, SigningSession, get_session
from core.session_manager import SessionState, get_session_manager

logger = logging.getLogger(__name__)

class ChallengeManager:
    """Manages signing challenges with validation and context generation"""

    def __init__(self, challenge_timeout: int = 180):
        """
        Initialize challenge manager

        Args:
            challenge_timeout: Default challenge timeout in seconds (3 minutes)
        """
        self.challenge_timeout = challenge_timeout

    def generate_challenge(self, session_id: str, context_data: Dict[str, Any]) -> Tuple[str, bytes, str]:
        """
        Generate a signing challenge for a session

        Args:
            session_id: Session ID
            context_data: Data to include in the challenge context

        Returns:
            Tuple of (challenge_id, challenge_data, human_readable_context)
        """
        # Get session
        session = get_session()
        try:
            db_session = session.query(SigningSession).filter_by(session_id=session_id).first()
            if not db_session:
                raise ValueError(f"Session {session_id} not found")

            if db_session.status != SessionState.INITIATED.value:
                raise ValueError(f"Session {session_id} is not in initiated state")

            # Generate challenge data
            challenge_data = self._create_challenge_data(session_id, context_data)

            # Generate human-readable context
            human_context = self._generate_human_readable_context(db_session, context_data)

            # Generate challenge ID
            challenge_id = self._generate_challenge_id(session_id, challenge_data)

            return challenge_id, challenge_data, human_context

        finally:
            session.close()

    def validate_challenge_response(self, session_id: str, signature: bytes, user_pubkey: str) -> bool:
        """
        Validate a user's signature response to a challenge

        Args:
            session_id: Session ID
            signature: User's signature
            user_pubkey: User's public key

        Returns:
            True if valid, False otherwise
        """
        session = get_session()
        try:
            # Get session and challenge
            db_session = session.query(SigningSession).filter_by(session_id=session_id).first()
            if not db_session or not db_session.challenge_id:
                logger.error(f"Session {session_id} or challenge not found")
                return False

            challenge = session.query(SigningChallenge).filter_by(challenge_id=db_session.challenge_id).first()
            if not challenge:
                logger.error(f"Challenge not found for session {session_id}")
                return False

            # Check expiration
            if challenge.expires_at < datetime.utcnow():
                logger.error(f"Challenge expired for session {session_id}")
                return False

            # Check if already used
            if challenge.is_used:
                logger.error(f"Challenge already used for session {session_id}")
                return False

            # Verify signature
            if not self._verify_signature(challenge.challenge_data, signature, user_pubkey):
                logger.error(f"Invalid signature for session {session_id}")
                return False

            # Mark challenge as used and store signature
            challenge.signature = signature
            challenge.is_used = True
            session.commit()

            logger.info(f"Successfully validated challenge response for session {session_id}")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Error validating challenge response: {e}")
            return False
        finally:
            session.close()

    def get_challenge_context(self, session_id: str) -> Optional[str]:
        """
        Get the human-readable context for a session's challenge

        Args:
            session_id: Session ID

        Returns:
            Human-readable context string or None
        """
        session = get_session()
        try:
            db_session = session.query(SigningSession).filter_by(session_id=session_id).first()
            if not db_session:
                return None

            if db_session.challenge_id:
                challenge = session.query(SigningChallenge).filter_by(challenge_id=db_session.challenge_id).first()
                if challenge:
                    return challenge.context

            return db_session.context

        except Exception as e:
            logger.error(f"Error getting challenge context: {e}")
            return None
        finally:
            session.close()

    def create_and_store_challenge(self, session_id: str, context_data: Dict[str, Any]) -> Optional[SigningChallenge]:
        """
        Create and store a challenge for a session

        Args:
            session_id: Session ID
            context_data: Context data for the challenge

        Returns:
            SigningChallenge object or None
        """
        try:
            # Generate challenge components
            challenge_id, challenge_data, human_context = self.generate_challenge(session_id, context_data)

            # Use session manager to create and store the challenge
            session_manager = get_session_manager()
            challenge = session_manager.create_challenge(session_id, challenge_data, human_context)

            return challenge

        except Exception as e:
            logger.error(f"Error creating challenge for session {session_id}: {e}")
            return None

    def cleanup_expired_challenges(self) -> int:
        """
        Clean up expired challenges

        Returns:
            Number of challenges cleaned up
        """
        session = get_session()
        try:
            expired_challenges = session.query(SigningChallenge).filter(
                SigningChallenge.expires_at < datetime.utcnow(),
                SigningChallenge.is_used == False
            ).all()

            count = len(expired_challenges)
            if count > 0:
                for challenge in expired_challenges:
                    session.delete(challenge)

                session.commit()
                logger.info(f"Cleaned up {count} expired challenges")

            return count

        except Exception as e:
            session.rollback()
            logger.error(f"Error cleaning up expired challenges: {e}")
            return 0
        finally:
            session.close()

    def _create_challenge_data(self, session_id: str, context_data: Dict[str, Any]) -> bytes:
        """
        Create binary challenge data

        Args:
            session_id: Session ID
            context_data: Context data to include

        Returns:
            Binary challenge data
        """
        # Create structured challenge data
        challenge_struct = {
            'session_id': session_id,
            'timestamp': datetime.utcnow().isoformat(),
            'nonce': self._generate_nonce(),
            'context': context_data
        }

        # Serialize and hash
        challenge_json = json.dumps(challenge_struct, sort_keys=True)
        challenge_hash = hashlib.sha256(challenge_json.encode()).digest()

        return challenge_hash

    def _generate_human_readable_context(self, db_session: SigningSession, context_data: Dict[str, Any]) -> str:
        """
        Generate human-readable context for the user

        Args:
            db_session: Database session object
            context_data: Context data

        Returns:
            Human-readable context string
        """
        session_type = db_session.session_type
        intent_data = db_session.intent_data

        context_parts = [f"Ark Relay Gateway - {session_type.replace('_', ' ').title()}"]

        if session_type == 'p2p_transfer':
            amount = intent_data.get('amount', 0)
            recipient = intent_data.get('recipient_pubkey', '')[:8] + '...'
            asset = intent_data.get('asset_id', 'BTC')
            context_parts.extend([
                f"Amount: {amount} {asset}",
                f"Recipient: {recipient}",
                f"Session: {db_session.session_id[:8]}..."
            ])

        elif session_type == 'lightning_lift':
            amount = intent_data.get('amount', 0)
            asset = intent_data.get('asset_id', 'BTC')
            context_parts.extend([
                f"Lightning Lift (On-ramp)",
                f"Amount: {amount} {asset}",
                f"Session: {db_session.session_id[:8]}..."
            ])

        elif session_type == 'lightning_land':
            amount = intent_data.get('amount', 0)
            asset = intent_data.get('asset_id', 'BTC')
            context_parts.extend([
                f"Lightning Land (Off-ramp)",
                f"Amount: {amount} {asset}",
                f"Session: {db_session.session_id[:8]}..."
            ])

        # Add timestamp and expiry
        context_parts.extend([
            f"Created: {db_session.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Expires: {db_session.expires_at.strftime('%Y-%m-%d %H:%M:%S')}"
        ])

        return "\n".join(context_parts)

    def _generate_challenge_id(self, session_id: str, challenge_data: bytes) -> str:
        """Generate unique challenge ID"""
        data = f"{session_id}{challenge_data.hex()}{datetime.utcnow().isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()

    def _generate_nonce(self) -> str:
        """Generate a random nonce"""
        import secrets
        return secrets.token_hex(16)

    def _verify_signature(self, challenge_data: bytes, signature: bytes, pubkey_hex: str) -> bool:
        """
        Verify ECDSA signature

        Args:
            challenge_data: Original challenge data
            signature: Signature to verify
            pubkey_hex: Public key in hex format

        Returns:
            True if valid, False otherwise
        """
        try:
            # Convert hex pubkey to bytes
            if pubkey_hex.startswith('0x'):
                pubkey_hex = pubkey_hex[2:]

            pubkey_bytes = bytes.fromhex(pubkey_hex)

            # Load public key
            public_key = serialization.load_der_public_key(
                pubkey_bytes,
                backend=default_backend()
            )

            # Verify signature
            public_key.verify(
                signature,
                challenge_data,
                ec.ECDSA(hashes.SHA256())
            )

            return True

        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    def get_challenge_info(self, challenge_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a challenge

        Args:
            challenge_id: Challenge ID

        Returns:
            Challenge information dictionary or None
        """
        session = get_session()
        try:
            challenge = session.query(SigningChallenge).filter_by(challenge_id=challenge_id).first()
            if not challenge:
                return None

            return {
                'challenge_id': challenge.challenge_id,
                'session_id': challenge.session_id,
                'context': challenge.context,
                'expires_at': challenge.expires_at.isoformat(),
                'is_used': challenge.is_used,
                'created_at': challenge.created_at.isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting challenge info: {e}")
            return None
        finally:
            session.close()

# Global challenge manager instance
challenge_manager = ChallengeManager()

def get_challenge_manager() -> ChallengeManager:
    """Get the global challenge manager instance"""
    return challenge_manager