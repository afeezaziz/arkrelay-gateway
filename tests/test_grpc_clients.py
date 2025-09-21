"""
Unit Tests for gRPC Clients

This module contains unit tests for gRPC client functionality that can be run
without requiring actual daemon installations. Tests focus on the client logic,
configuration, and error handling.
"""

import unittest
from unittest.mock import Mock, patch
import os
import sys

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grpc_clients import GrpcClientManager, ServiceType, CircuitBreaker
from config import Config


class TestCircuitBreaker(unittest.TestCase):
    """Test CircuitBreaker functionality"""

    def setUp(self):
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1)

    def test_initially_closed(self):
        """Test that circuit breaker starts in closed state"""
        from grpc_clients import CircuitBreakerState
        self.assertEqual(self.circuit_breaker.state, CircuitBreakerState.CLOSED)
        self.assertEqual(self.circuit_breaker.failure_count, 0)

    def test_successful_call_remains_closed(self):
        """Test that successful calls keep circuit closed"""
        mock_func = Mock(return_value="success")
        result = self.circuit_breaker.call(mock_func)
        self.assertEqual(result, "success")
        self.assertEqual(self.circuit_breaker.failure_count, 0)

    def test_failure_count_increment(self):
        """Test that failure count increments on exceptions"""
        mock_func = Mock(side_effect=Exception("Test error"))
        with self.assertRaises(Exception):
            self.circuit_breaker.call(mock_func)
        self.assertEqual(self.circuit_breaker.failure_count, 1)


class TestConfiguration(unittest.TestCase):
    """Test configuration loading and validation"""

    def test_config_loading(self):
        """Test that configuration loads correctly"""
        self.assertIsNotNone(Config.DATABASE_URL)
        self.assertIsNotNone(Config.REDIS_URL)
        self.assertIsNotNone(Config.SECRET_KEY)

    def test_grpc_config(self):
        """Test gRPC configuration parameters"""
        self.assertIsNotNone(Config.ARKD_HOST)
        self.assertIsNotNone(Config.ARKD_PORT)
        self.assertIsNotNone(Config.TAPD_HOST)
        self.assertIsNotNone(Config.TAPD_PORT)
        self.assertIsNotNone(Config.LND_HOST)
        self.assertIsNotNone(Config.LND_PORT)

    def test_connection_params(self):
        """Test connection parameter methods"""
        arkd_params = Config.get_arkd_connection_params()
        self.assertIn('host', arkd_params)
        self.assertIn('port', arkd_params)
        self.assertIn('tls_cert', arkd_params)
        self.assertIn('macaroon', arkd_params)

        tapd_params = Config.get_tapd_connection_params()
        self.assertIn('host', tapd_params)
        self.assertIn('port', tapd_params)

        lnd_params = Config.get_lnd_connection_params()
        self.assertIn('host', lnd_params)
        self.assertIn('port', lnd_params)


class TestGrpcClientManager(unittest.TestCase):
    """Test gRPC client manager initialization"""

    @patch('grpc_clients.arkd_client.ArkdClient')
    @patch('grpc_clients.tapd_client.TapdClient')
    @patch('grpc_clients.lnd_client.LndClient')
    def test_manager_initialization(self, mock_lnd, mock_tapd, mock_arkd):
        """Test that manager initializes with all clients"""
        # Mock client creation
        mock_arkd.return_value = Mock()
        mock_tapd.return_value = Mock()
        mock_lnd.return_value = Mock()

        # Test that manager can be created
        with patch.dict(os.environ, {
            'ARKD_HOST': 'localhost',
            'ARKD_PORT': '10009',
            'TAPD_HOST': 'localhost',
            'TAPD_PORT': '10029',
            'LND_HOST': 'localhost',
            'LND_PORT': '10009'
        }) and patch('grpc_clients.grpc_client.ArkdClient', mock_arkd), patch('grpc_clients.grpc_client.TapdClient', mock_tapd), patch('grpc_clients.grpc_client.LndClient', mock_lnd):
            manager = GrpcClientManager()
            self.assertIsNotNone(manager)
            self.assertIn(ServiceType.ARKD, manager.clients)
            self.assertIn(ServiceType.TAPD, manager.clients)
            self.assertIn(ServiceType.LND, manager.clients)


