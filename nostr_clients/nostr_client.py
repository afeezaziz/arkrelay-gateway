import asyncio
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
import base64
import hashlib

import pynostr
from pynostr.event import Event
from pynostr.relay_manager import RelayManager
from pynostr.key import PrivateKey, PublicKey
from pynostr.encrypted_dm import EncryptedDirectMessage

from core.config import Config
from core.models import get_session, SigningSession, SigningChallenge
from redis import Redis

logger = logging.getLogger(__name__)

@dataclass
class NostrEvent:
    id: str
    pubkey: str
    created_at: int
    kind: int
    tags: List[List[str]]
    content: str
    sig: str

@dataclass
class ActionIntent:
    user_pubkey: str
    session_type: str
    intent_data: Dict[str, Any]
    timestamp: int

@dataclass
class SigningResponse:
    challenge_id: str
    signature: str
    user_pubkey: str
    timestamp: int

class NostrClient:
    def __init__(self, relays: Optional[List[str]] = None, private_key: Optional[str] = None):
        self.relays = relays or Config.NOSTR_RELAYS
        self.private_key_hex = private_key or Config.NOSTR_PRIVATE_KEY

        # Initialize Nostr identity
        if self.private_key_hex:
            self.private_key = PrivateKey(bytes.fromhex(self.private_key_hex))
            self.public_key = self.private_key.public_key
        else:
            # Generate new key pair if none provided
            self.private_key = PrivateKey()
            self.public_key = self.private_key.public_key
            self.private_key_hex = self.private_key.hex()
            logger.warning(f"Generated new Nostr identity. Save this private key: {self.private_key_hex}")

        self.relay_manager = RelayManager()
        self.redis_conn = Redis.from_url(Config.REDIS_URL)

        # Event handlers
        self.event_handlers = {
            31510: [],  # Action Intent
            31512: [],  # Signing Response
        }

        # Subscription filters
        self.subscriptions = {}

        # Running state
        self._running = False
        self._worker_thread = None

        # Statistics
        self.stats = {
            'events_received': 0,
            'events_published': 0,
            'connections': 0,
            'errors': 0
        }

        logger.info(f"Initialized Nostr client with pubkey: {self.public_key.hex()}")
        logger.info(f"Relays: {self.relays}")

    def connect(self) -> bool:
        """Connect to all configured relays"""
        try:
            # Add relays to manager
            for relay_url in self.relays:
                self.relay_manager.add_relay(relay_url)

            # Connect to relays
            self.relay_manager.open_connections()

            # Wait for connections
            time.sleep(2)

            # Check connection status
            connected_relays = [r for r in self.relay_manager.relays.values() if r.is_connected]
            self.stats['connections'] = len(connected_relays)

            logger.info(f"Connected to {len(connected_relays)}/{len(self.relays)} relays")
            return len(connected_relays) > 0

        except Exception as e:
            logger.error(f"Failed to connect to relays: {e}")
            self.stats['errors'] += 1
            return False

    def disconnect(self):
        """Disconnect from all relays"""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)

        self.relay_manager.close_connections()
        logger.info("Disconnected from all relays")

    def subscribe_to_events(self, kinds: List[int], authors: Optional[List[str]] = None):
        """Subscribe to specific event kinds from specific authors"""
        for kind in kinds:
            filter_dict = {"kinds": [kind]}
            if authors:
                filter_dict["authors"] = authors

            subscription_id = f"sub_{kind}_{int(time.time())}"
            self.relay_manager.add_subscription(subscription_id, filter_dict)
            self.subscriptions[subscription_id] = filter_dict

            logger.info(f"Subscribed to kind {kind} events with filter: {filter_dict}")

    def subscribe_to_gateway_events(self):
        """Subscribe to events directed at this gateway"""
        self.subscribe_to_events(
            kinds=[31510, 31512],  # Action Intent and Signing Response
            authors=None  # Listen from all authors
        )

    def add_event_handler(self, kind: int, handler: Callable[[NostrEvent], None]):
        """Add an event handler for a specific kind"""
        if kind not in self.event_handlers:
            self.event_handlers[kind] = []
        self.event_handlers[kind].append(handler)
        logger.info(f"Added handler for kind {kind} events")

    def _process_event(self, event: Event):
        """Process a received Nostr event"""
        try:
            nostr_event = NostrEvent(
                id=event.id,
                pubkey=event.pubkey,
                created_at=event.created_at,
                kind=event.kind,
                tags=event.tags or [],
                content=event.content,
                sig=event.sig
            )

            # Update statistics
            self.stats['events_received'] += 1

            # Log event for monitoring
            self._log_event_to_redis(nostr_event)

            # Call appropriate handlers
            if nostr_event.kind in self.event_handlers:
                for handler in self.event_handlers[nostr_event.kind]:
                    try:
                        handler(nostr_event)
                    except Exception as e:
                        logger.error(f"Error in event handler for kind {nostr_event.kind}: {e}")
                        self.stats['errors'] += 1
            else:
                logger.warning(f"No handler for event kind {nostr_event.kind}")

        except Exception as e:
            logger.error(f"Error processing event: {e}")
            self.stats['errors'] += 1

    def _log_event_to_redis(self, event: NostrEvent):
        """Log event to Redis for monitoring"""
        try:
            event_data = {
                'id': event.id,
                'pubkey': event.pubkey,
                'kind': event.kind,
                'created_at': event.created_at,
                'content_length': len(event.content),
                'timestamp': datetime.utcnow().isoformat()
            }

            self.redis_conn.lpush('nostr_events', json.dumps(event_data))
            self.redis_conn.ltrim('nostr_events', 0, 999)  # Keep last 1000 events

        except Exception as e:
            logger.error(f"Error logging event to Redis: {e}")

    def publish_event(self, kind: int, content: str, tags: Optional[List[List[str]]] = None) -> Optional[str]:
        """Publish a Nostr event"""
        try:
            event = Event(
                kind=kind,
                content=content,
                tags=tags or [],
                public_key=self.public_key.hex()
            )

            # Sign the event
            event.sign(self.private_key.hex())

            # Publish to relays
            self.relay_manager.publish_event(event)

            # Update statistics
            self.stats['events_published'] += 1

            logger.info(f"Published event kind {kind} with ID: {event.id}")
            return event.id

        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
            self.stats['errors'] += 1
            return None

    def start_listening(self):
        """Start listening for events in a background thread"""
        if self._running:
            logger.warning("Nostr client is already running")
            return

        self._running = True
        self._worker_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._worker_thread.start()
        logger.info("Started Nostr event listener")

    def _listen_loop(self):
        """Main listening loop"""
        logger.info("Starting Nostr event listening loop")

        while self._running:
            try:
                # Process any messages
                while self.relay_manager.message_queue:
                    message = self.relay_manager.message_queue.get()
                    if message.type == "EVENT":
                        self._process_event(message.event)
                    elif message.type == "NOTICE":
                        logger.info(f"Relay notice: {message.content}")

                time.sleep(0.1)  # Small sleep to prevent CPU overuse

            except Exception as e:
                logger.error(f"Error in listening loop: {e}")
                self.stats['errors'] += 1
                time.sleep(1)  # Wait before retrying

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        return {
            **self.stats,
            'running': self._running,
            'relay_count': len(self.relays),
            'connected_relays': len([r for r in self.relay_manager.relays.values() if r.is_connected]),
            'subscriptions': len(self.subscriptions),
            'handlers': {k: len(v) for k, v in self.event_handlers.items()}
        }

    def validate_event_signature(self, event: NostrEvent) -> bool:
        """Validate Nostr event signature"""
        try:
            # Create event hash
            event_data = [
                0,
                event.pubkey,
                event.created_at,
                event.kind,
                event.tags,
                event.content
            ]

            event_str = json.dumps(event_data, separators=(',', ':'), ensure_ascii=False)
            event_hash = hashlib.sha256(event_str.encode()).digest()

            # Verify signature
            public_key = PublicKey(event.pubkey)
            return public_key.verify_signed_hash(event.sig, event_hash)

        except Exception as e:
            logger.error(f"Error validating event signature: {e}")
            return False

    def encrypt_dm(self, recipient_pubkey: str, message: str) -> Optional[str]:
        """Encrypt a direct message for a recipient"""
        try:
            dm = EncryptedDirectMessage()
            dm.encrypt(
                private_key_hex=self.private_key.hex(),
                cleartext_content=message,
                recipient_pubkey=recipient_pubkey
            )
            return dm.encrypted_message

        except Exception as e:
            logger.error(f"Error encrypting DM: {e}")
            return None

    def decrypt_dm(self, sender_pubkey: str, encrypted_content: str) -> Optional[str]:
        """Decrypt a direct message from a sender"""
        try:
            dm = EncryptedDirectMessage()
            dm.decrypt(
                private_key_hex=self.private_key.hex(),
                encrypted_message=encrypted_content,
                public_key_hex=sender_pubkey
            )
            return dm.cleartext_content

        except Exception as e:
            logger.error(f"Error decrypting DM: {e}")
            return None

    def send_encrypted_dm(self, recipient_pubkey: str, message: str) -> Optional[str]:
        """Send an encrypted direct message"""
        try:
            encrypted_content = self.encrypt_dm(recipient_pubkey, message)
            if not encrypted_content:
                return None

            return self.publish_event(
                kind=4,  # Encrypted DM kind
                content=encrypted_content,
                tags=[["p", recipient_pubkey]]
            )

        except Exception as e:
            logger.error(f"Error sending encrypted DM: {e}")
            return None

    def parse_action_intent(self, event: NostrEvent) -> Optional[ActionIntent]:
        """Parse action intent from event content"""
        try:
            if event.kind != 31510:
                return None

            content_data = json.loads(event.content)

            return ActionIntent(
                user_pubkey=event.pubkey,
                session_type=content_data.get('session_type'),
                intent_data=content_data.get('intent_data', {}),
                timestamp=event.created_at
            )

        except Exception as e:
            logger.error(f"Error parsing action intent: {e}")
            return None

    def parse_signing_response(self, event: NostrEvent) -> Optional[SigningResponse]:
        """Parse signing response from event content"""
        try:
            if event.kind != 31512:
                return None

            content_data = json.loads(event.content)

            return SigningResponse(
                challenge_id=content_data.get('challenge_id'),
                signature=content_data.get('signature'),
                user_pubkey=event.pubkey,
                timestamp=event.created_at
            )

        except Exception as e:
            logger.error(f"Error parsing signing response: {e}")
            return None

    def publish_signing_challenge(self, user_pubkey: str, challenge_id: str, context: str) -> Optional[str]:
        """Publish a signing challenge"""
        try:
            challenge_data = {
                'challenge_id': challenge_id,
                'context': context,
                'gateway_pubkey': self.public_key.hex(),
                'timestamp': int(time.time())
            }

            return self.publish_event(
                kind=31111,  # Signing Challenge kind
                content=json.dumps(challenge_data),
                tags=[["p", user_pubkey]]
            )

        except Exception as e:
            logger.error(f"Error publishing signing challenge: {e}")
            return None

    def publish_session_status(self, session_id: str, status: str, user_pubkey: str) -> Optional[str]:
        """Publish session status update"""
        try:
            status_data = {
                'session_id': session_id,
                'status': status,
                'gateway_pubkey': self.public_key.hex(),
                'timestamp': int(time.time())
            }

            return self.publish_event(
                kind=31113,  # Session Status kind
                content=json.dumps(status_data),
                tags=[["p", user_pubkey]]
            )

        except Exception as e:
            logger.error(f"Error publishing session status: {e}")
            return None

# Global Nostr client instance
_nostr_client = None

def get_nostr_client() -> NostrClient:
    """Get the global Nostr client instance"""
    global _nostr_client
    if _nostr_client is None:
        _nostr_client = NostrClient()
    return _nostr_client

def initialize_nostr_client():
    """Initialize the global Nostr client and start listening"""
    client = get_nostr_client()

    # Connect to relays
    if not client.connect():
        logger.error("Failed to connect to Nostr relays")
        return False

    # Subscribe to gateway events
    client.subscribe_to_gateway_events()

    # Start listening
    client.start_listening()

    logger.info("Nostr client initialized successfully")
    return True

def shutdown_nostr_client():
    """Shutdown the global Nostr client"""
    global _nostr_client
    if _nostr_client:
        _nostr_client.disconnect()
        _nostr_client = None
        logger.info("Nostr client shutdown")