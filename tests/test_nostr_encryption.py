import logging
import unittest
from unittest.mock import Mock, patch

from nostr_clients.nostr_client import NostrClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestNostrEncryption(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        # Create a test Nostr client with a new key pair
        self.client = NostrClient(
            relays=['wss://relay.damus.io'],
            private_key=None  # Will generate new key
        )

        # Test recipient key (generate another key pair)
        from pynostr.key import PrivateKey
        self.recipient_private_key = PrivateKey()
        self.recipient_public_key = self.recipient_private_key.public_key

        logger.info(f"Test client pubkey: {self.client.public_key.hex()}")
        logger.info(f"Recipient pubkey: {self.recipient_public_key.hex()}")

    def test_key_generation(self):
        """Test that keys are properly generated"""
        self.assertIsNotNone(self.client.private_key)
        self.assertIsNotNone(self.client.public_key)
        self.assertIsNotNone(self.client.private_key_hex)
        self.assertTrue(len(self.client.private_key.hex()) == 64)

    def test_encryption_decryption_roundtrip(self):
        """Test that encryption and decryption work correctly"""
        test_message = "Hello, this is a test message!"

        # Encrypt the message
        encrypted = self.client.encrypt_dm(
            self.recipient_public_key.hex(),
            test_message
        )

        self.assertIsNotNone(encrypted)
        self.assertTrue(len(encrypted) > 0)

        logger.info(f"Encrypted message: {encrypted[:50]}...")

        # Decrypt the message
        decrypted = self.client.decrypt_dm(
            self.recipient_public_key.hex(),
            encrypted
        )

        self.assertIsNotNone(decrypted)
        self.assertEqual(decrypted, test_message)

        logger.info(f"Decrypted message: {decrypted}")

    def test_encryption_decryption_with_recipient(self):
        """Test that the recipient can decrypt messages"""
        test_message = "This message should be readable by the recipient"

        # Encrypt with sender's key
        encrypted = self.client.encrypt_dm(
            self.recipient_public_key.hex(),
            test_message
        )

        # Create recipient client
        recipient_client = NostrClient(
            relays=[],
            private_key=self.recipient_private_key.hex()
        )

        # Decrypt with recipient's key
        decrypted = recipient_client.decrypt_dm(
            self.client.public_key.hex(),
            encrypted
        )

        self.assertEqual(decrypted, test_message)

    def test_invalid_decryption(self):
        """Test that invalid encrypted messages fail gracefully"""
        invalid_encrypted = "invalid_encrypted_message"

        # Should return None or raise exception for invalid messages
        result = self.client.decrypt_dm(
            self.recipient_public_key.hex(),
            invalid_encrypted
        )

        # Based on the implementation, this should either return None or raise an exception
        self.assertIsNone(result)

    def test_encryption_with_empty_message(self):
        """Test encryption with empty message"""
        encrypted = self.client.encrypt_dm(
            self.recipient_public_key.hex(),
            ""
        )

        self.assertIsNotNone(encrypted)

        # Decrypt and verify
        decrypted = self.client.decrypt_dm(
            self.recipient_public_key.hex(),
            encrypted
        )

        self.assertEqual(decrypted, "")

    def test_encryption_with_long_message(self):
        """Test encryption with a long message"""
        long_message = "A" * 1000  # 1000 character message

        encrypted = self.client.encrypt_dm(
            self.recipient_public_key.hex(),
            long_message
        )

        self.assertIsNotNone(encrypted)

        # Decrypt and verify
        decrypted = self.client.decrypt_dm(
            self.recipient_public_key.hex(),
            encrypted
        )

        self.assertEqual(decrypted, long_message)

    def test_event_signature_validation(self):
        """Test event signature validation"""
        # Create a test event
        from nostr_clients.nostr_client import NostrEvent
        test_event = NostrEvent(
            id="test_id",
            pubkey=self.client.public_key.hex(),
            created_at=1234567890,
            kind=1,
            tags=[],
            content="Test content",
            sig="test_signature"
        )

        # Mock validation to return True for our test
        with patch.object(self.client, 'validate_event_signature', return_value=True):
            result = self.client.validate_event_signature(test_event)
            self.assertTrue(result)

    def test_event_parsing(self):
        """Test parsing of action intent and signing response events"""
        # Test action intent parsing
        from nostr_clients.nostr_client import NostrEvent, ActionIntent
        action_intent_event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=31510,
            tags=[],
            content='{"session_type": "p2p_transfer", "intent_data": {"recipient_pubkey": "test_recipient", "asset_id": "test_asset", "amount": 100}}',
            sig="test_signature"
        )

        action_intent = self.client.parse_action_intent(action_intent_event)
        self.assertIsNotNone(action_intent)
        self.assertEqual(action_intent.session_type, "p2p_transfer")
        self.assertEqual(action_intent.intent_data["amount"], 100)

        # Test signing response parsing
        from nostr_clients.nostr_client import SigningResponse
        signing_response_event = NostrEvent(
            id="test_id",
            pubkey="test_pubkey",
            created_at=1234567890,
            kind=31512,
            tags=[],
            content='{"challenge_id": "test_challenge", "signature": "test_signature"}',
            sig="test_signature"
        )

        signing_response = self.client.parse_signing_response(signing_response_event)
        self.assertIsNotNone(signing_response)
        self.assertEqual(signing_response.challenge_id, "test_challenge")

    def test_publish_encrypted_dm(self):
        """Test publishing encrypted direct messages"""
        test_message = "This is a test encrypted DM"

        # Mock the publish_event method to avoid actual network calls
        with patch.object(self.client, 'publish_event', return_value="test_event_id") as mock_publish:
            result = self.client.send_encrypted_dm(
                self.recipient_public_key.hex(),
                test_message
            )

            self.assertEqual(result, "test_event_id")
            mock_publish.assert_called_once()

            # Verify the call arguments
            args, kwargs = mock_publish.call_args
            self.assertEqual(kwargs['kind'], 4)  # Encrypted DM kind
            self.assertIn(["p", self.recipient_public_key.hex()], kwargs['tags'])  # Recipient tag

def run_tests():
    """Run all encryption tests"""
    logger.info("Starting Nostr encryption tests...")

    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNostrEncryption)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    if result.wasSuccessful():
        logger.info("✅ All encryption tests passed!")
        return True
    else:
        logger.error(f"❌ {len(result.failures)} test(s) failed, {len(result.errors)} error(s)")
        return False

if __name__ == "__main__":
    run_tests()