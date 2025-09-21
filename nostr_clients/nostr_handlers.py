import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from .nostr_client import NostrClient, NostrEvent, ActionIntent, SigningResponse, get_nostr_client
from core.models import get_session, SigningSession, SigningChallenge, AssetBalance
from core.config import Config
from redis import Redis

logger = logging.getLogger(__name__)

class NostrEventHandler:
    def __init__(self, nostr_client: NostrClient):
        self.client = nostr_client
        self.redis_conn = Redis.from_url(Config.REDIS_URL)

        # Register event handlers
        self.client.add_event_handler(31510, self.handle_action_intent)
        self.client.add_event_handler(31512, self.handle_signing_response)

        logger.info("Registered Nostr event handlers")

    def handle_action_intent(self, event: NostrEvent):
        """Handle Action Intent (kind: 31510) events"""
        try:
            logger.info(f"Processing Action Intent from {event.pubkey}")

            # Validate event signature
            if not self.client.validate_event_signature(event):
                logger.warning(f"Invalid signature for Action Intent event {event.id}")
                return

            # Parse action intent
            action_intent = self.client.parse_action_intent(event)
            if not action_intent:
                logger.error(f"Failed to parse Action Intent from event {event.id}")
                return

            # Validate action intent
            if not self._validate_action_intent(action_intent):
                logger.warning(f"Invalid Action Intent from {action_intent.user_pubkey}")
                return

            # Create signing session
            session_id = str(uuid.uuid4())
            session = self._create_signing_session(session_id, action_intent)

            if not session:
                logger.error(f"Failed to create signing session for {action_intent.user_pubkey}")
                return

            # Generate signing challenge
            challenge = self._generate_signing_challenge(session_id, action_intent)

            if not challenge:
                logger.error(f"Failed to generate challenge for session {session_id}")
                return

            # Publish challenge via Nostr
            self.client.publish_signing_challenge(
                user_pubkey=action_intent.user_pubkey,
                challenge_id=challenge.challenge_id,
                context=challenge.context
            )

            # Publish event to Redis for processing
            self._publish_to_redis('action_intent', {
                'event_id': event.id,
                'session_id': session_id,
                'user_pubkey': action_intent.user_pubkey,
                'session_type': action_intent.session_type,
                'intent_data': action_intent.intent_data,
                'timestamp': datetime.utcnow().isoformat()
            })

            logger.info(f"Successfully processed Action Intent, created session {session_id}")

        except Exception as e:
            logger.error(f"Error handling Action Intent: {e}")

    def handle_signing_response(self, event: NostrEvent):
        """Handle Signing Response (kind: 31512) events"""
        try:
            logger.info(f"Processing Signing Response from {event.pubkey}")

            # Validate event signature
            if not self.client.validate_event_signature(event):
                logger.warning(f"Invalid signature for Signing Response event {event.id}")
                return

            # Parse signing response
            signing_response = self.client.parse_signing_response(event)
            if not signing_response:
                logger.error(f"Failed to parse Signing Response from event {event.id}")
                return

            # Validate signing response
            if not self._validate_signing_response(signing_response):
                logger.warning(f"Invalid Signing Response from {signing_response.user_pubkey}")
                return

            # Process signing response
            session = self._process_signing_response(signing_response)

            if not session:
                logger.error(f"Failed to process signing response for challenge {signing_response.challenge_id}")
                return

            # Publish session status update
            self.client.publish_session_status(
                session_id=session.session_id,
                status='signing',
                user_pubkey=signing_response.user_pubkey
            )

            # Publish event to Redis for processing
            self._publish_to_redis('signing_response', {
                'event_id': event.id,
                'session_id': session.session_id,
                'challenge_id': signing_response.challenge_id,
                'user_pubkey': signing_response.user_pubkey,
                'signature': signing_response.signature,
                'timestamp': datetime.utcnow().isoformat()
            })

            logger.info(f"Successfully processed Signing Response for session {session.session_id}")

        except Exception as e:
            logger.error(f"Error handling Signing Response: {e}")

    def _validate_action_intent(self, action_intent: ActionIntent) -> bool:
        """Validate action intent"""
        # Check required fields
        if not action_intent.user_pubkey or not action_intent.session_type:
            return False

        # Validate session type
        valid_session_types = ['p2p_transfer', 'lightning_lift', 'lightning_land']
        if action_intent.session_type not in valid_session_types:
            logger.warning(f"Invalid session type: {action_intent.session_type}")
            return False

        # Validate intent data based on session type
        if action_intent.session_type == 'p2p_transfer':
            required_fields = ['recipient_pubkey', 'asset_id', 'amount']
            if not all(field in action_intent.intent_data for field in required_fields):
                return False

        elif action_intent.session_type in ['lightning_lift', 'lightning_land']:
            required_fields = ['asset_id', 'amount', 'invoice']
            if not all(field in action_intent.intent_data for field in required_fields):
                return False

        # Check if user has sufficient balance (for asset transfers)
        if action_intent.session_type in ['p2p_transfer', 'lightning_land']:
            asset_id = action_intent.intent_data.get('asset_id')
            amount = action_intent.intent_data.get('amount')

            if not self._check_user_balance(action_intent.user_pubkey, asset_id, amount):
                logger.warning(f"Insufficient balance for user {action_intent.user_pubkey}")
                return False

        return True

    def _validate_signing_response(self, signing_response: SigningResponse) -> bool:
        """Validate signing response"""
        if not signing_response.challenge_id or not signing_response.signature:
            return False

        # Check if challenge exists and is valid
        session = get_session()
        try:
            challenge = session.query(SigningChallenge).filter_by(
                challenge_id=signing_response.challenge_id
            ).first()

            if not challenge:
                logger.warning(f"Challenge {signing_response.challenge_id} not found")
                return False

            # Check if challenge is expired
            if datetime.utcnow() > challenge.expires_at:
                logger.warning(f"Challenge {signing_response.challenge_id} expired")
                return False

            # Check if challenge is already used
            if challenge.is_used:
                logger.warning(f"Challenge {signing_response.challenge_id} already used")
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating signing response: {e}")
            return False
        finally:
            session.close()

    def _create_signing_session(self, session_id: str, action_intent: ActionIntent) -> Optional[SigningSession]:
        """Create a new signing session"""
        session = get_session()
        try:
            # Calculate expiration time
            expires_at = datetime.utcnow() + timedelta(minutes=Config.SESSION_TIMEOUT_MINUTES)

            # Create human-readable context
            context = self._generate_context(action_intent)

            # Create session
            signing_session = SigningSession(
                session_id=session_id,
                user_pubkey=action_intent.user_pubkey,
                session_type=action_intent.session_type,
                status='challenge_sent',
                intent_data=action_intent.intent_data,
                context=context,
                expires_at=expires_at
            )

            session.add(signing_session)
            session.commit()

            return signing_session

        except Exception as e:
            logger.error(f"Error creating signing session: {e}")
            session.rollback()
            return None
        finally:
            session.close()

    def _generate_signing_challenge(self, session_id: str, action_intent: ActionIntent) -> Optional[SigningChallenge]:
        """Generate a signing challenge"""
        session = get_session()
        try:
            # Get session
            signing_session = session.query(SigningSession).filter_by(
                session_id=session_id
            ).first()

            if not signing_session:
                logger.error(f"Session {session_id} not found")
                return None

            # Generate challenge data
            challenge_data = self._generate_challenge_data(action_intent)
            if not challenge_data:
                return None

            # Create challenge
            challenge = SigningChallenge(
                challenge_id=str(uuid.uuid4()),
                session_id=session_id,
                challenge_data=challenge_data,
                context=signing_session.context,
                expires_at=signing_session.expires_at
            )

            session.add(challenge)
            session.commit()

            # Update session with challenge ID
            signing_session.challenge_id = challenge.challenge_id
            session.commit()

            return challenge

        except Exception as e:
            logger.error(f"Error generating signing challenge: {e}")
            session.rollback()
            return None
        finally:
            session.close()

    def _generate_challenge_data(self, action_intent: ActionIntent) -> Optional[bytes]:
        """Generate challenge data for signing"""
        try:
            # Create deterministic challenge based on action intent
            challenge_dict = {
                'user_pubkey': action_intent.user_pubkey,
                'session_type': action_intent.session_type,
                'intent_data': action_intent.intent_data,
                'timestamp': int(action_intent.timestamp),
                'gateway_pubkey': self.client.public_key.hex()
            }

            challenge_json = json.dumps(challenge_dict, sort_keys=True)
            return challenge_json.encode('utf-8')

        except Exception as e:
            logger.error(f"Error generating challenge data: {e}")
            return None

    def _generate_context(self, action_intent: ActionIntent) -> str:
        """Generate human-readable context for the signing challenge"""
        session_type = action_intent.session_type

        if session_type == 'p2p_transfer':
            recipient = action_intent.intent_data.get('recipient_pubkey', 'unknown')[:8] + '...'
            asset_id = action_intent.intent_data.get('asset_id', 'unknown')
            amount = action_intent.intent_data.get('amount', 0)

            return f"Transfer {amount} units of asset {asset_id} to {recipient}"

        elif session_type == 'lightning_lift':
            asset_id = action_intent.intent_data.get('asset_id', 'unknown')
            amount = action_intent.intent_data.get('amount', 0)

            return f"Lightning lift: Convert {amount} units of asset {asset_id} to Lightning"

        elif session_type == 'lightning_land':
            asset_id = action_intent.intent_data.get('asset_id', 'unknown')
            amount = action_intent.intent_data.get('amount', 0)

            return f"Lightning land: Convert Lightning to {amount} units of asset {asset_id}"

        else:
            return f"Unknown action: {session_type}"

    def _check_user_balance(self, user_pubkey: str, asset_id: str, amount: int) -> bool:
        """Check if user has sufficient balance"""
        session = get_session()
        try:
            balance = session.query(AssetBalance).filter_by(
                user_pubkey=user_pubkey,
                asset_id=asset_id
            ).first()

            if not balance:
                return False

            return balance.balance >= amount

        except Exception as e:
            logger.error(f"Error checking user balance: {e}")
            return False
        finally:
            session.close()

    def _process_signing_response(self, signing_response: SigningResponse) -> Optional[SigningSession]:
        """Process a signing response"""
        session = get_session()
        try:
            # Get challenge
            challenge = session.query(SigningChallenge).filter_by(
                challenge_id=signing_response.challenge_id
            ).first()

            if not challenge:
                return None

            # Get signing session
            signing_session = session.query(SigningSession).filter_by(
                session_id=challenge.session_id
            ).first()

            if not signing_session:
                return None

            # Verify signature matches challenge
            # Note: In a real implementation, you would verify the signature here
            # For now, we'll mark it as used

            # Mark challenge as used
            challenge.is_used = True
            challenge.signature = signing_response.signature.encode('utf-8')

            # Update session status
            signing_session.status = 'signing'

            session.commit()

            return signing_session

        except Exception as e:
            logger.error(f"Error processing signing response: {e}")
            session.rollback()
            return None
        finally:
            session.close()

    def _publish_to_redis(self, channel: str, data: Dict[str, Any]):
        """Publish event to Redis for processing"""
        try:
            self.redis_conn.publish(channel, json.dumps(data))

            # Also store in a list for processing
            self.redis_conn.lpush(f'{channel}_queue', json.dumps(data))
            self.redis_conn.ltrim(f'{channel}_queue', 0, 9999)  # Keep last 10,000 items

        except Exception as e:
            logger.error(f"Error publishing to Redis: {e}")

# Global event handler
_event_handler = None

def get_event_handler() -> NostrEventHandler:
    """Get the global event handler instance"""
    global _event_handler
    if _event_handler is None:
        nostr_client = get_nostr_client()
        _event_handler = NostrEventHandler(nostr_client)
    return _event_handler

def initialize_event_handler():
    """Initialize the global event handler"""
    handler = get_event_handler()
    logger.info("Nostr event handler initialized")
    return handler