class TestDataStructures(unittest.TestCase):
    """Test data structure definitions"""

    def test_arkd_data_structures(self):
        """Test ARKD client data structures"""
        from grpc_clients.arkd_client import VtxoInfo, ArkTransaction, SigningRequest
        from datetime import datetime

        # Test VtxoInfo
        vtxo = VtxoInfo(
            vtxo_id="test_vtxo",
            owner_pubkey="test_pubkey",
            amount=100000,
            asset_id="test_asset",
            status="available",
            created_at=datetime.now()
        )
        self.assertEqual(vtxo.vtxo_id, "test_vtxo")
        self.assertEqual(vtxo.amount, 100000)

        # Test ArkTransaction
        tx = ArkTransaction(
            ark_tx="test_tx",
            checkpoint_txs=["cp1", "cp2"],
            vtxos_to_spend=["vtxo1"],
            vtxos_to_create=[],
            fee_amount=1000,
            network="testnet"
        )
        self.assertEqual(tx.ark_tx, "test_tx")
        self.assertEqual(len(tx.checkpoint_txs), 2)

        # Test SigningRequest
        request = SigningRequest(
            session_id="test_session",
            challenge_type="ark_tx",
            payload_to_sign="test_payload",
            human_readable_context="Test signing",
            expires_at=datetime.now()
        )
        self.assertEqual(request.session_id, "test_session")
        self.assertEqual(request.challenge_type, "ark_tx")

    def test_tapd_data_structures(self):
        """Test TAPD client data structures"""
        from grpc_clients.tapd_client import AssetInfo, AssetBalance, AssetProof, LightningInvoice
        from datetime import datetime

        # Test AssetInfo
        asset = AssetInfo(
            asset_id="test_asset",
            name="Test Asset",
            ticker="TEST",
            asset_type="normal",
            amount=1000000,
            genesis_point="test_genesis",
            version=1,
            output_index=0,
            script_key="test_script"
        )
        self.assertEqual(asset.asset_id, "test_asset")
        self.assertEqual(asset.ticker, "TEST")

        # Test AssetBalance
        balance = AssetBalance(
            asset_id="test_asset",
            balance=1000000,
            utxo_count=1,
            channel_balance=500000
        )
        self.assertEqual(balance.balance, 1000000)
        self.assertEqual(balance.utxo_count, 1)

        # Test LightningInvoice
        invoice = LightningInvoice(
            invoice="test_invoice",
            payment_hash="test_hash",
            amount=100000,
            asset_id="test_asset",
            description="Test",
            expiry=3600,
            created_at=datetime.now()
        )
        self.assertEqual(invoice.invoice, "test_invoice")
        self.assertEqual(invoice.amount, 100000)

    def test_lnd_data_structures(self):
        """Test LND client data structures"""
        from grpc_clients.lnd_client import LightningBalance, OnchainBalance, ChannelInfo, LightningInvoice, Payment
        from datetime import datetime

        # Test LightningBalance
        lb = LightningBalance(
            local_balance=500000,
            remote_balance=500000,
            pending_open_local=0,
            pending_open_remote=0,
            pending_htlc_local=0,
            pending_htlc_remote=0
        )
        self.assertEqual(lb.local_balance, 500000)
        self.assertEqual(lb.remote_balance, 500000)

        # Test OnchainBalance
        ob = OnchainBalance(
            total_balance=1000000,
            confirmed_balance=1000000,
            unconfirmed_balance=0
        )
        self.assertEqual(ob.total_balance, 1000000)

        # Test ChannelInfo
        channel = ChannelInfo(
            channel_id="test_channel",
            remote_pubkey="remote_pubkey",
            capacity=1000000,
            local_balance=500000,
            remote_balance=500000,
            private=False,
            active=True,
            funding_txid="test_tx",
            funding_output_index=0
        )
        self.assertEqual(channel.channel_id, "test_channel")
        self.assertEqual(channel.capacity, 1000000)

        # Test LightningInvoice
        invoice = LightningInvoice(
            payment_request="test_request",
            r_hash="test_hash",
            payment_hash="test_payment_hash",
            value=100000,
            settled=False,
            creation_date=datetime.now(),
            expiry=3600,
            memo="Test"
        )
        self.assertEqual(invoice.payment_request, "test_request")
        self.assertEqual(invoice.value, 100000)


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)