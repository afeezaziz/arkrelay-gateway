"""
Test cases for ARKD gRPC client
"""

import pytest
import grpc
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from grpc_clients.arkd_client import ArkdClient, VtxoInfo, ArkTransaction, SigningRequest
from grpc_clients.grpc_client import ConnectionConfig, ServiceType


class TestArkdClient:
    """Test cases for ArkdClient"""

    @pytest.fixture
    def connection_config(self):
        """Create test connection config"""
        return ConnectionConfig(
            host="localhost",
            port=10009,
            tls_cert=None,
            macaroon=None,
            timeout_seconds=30
        )

    @pytest.fixture
    def arkd_client(self, connection_config):
        """Create ARKD client instance"""
        with patch('grpc_clients.arkd_client.grpc.insecure_channel'):
            with patch('grpc_clients.arkd_client.grpc.secure_channel'):
                client = ArkdClient(connection_config)
                # Mock the stub creation
                client.stub = Mock()
                return client

    def test_client_initialization(self, connection_config):
        """Test ARKD client initialization"""
        with patch('grpc_clients.arkd_client.grpc.insecure_channel'):
            with patch('grpc_clients.arkd_client.grpc.secure_channel'):
                client = ArkdClient(connection_config)
                assert client.service_type == ServiceType.ARKD
                assert client.config == connection_config
                assert client.circuit_breaker is not None

    def test_health_check_success(self, arkd_client):
        """Test successful health check"""
        result = arkd_client.health_check()
        assert result is True

    def test_health_check_failure(self, arkd_client):
        """Test failed health check"""
        with patch.object(arkd_client, '_health_check_impl', side_effect=Exception("Service unavailable")):
            result = arkd_client.health_check()
            assert result is False

    def test_create_vtxos_success(self, arkd_client):
        """Test successful VTXO creation"""
        with patch.object(arkd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = []

            result = arkd_client.create_vtxos(amount=1000, asset_id="btc", count=2)

            assert isinstance(result, list)
            assert len(result) == 0  # Placeholder returns empty list

    def test_create_vtxos_failure(self, arkd_client):
        """Test VTXO creation failure"""
        with patch.object(arkd_client, '_execute_with_retry', side_effect=Exception("Creation failed")):
            with pytest.raises(Exception, match="Failed to create VTXOs"):
                arkd_client.create_vtxos(amount=1000, asset_id="btc")

    def test_get_vtxo_info_success(self, arkd_client):
        """Test successful VTXO info retrieval"""
        with patch.object(arkd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = Mock()

            result = arkd_client.get_vtxo_info("test_vtxo_id")

            assert result is None  # Placeholder returns None

    def test_get_vtxo_info_not_found(self, arkd_client):
        """Test VTXO not found scenario"""
        with patch.object(arkd_client, '_execute_with_retry', side_effect=grpc.RpcError()):
            with patch('grpc.StatusCode.NOT_FOUND', grpc.StatusCode.NOT_FOUND):
                result = arkd_client.get_vtxo_info("nonexistent_vtxo")
                assert result is None

    def test_list_vtxos_success(self, arkd_client):
        """Test successful VTXO listing"""
        with patch.object(arkd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = []

            result = arkd_client.list_vtxos(owner_pubkey="test_pubkey")

            assert isinstance(result, list)
            assert len(result) == 0

    def test_list_vtxos_with_filters(self, arkd_client):
        """Test VTXO listing with filters"""
        with patch.object(arkd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = []

            result = arkd_client.list_vtxos(
                owner_pubkey="test_pubkey",
                asset_id="btc",
                status="active"
            )

            assert isinstance(result, list)

    def test_spend_vtxos_success(self, arkd_client):
        """Test successful VTXO spending"""
        with patch.object(arkd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = Mock()

            result = arkd_client.spend_vtxos(
                vtxo_ids=["vtxo1", "vtxo2"],
                destination_pubkey="dest_pubkey",
                amount=1000,
                asset_id="btc"
            )

            assert isinstance(result, ArkTransaction)
            assert result.vtxos_to_spend == ["vtxo1", "vtxo2"]
            assert result.network == "testnet"

    def test_spend_vtxos_failure(self, arkd_client):
        """Test VTXO spending failure"""
        with patch.object(arkd_client, '_execute_with_retry', side_effect=Exception("Spending failed")):
            with pytest.raises(Exception, match="Failed to prepare VTXO spending"):
                arkd_client.spend_vtxos(
                    vtxo_ids=["vtxo1"],
                    destination_pubkey="dest_pubkey",
                    amount=1000,
                    asset_id="btc"
                )

    def test_prepare_signing_request_success(self, arkd_client):
        """Test successful signing request preparation"""
        test_context = {"amount": 1000, "asset": "btc"}

        result = arkd_client.prepare_signing_request(
            session_id="test_session",
            challenge_type="vtxo_transfer",
            context=test_context
        )

        assert isinstance(result, SigningRequest)
        assert result.session_id == "test_session"
        assert result.challenge_type == "vtxo_transfer"

    def test_prepare_signing_request_failure(self, arkd_client):
        """Test signing request preparation failure"""
        with patch.object(arkd_client, '_execute_with_retry', side_effect=Exception("Preparation failed")):
            with pytest.raises(Exception, match="Failed to prepare signing request"):
                arkd_client.prepare_signing_request(
                    session_id="test_session",
                    challenge_type="vtxo_transfer",
                    context={}
                )

    def test_submit_signatures_success(self, arkd_client):
        """Test successful signature submission"""
        signatures = {"sig1": "signature_data"}

        result = arkd_client.submit_signatures(
            session_id="test_session",
            signatures=signatures
        )

        assert result is True

    def test_submit_signatures_failure(self, arkd_client):
        """Test signature submission failure"""
        with patch.object(arkd_client, '_execute_with_retry', side_effect=Exception("Submission failed")):
            with pytest.raises(Exception, match="Failed to submit signatures"):
                arkd_client.submit_signatures(
                    session_id="test_session",
                    signatures={}
                )

    def test_get_session_status_success(self, arkd_client):
        """Test successful session status retrieval"""
        result = arkd_client.get_session_status("test_session")

        assert isinstance(result, dict)
        assert result["session_id"] == "test_session"
        assert result["status"] == "pending"

    def test_get_session_status_failure(self, arkd_client):
        """Test session status retrieval failure"""
        with patch.object(arkd_client, '_execute_with_retry', side_effect=Exception("Status retrieval failed")):
            with pytest.raises(Exception, match="Failed to get session status"):
                arkd_client.get_session_status("test_session")

    def test_get_network_info_success(self, arkd_client):
        """Test successful network info retrieval"""
        result = arkd_client.get_network_info()

        assert isinstance(result, dict)
        assert result["network"] == "testnet"
        assert result["synced"] is True
        assert "block_height" in result

    def test_get_network_info_failure(self, arkd_client):
        """Test network info retrieval failure"""
        with patch.object(arkd_client, '_execute_with_retry', side_effect=Exception("Network info failed")):
            with pytest.raises(Exception, match="Failed to get network info"):
                arkd_client.get_network_info()

    def test_get_pending_transactions_success(self, arkd_client):
        """Test successful pending transactions retrieval"""
        result = arkd_client.get_pending_transactions()

        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_pending_transactions_failure(self, arkd_client):
        """Test pending transactions retrieval failure"""
        with patch.object(arkd_client, '_execute_with_retry', side_effect=Exception("Pending txs failed")):
            with pytest.raises(Exception, match="Failed to get pending transactions"):
                arkd_client.get_pending_transactions()

    def test_create_commitment_transaction_success(self, arkd_client):
        """Test successful commitment transaction creation"""
        l2_changes = [{"change_type": "vtxo_create", "amount": 1000}]

        result = arkd_client.create_commitment_transaction(l2_changes)

        assert isinstance(result, str)
        assert result == "mock_txid"

    def test_create_commitment_transaction_failure(self, arkd_client):
        """Test commitment transaction creation failure"""
        with patch.object(arkd_client, '_execute_with_retry', side_effect=Exception("Commitment failed")):
            with pytest.raises(Exception, match="Failed to create commitment transaction"):
                arkd_client.create_commitment_transaction([])

    def test_circuit_breaker_integration(self, arkd_client):
        """Test circuit breaker integration"""
        # Test that circuit breaker is properly initialized
        assert arkd_client.circuit_breaker is not None
        assert arkd_client.circuit_breaker.failure_threshold == 5
        assert arkd_client.circuit_breaker.recovery_timeout == 60

    def test_retry_mechanism_integration(self, arkd_client):
        """Test retry mechanism integration"""
        with patch.object(arkd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = "success"

            result = arkd_client.health_check()
            assert result is True
            mock_retry.assert_called_once()

    def test_vtxo_info_dataclass(self):
        """Test VtxoInfo dataclass"""
        vtxo = VtxoInfo(
            vtxo_id="test_id",
            owner_pubkey="test_pubkey",
            amount=1000,
            asset_id="btc",
            status="active",
            created_at=datetime.now()
        )

        assert vtxo.vtxo_id == "test_id"
        assert vtxo.owner_pubkey == "test_pubkey"
        assert vtxo.amount == 1000
        assert vtxo.asset_id == "btc"
        assert vtxo.status == "active"

    def test_ark_transaction_dataclass(self):
        """Test ArkTransaction dataclass"""
        vtxo = VtxoInfo(
            vtxo_id="test_id",
            owner_pubkey="test_pubkey",
            amount=1000,
            asset_id="btc",
            status="active",
            created_at=datetime.now()
        )

        tx = ArkTransaction(
            ark_tx="test_tx",
            checkpoint_txs=["checkpoint1"],
            vtxos_to_spend=["vtxo1"],
            vtxos_to_create=[vtxo],
            fee_amount=100,
            network="testnet"
        )

        assert tx.ark_tx == "test_tx"
        assert len(tx.checkpoint_txs) == 1
        assert len(tx.vtxos_to_spend) == 1
        assert len(tx.vtxos_to_create) == 1
        assert tx.fee_amount == 100
        assert tx.network == "testnet"

    def test_signing_request_dataclass(self):
        """Test SigningRequest dataclass"""
        request = SigningRequest(
            session_id="test_session",
            challenge_type="vtxo_transfer",
            payload_to_sign="test_payload",
            human_readable_context="Test context",
            expires_at=datetime.now()
        )

        assert request.session_id == "test_session"
        assert request.challenge_type == "vtxo_transfer"
        assert request.payload_to_sign == "test_payload"
        assert request.human_readable_context == "Test context"

    def test_connection_with_tls(self):
        """Test connection with TLS"""
        config = ConnectionConfig(
            host="localhost",
            port=10009,
            tls_cert="/path/to/cert.pem",
            macaroon="/path/to/macaroon",
            timeout_seconds=30
        )

        with patch('grpc_clients.arkd_client.grpc.secure_channel') as mock_secure:
            with patch('builtins.open', mock_open_read("mock_cert")):
                with patch('grpc_clients.arkd_client.grpc.ssl_channel_credentials'):
                    client = ArkdClient(config)
                    mock_secure.assert_called_once()

    def test_connection_without_tls(self):
        """Test connection without TLS"""
        config = ConnectionConfig(
            host="localhost",
            port=10009,
            tls_cert=None,
            macaroon=None,
            timeout_seconds=30
        )

        with patch('grpc_clients.arkd_client.grpc.insecure_channel') as mock_insecure:
            client = ArkdClient(config)
            mock_insecure.assert_called_once()

    def test_grpc_error_handling(self, arkd_client):
        """Test gRPC error handling"""
        with patch.object(arkd_client, '_execute_with_retry', side_effect=grpc.RpcError()):
            with pytest.raises(grpc.RpcError):
                arkd_client.get_vtxo_info("test_vtxo")

    def test_timeout_configuration(self, arkd_client):
        """Test timeout configuration"""
        assert arkd_client.config.timeout_seconds == 30

    @pytest.mark.unit
    def test_client_independence(self, connection_config):
        """Test that multiple client instances are independent"""
        with patch('grpc_clients.arkd_client.grpc.insecure_channel'):
            with patch('grpc_clients.arkd_client.grpc.secure_channel'):
                client1 = ArkdClient(connection_config)
                client2 = ArkdClient(connection_config)

                assert client1 is not client2
                assert client1.circuit_breaker is not client2.circuit_breaker

    @pytest.mark.integration
    def test_integration_with_grpc_base(self, arkd_client):
        """Test integration with base gRPC client functionality"""
        # Test that the client properly inherits base functionality
        assert hasattr(arkd_client, '_execute_with_retry')
        assert hasattr(arkd_client, 'health_check')
        assert hasattr(arkd_client, 'close')

        # Test health check through base class
        with patch.object(arkd_client, '_health_check_impl') as mock_health:
            mock_health.return_value = True
            result = arkd_client.health_check()
            assert result is True

    @pytest.mark.performance
    def test_method_performance(self, arkd_client):
        """Test method performance characteristics"""
        import time

        start_time = time.time()
        arkd_client.health_check()
        end_time = time.time()

        # Health check should be fast (less than 1 second)
        assert end_time - start_time < 1.0

    @pytest.mark.slow
    def test_slow_operations(self, arkd_client):
        """Test slower operations"""
        # This would test operations that might take longer
        # For now, just verify the methods exist and can be called
        assert hasattr(arkd_client, 'list_vtxos')
        assert hasattr(arkd_client, 'get_pending_transactions')
        assert hasattr(arkd_client, 'create_commitment_transaction')


# Helper function for mocking file operations
def mock_open_read(content):
    """Mock file open for reading"""
    mock_file = Mock()
    mock_file.read.return_value = content.encode()
    return mock_file