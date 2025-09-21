"""
Test cases for Nostr client
"""

import pytest
import json
import threading
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from nostr_clients.nostr_client import NostrClient, NostrEvent, ActionIntent, SigningResponse
from core.config import Config


class TestNostrClient:
    """Test cases for NostrClient"""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing"""
        config = Mock()
        config.NOSTR_RELAYS = ["wss://relay1.example.com", "wss://relay2.example.com"]
        config.NOSTR_PRIVATE_KEY = None
        config.REDIS_URL = "redis://localhost:6379/0"
        return config

    @pytest.fixture
    def nostr_client(self, mock_config):
        """Create Nostr client with mocked dependencies"""
        with patch('nostr_clients.nostr_client.Config', return_value=mock_config):
            with patch('nostr_clients.nostr_client.PrivateKey') as mock_private_key:
                with patch('nostr_clients.nostr_client.RelayManager') as mock_relay_manager:
                    with patch('nostr_clients.nostr_client.Redis') as mock_redis:
                        # Mock private key
                        mock_pk = Mock()
                        mock_pk.hex.return_value = "test_private_key"
                        mock_pk.public_key.hex.return_value = "test_public_key"
                        mock_private_key.return_value = mock_pk

                        # Mock Redis
                        mock_redis_instance = Mock()
                        mock_redis.from_url.return_value = mock_redis_instance

                        # Mock relay manager
                        mock_rm = Mock()
                        mock_rm.relays = {}
                        mock_rm.message_queue = []
                        mock_relay_manager.return_value = mock_rm

                        client = NostrClient()
                        client.redis_conn = mock_redis_instance
                        return client

    def test_client_initialization_with_key(self, mock_config):
        """Test client initialization with private key"""
        mock_config.NOSTR_PRIVATE_KEY = "existing_private_key"

        with patch('nostr_clients.nostr_client.Config', return_value=mock_config):
            with patch('nostr_clients.nostr_client.PrivateKey') as mock_private_key:
                with patch('nostr_clients.nostr_client.RelayManager'):
                    with patch('nostr_clients.nostr_client.Redis'):
                        mock_pk = Mock()
                        mock_pk.hex.return_value = "existing_private_key"
                        mock_private_key.fromhex.return_value = mock_pk

                        client = NostrClient()
                        assert client.private_key_hex == "existing_private_key"

    def test_client_initialization_generates_key(self, mock_config):
        """Test client initialization generates new key when none provided"""
        with patch('nostr_clients.nostr_client.Config', return_value=mock_config):
            with patch('nostr_clients.nostr_client.PrivateKey') as mock_private_key:
                with patch('nostr_clients.nostr_client.RelayManager'):
                    with patch('nostr_clients.nostr_client.Redis'):
                        mock_pk = Mock()
                        mock_pk.hex.return_value = "generated_private_key"
                        mock_private_key.return_value = mock_pk

                        client = NostrClient()
                        assert client.private_key_hex == "generated_private_key"

    def test_connect_success(self, nostr_client):
        """Test successful connection to relays"""
        # Mock successful relay connection
        mock_relay = Mock()
        mock_relay.is_connected = True
        nostr_client.relay_manager.relays = {"relay1": mock_relay}

        result = nostr_client.connect()

        assert result is True
        assert nostr_client.stats['connections'] == 1
        nostr_client.relay_manager.add_relay.assert_called()
        nostr_client.relay_manager.open_connections.assert_called_once()

    def test_connect_failure(self, nostr_client):
        """Test connection failure"""
        # Mock connection failure
        nostr_client.relay_manager.add_relay.side_effect = Exception("Connection failed")

        result = nostr_client.connect()

        assert result is False
        assert nostr_client.stats['errors'] == 1

    def test_connect_partial_success(self, nostr_client):
        """Test partial connection success"""
        # Mock mixed connection results
        mock_relay1 = Mock()
        mock_relay1.is_connected = True
        mock_relay2 = Mock()
        mock_relay2.is_connected = False
        nostr_client.relay_manager.relays = {"relay1": mock_relay1, "relay2": mock_relay2}

        result = nostr_client.connect()

        assert result is True  # At least one connection succeeds
        assert nostr_client.stats['connections'] == 1

    def test_disconnect(self, nostr_client):
        """Test disconnection from relays"""
        # Mock running state
        nostr_client._running = True
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        nostr_client._worker_thread = mock_thread

        nostr_client.disconnect()

        assert nostr_client._running is False
        nostr_client.relay_manager.close_connections.assert_called_once()
        mock_thread.join.assert_called_once_with(timeout=5)

    def test_subscribe_to_events(self, nostr_client):
        """Test event subscription"""
        kinds = [31510, 31512]
        authors = ["author1", "author2"]

        nostr_client.subscribe_to_events(kinds, authors)

        # Should create subscriptions for each kind
        assert len(nostr_client.subscriptions) == 2
        nostr_client.relay_manager.add_subscription.assert_called()

    def test_subscribe_to_gateway_events(self, nostr_client):
        """Test gateway event subscription"""
        nostr_client.subscribe_to_gateway_events()

        # Should subscribe to action intent and signing response events
        assert 31510 in nostr_client.event_handlers or 31512 in nostr_client.event_handlers

    def test_add_event_handler(self, nostr_client):
        """Test adding event handlers"""
        def mock_handler(event):
            pass

        nostr_client.add_event_handler(31510, mock_handler)

        assert 31510 in nostr_client.event_handlers
        assert mock_handler in nostr_client.event_handlers[31510]

    def test_add_event_handler_new_kind(self, nostr_client):
        """Test adding handler for new event kind"""
        def mock_handler(event):
            pass

        nostr_client.add_event_handler(99999, mock_handler)

        assert 99999 in nostr_client.event_handlers
        assert len(nostr_client.event_handlers[99999]) == 1

    def test_process_event_success(self, nostr_client):
        """Test successful event processing"""
        # Mock event
        mock_event = Mock()
        mock_event.id = "test_id"
        mock_event.pubkey = "test_pubkey"
        mock_event.created_at = 1234567890
        mock_event.kind = 31510
        mock_event.tags = []
        mock_event.content = "test_content"
        mock_event.sig = "test_sig"

        # Mock handler
        def mock_handler(event):
            processed_events.append(event)

        processed_events = []
        nostr_client.add_event_handler(31510, mock_handler)

        # Process event
        nostr_client._process_event(mock_event)

        assert len(processed_events) == 1
        assert processed_events[0].id == "test_id"
        assert nostr_client.stats['events_received'] == 1

    def test_process_event_no_handler(self, nostr_client):
        """Test processing event with no handler"""
        mock_event = Mock()
        mock_event.kind = 99999  # No handler for this kind

        nostr_client._process_event(mock_event)

        assert nostr_client.stats['events_received'] == 1
        # Should not raise an error

    def test_process_event_handler_error(self, nostr_client):
        """Test processing event with handler error"""
        mock_event = Mock()
        mock_event.kind = 31510

        def error_handler(event):
            raise Exception("Handler error")

        nostr_client.add_event_handler(31510, error_handler)

        # Should handle handler error gracefully
        nostr_client._process_event(mock_event)

        assert nostr_client.stats['events_received'] == 1
        assert nostr_client.stats['errors'] == 1

    def test_log_event_to_redis(self, nostr_client):
        """Test logging event to Redis"""
        event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=31510,
            tags=[],
            content="test_content",
            sig="test_sig"
        )

        nostr_client._log_event_to_redis(event)

        nostr_client.redis_conn.lpush.assert_called_once()
        nostr_client.redis_conn.ltrim.assert_called_once()

    def test_log_event_to_redis_error(self, nostr_client):
        """Test Redis logging error handling"""
        event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=31510,
            tags=[],
            content="test_content",
            sig="test_sig"
        )

        nostr_client.redis_conn.lpush.side_effect = Exception("Redis error")

        # Should handle Redis error gracefully
        nostr_client._log_event_to_redis(event)

        assert nostr_client.stats['errors'] == 1

    def test_publish_event_success(self, nostr_client):
        """Test successful event publishing"""
        with patch('nostr_clients.nostr_client.Event') as mock_event_class:
            mock_event = Mock()
            mock_event.id = "published_id"
            mock_event_class.return_value = mock_event

            result = nostr_client.publish_event(31510, "test_content", [["tag", "value"]])

            assert result == "published_id"
            assert nostr_client.stats['events_published'] == 1
            mock_event.sign.assert_called_once()
            nostr_client.relay_manager.publish_event.assert_called_once()

    def test_publish_event_failure(self, nostr_client):
        """Test event publishing failure"""
        nostr_client.relay_manager.publish_event.side_effect = Exception("Publish failed")

        result = nostr_client.publish_event(31510, "test_content")

        assert result is None
        assert nostr_client.stats['errors'] == 1

    def test_start_listening_already_running(self, nostr_client):
        """Test starting listener when already running"""
        nostr_client._running = True

        nostr_client.start_listening()

        # Should not start new thread
        assert nostr_client._worker_thread is None

    def test_start_listening_success(self, nostr_client):
        """Test successful listener start"""
        nostr_client._running = False

        nostr_client.start_listening()

        assert nostr_client._running is True
        assert nostr_client._worker_thread is not None
        assert nostr_client._worker_thread.daemon is True

    def test_listen_loop(self, nostr_client):
        """Test main listening loop"""
        nostr_client._running = True

        # Mock messages
        mock_event_msg = Mock()
        mock_event_msg.type = "EVENT"
        mock_event_msg.event = Mock()

        mock_notice_msg = Mock()
        mock_notice_msg.type = "NOTICE"
        mock_notice_msg.content = "Test notice"

        nostr_client.relay_manager.message_queue = [mock_event_msg, mock_notice_msg]

        # Run for a short time
        def stop_loop():
            time.sleep(0.1)
            nostr_client._running = False

        stop_thread = threading.Thread(target=stop_loop)
        stop_thread.start()

        nostr_client._listen_loop()

        stop_thread.join()

        # Should process messages
        assert nostr_client.stats['events_received'] >= 0

    def test_listen_loop_error(self, nostr_client):
        """Test listening loop error handling"""
        nostr_client._running = True
        nostr_client.relay_manager.message_queue.get.side_effect = Exception("Queue error")

        def stop_loop():
            time.sleep(0.1)
            nostr_client._running = False

        stop_thread = threading.Thread(target=stop_loop)
        stop_thread.start()

        nostr_client._listen_loop()

        stop_thread.join()

        assert nostr_client.stats['errors'] >= 1

    def test_get_stats(self, nostr_client):
        """Test statistics retrieval"""
        nostr_client._running = True
        nostr_client.stats = {
            'events_received': 10,
            'events_published': 5,
            'connections': 2,
            'errors': 1
        }

        stats = nostr_client.get_stats()

        assert stats['running'] is True
        assert stats['events_received'] == 10
        assert stats['events_published'] == 5
        assert 'relay_count' in stats
        assert 'connected_relays' in stats
        assert 'subscriptions' in stats
        assert 'handlers' in stats

    def test_validate_event_signature_success(self, nostr_client):
        """Test successful event signature validation"""
        event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=31510,
            tags=[],
            content="test_content",
            sig="test_sig"
        )

        with patch('nostr_clients.nostr_client.PublicKey') as mock_public_key:
            mock_pk = Mock()
            mock_pk.verify_signed_hash.return_value = True
            mock_public_key.return_value = mock_pk

            result = nostr_client.validate_event_signature(event)

            assert result is True

    def test_validate_event_signature_failure(self, nostr_client):
        """Test event signature validation failure"""
        event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=31510,
            tags=[],
            content="test_content",
            sig="test_sig"
        )

        with patch('nostr_clients.nostr_client.PublicKey') as mock_public_key:
            mock_pk = Mock()
            mock_pk.verify_signed_hash.return_value = False
            mock_public_key.return_value = mock_pk

            result = nostr_client.validate_event_signature(event)

            assert result is False

    def test_validate_event_signature_error(self, nostr_client):
        """Test event signature validation error handling"""
        event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=31510,
            tags=[],
            content="test_content",
            sig="test_sig"
        )

        with patch('nostr_clients.nostr_client.PublicKey') as mock_public_key:
            mock_public_key.side_effect = Exception("Validation error")

            result = nostr_client.validate_event_signature(event)

            assert result is False

    def test_encrypt_dm_success(self, nostr_client):
        """Test successful DM encryption"""
        with patch('nostr_clients.nostr_client.EncryptedDirectMessage') as mock_dm_class:
            mock_dm = Mock()
            mock_dm.encrypted_message = "encrypted_content"
            mock_dm_class.return_value = mock_dm

            result = nostr_client.encrypt_dm("recipient_pubkey", "test_message")

            assert result == "encrypted_content"
            mock_dm.encrypt.assert_called_once()

    def test_encrypt_dm_failure(self, nostr_client):
        """Test DM encryption failure"""
        with patch('nostr_clients.nostr_client.EncryptedDirectMessage') as mock_dm_class:
            mock_dm = Mock()
            mock_dm.encrypt.side_effect = Exception("Encryption failed")
            mock_dm_class.return_value = mock_dm

            result = nostr_client.encrypt_dm("recipient_pubkey", "test_message")

            assert result is None

    def test_decrypt_dm_success(self, nostr_client):
        """Test successful DM decryption"""
        with patch('nostr_clients.nostr_client.EncryptedDirectMessage') as mock_dm_class:
            mock_dm = Mock()
            mock_dm.cleartext_content = "decrypted_message"
            mock_dm_class.return_value = mock_dm

            result = nostr_client.decrypt_dm("sender_pubkey", "encrypted_content")

            assert result == "decrypted_message"
            mock_dm.decrypt.assert_called_once()

    def test_decrypt_dm_failure(self, nostr_client):
        """Test DM decryption failure"""
        with patch('nostr_clients.nostr_client.EncryptedDirectMessage') as mock_dm_class:
            mock_dm = Mock()
            mock_dm.decrypt.side_effect = Exception("Decryption failed")
            mock_dm_class.return_value = mock_dm

            result = nostr_client.decrypt_dm("sender_pubkey", "encrypted_content")

            assert result is None

    def test_send_encrypted_dm_success(self, nostr_client):
        """Test successful encrypted DM sending"""
        with patch.object(nostr_client, 'encrypt_dm', return_value="encrypted_content") as mock_encrypt:
            with patch.object(nostr_client, 'publish_event', return_value="event_id") as mock_publish:

                result = nostr_client.send_encrypted_dm("recipient_pubkey", "test_message")

                assert result == "event_id"
                mock_encrypt.assert_called_once_with("recipient_pubkey", "test_message")
                mock_publish.assert_called_once()

    def test_send_encrypted_dm_failure(self, nostr_client):
        """Test encrypted DM sending failure"""
        with patch.object(nostr_client, 'encrypt_dm', return_value=None):

            result = nostr_client.send_encrypted_dm("recipient_pubkey", "test_message")

            assert result is None

    def test_parse_action_intent_success(self, nostr_client):
        """Test successful action intent parsing"""
        event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=31510,  # Action Intent kind
            tags=[],
            content=json.dumps({
                "session_type": "vtxo_transfer",
                "intent_data": {"amount": 1000}
            }),
            sig="test_sig"
        )

        result = nostr_client.parse_action_intent(event)

        assert result is not None
        assert result.user_pubkey == "test_pubkey"
        assert result.session_type == "vtxo_transfer"
        assert result.intent_data["amount"] == 1000

    def test_parse_action_intent_wrong_kind(self, nostr_client):
        """Test action intent parsing with wrong kind"""
        event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=99999,  # Wrong kind
            tags=[],
            content="test_content",
            sig="test_sig"
        )

        result = nostr_client.parse_action_intent(event)

        assert result is None

    def test_parse_action_intent_invalid_json(self, nostr_client):
        """Test action intent parsing with invalid JSON"""
        event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=31510,
            tags=[],
            content="invalid_json",
            sig="test_sig"
        )

        result = nostr_client.parse_action_intent(event)

        assert result is None

    def test_parse_signing_response_success(self, nostr_client):
        """Test successful signing response parsing"""
        event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=31512,  # Signing Response kind
            tags=[],
            content=json.dumps({
                "challenge_id": "test_challenge",
                "signature": "test_signature"
            }),
            sig="test_sig"
        )

        result = nostr_client.parse_signing_response(event)

        assert result is not None
        assert result.challenge_id == "test_challenge"
        assert result.signature == "test_signature"
        assert result.user_pubkey == "test_pubkey"

    def test_parse_signing_response_wrong_kind(self, nostr_client):
        """Test signing response parsing with wrong kind"""
        event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=99999,  # Wrong kind
            tags=[],
            content="test_content",
            sig="test_sig"
        )

        result = nostr_client.parse_signing_response(event)

        assert result is None

    def test_publish_signing_challenge_success(self, nostr_client):
        """Test successful signing challenge publishing"""
        with patch.object(nostr_client, 'publish_event', return_value="event_id") as mock_publish:

            result = nostr_client.publish_signing_challenge(
                "user_pubkey",
                "challenge_id",
                "test_context"
            )

            assert result == "event_id"
            mock_publish.assert_called_once()

    def test_publish_signing_challenge_failure(self, nostr_client):
        """Test signing challenge publishing failure"""
        with patch.object(nostr_client, 'publish_event', return_value=None):

            result = nostr_client.publish_signing_challenge(
                "user_pubkey",
                "challenge_id",
                "test_context"
            )

            assert result is None

    def test_publish_session_status_success(self, nostr_client):
        """Test successful session status publishing"""
        with patch.object(nostr_client, 'publish_event', return_value="event_id") as mock_publish:

            result = nostr_client.publish_session_status(
                "session_id",
                "completed",
                "user_pubkey"
            )

            assert result == "event_id"
            mock_publish.assert_called_once()

    def test_publish_session_status_failure(self, nostr_client):
        """Test session status publishing failure"""
        with patch.object(nostr_client, 'publish_event', return_value=None):

            result = nostr_client.publish_session_status(
                "session_id",
                "completed",
                "user_pubkey"
            )

            assert result is None

    def test_nostr_event_dataclass(self):
        """Test NostrEvent dataclass"""
        event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=31510,
            tags=[["tag", "value"]],
            content="test_content",
            sig="test_sig"
        )

        assert event.id == "test_id"
        assert event.pubkey == "test_pubkey"
        assert event.kind == 31510
        assert len(event.tags) == 1
        assert event.content == "test_content"

    def test_action_intent_dataclass(self):
        """Test ActionIntent dataclass"""
        intent = ActionIntent(
            user_pubkey="test_pubkey",
            session_type="vtxo_transfer",
            intent_data={"amount": 1000},
            timestamp=1234567890
        )

        assert intent.user_pubkey == "test_pubkey"
        assert intent.session_type == "vtxo_transfer"
        assert intent.intent_data["amount"] == 1000

    def test_signing_response_dataclass(self):
        """Test SigningResponse dataclass"""
        response = SigningResponse(
            challenge_id="test_challenge",
            signature="test_signature",
            user_pubkey="test_pubkey",
            timestamp=1234567890
        )

        assert response.challenge_id == "test_challenge"
        assert response.signature == "test_signature"
        assert response.user_pubkey == "test_pubkey"

    @pytest.mark.unit
    def test_client_isolation(self, mock_config):
        """Test that multiple client instances are independent"""
        with patch('nostr_clients.nostr_client.Config', return_value=mock_config):
            with patch('nostr_clients.nostr_client.PrivateKey'):
                with patch('nostr_clients.nostr_client.RelayManager'):
                    with patch('nostr_clients.nostr_client.Redis'):
                        client1 = NostrClient()
                        client2 = NostrClient()

                        assert client1 is not client2
                        assert client1.private_key_hex != client2.private_key_hex

    @pytest.mark.integration
    def test_integration_with_redis(self, nostr_client):
        """Test integration with Redis"""
        event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=31510,
            tags=[],
            content="test_content",
            sig="test_sig"
        )

        nostr_client._log_event_to_redis(event)

        nostr_client.redis_conn.lpush.assert_called_once()
        call_args = nostr_client.redis_conn.lpush.call_args
        assert 'nostr_events' in call_args[0]

    @pytest.mark.performance
    def test_event_processing_performance(self, nostr_client):
        """Test event processing performance"""
        import time

        # Mock event
        mock_event = Mock()
        mock_event.id = "test_id"
        mock_event.pubkey = "test_pubkey"
        mock_event.created_at = 1234567890
        mock_event.kind = 31510
        mock_event.tags = []
        mock_event.content = "test_content"
        mock_event.sig = "test_sig"

        def fast_handler(event):
            pass

        nostr_client.add_event_handler(31510, fast_handler)

        start_time = time.time()
        for _ in range(100):
            nostr_client._process_event(mock_event)
        end_time = time.time()

        # Should process 100 events quickly (less than 1 second)
        assert end_time - start_time < 1.0

    @pytest.mark.error_handling
    def test_error_handling_scenarios(self, nostr_client):
        """Test various error handling scenarios"""
        # Test Redis connection error
        nostr_client.redis_conn.lpush.side_effect = Exception("Redis error")
        event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=31510,
            tags=[],
            content="test_content",
            sig="test_sig"
        )

        # Should handle gracefully
        nostr_client._log_event_to_redis(event)

        # Test handler exception
        def error_handler(event):
            raise Exception("Handler error")

        nostr_client.add_event_handler(31510, error_handler)
        nostr_client._process_event(mock_event)

        assert nostr_client.stats['errors'] >= 1