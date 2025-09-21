"""
Test cases for TAPD gRPC client
"""

import pytest
import grpc
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from grpc_clients.tapd_client import TapdClient
from grpc_clients.grpc_client import ConnectionConfig, ServiceType


class TestTapdClient:
    """Test cases for TapdClient"""

    @pytest.fixture
    def connection_config(self):
        """Create test connection config"""
        return ConnectionConfig(
            host="localhost",
            port=10029,
            tls_cert=None,
            macaroon=None,
            timeout_seconds=30
        )

    @pytest.fixture
    def tapd_client(self, connection_config):
        """Create TAPD client instance"""
        with patch('grpc_clients.tapd_client.grpc.insecure_channel'):
            with patch('grpc_clients.tapd_client.grpc.secure_channel'):
                client = TapdClient(connection_config)
                # Mock the stub creation
                client.stub = Mock()
                return client

    def test_client_initialization(self, connection_config):
        """Test TAPD client initialization"""
        with patch('grpc_clients.tapd_client.grpc.insecure_channel'):
            with patch('grpc_clients.tapd_client.grpc.secure_channel'):
                client = TapdClient(connection_config)
                assert client.service_type == ServiceType.TAPD
                assert client.config == connection_config
                assert client.circuit_breaker is not None

    def test_health_check_success(self, tapd_client):
        """Test successful health check"""
        with patch.object(tapd_client, '_health_check_impl') as mock_health:
            mock_health.return_value = True
            result = tapd_client.health_check()
            assert result is True

    def test_health_check_failure(self, tapd_client):
        """Test failed health check"""
        with patch.object(tapd_client, '_health_check_impl', side_effect=Exception("Service unavailable")):
            result = tapd_client.health_check()
            assert result is False

    def test_create_asset_success(self, tapd_client):
        """Test successful asset creation"""
        asset_info = {
            "asset_name": "Test Asset",
            "asset_type": "normal",
            "supply": 1000000,
            "precision": 8
        }

        with patch.object(tapd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = "mock_asset_id"

            result = tapd_client.create_asset(asset_info)
            assert result == "mock_asset_id"

    def test_create_asset_failure(self, tapd_client):
        """Test asset creation failure"""
        asset_info = {"asset_name": "Test Asset"}

        with patch.object(tapd_client, '_execute_with_retry', side_effect=Exception("Creation failed")):
            with pytest.raises(Exception, match="Failed to create asset"):
                tapd_client.create_asset(asset_info)

    def test_mint_asset_success(self, tapd_client):
        """Test successful asset minting"""
        mint_request = {
            "asset_id": "test_asset_id",
            "amount": 1000,
            "destination": "test_address"
        }

        with patch.object(tapd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = "mock_txid"

            result = tapd_client.mint_asset(mint_request)
            assert result == "mock_txid"

    def test_mint_asset_failure(self, tapd_client):
        """Test asset minting failure"""
        mint_request = {"asset_id": "test_asset_id", "amount": 1000}

        with patch.object(tapd_client, '_execute_with_retry', side_effect=Exception("Minting failed")):
            with pytest.raises(Exception, match="Failed to mint asset"):
                tapd_client.mint_asset(mint_request)

    def test_transfer_asset_success(self, tapd_client):
        """Test successful asset transfer"""
        transfer_request = {
            "asset_id": "test_asset_id",
            "amount": 100,
            "source": "source_address",
            "destination": "dest_address"
        }

        with patch.object(tapd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = "transfer_txid"

            result = tapd_client.transfer_asset(transfer_request)
            assert result == "transfer_txid"

    def test_transfer_asset_failure(self, tapd_client):
        """Test asset transfer failure"""
        transfer_request = {"asset_id": "test_asset_id", "amount": 100}

        with patch.object(tapd_client, '_execute_with_retry', side_effect=Exception("Transfer failed")):
            with pytest.raises(Exception, match="Failed to transfer asset"):
                tapd_client.transfer_asset(transfer_request)

    def test_get_asset_info_success(self, tapd_client):
        """Test successful asset info retrieval"""
        with patch.object(tapd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = {
                "asset_id": "test_asset_id",
                "name": "Test Asset",
                "supply": 1000000
            }

            result = tapd_client.get_asset_info("test_asset_id")
            assert result["asset_id"] == "test_asset_id"
            assert result["name"] == "Test Asset"

    def test_get_asset_info_not_found(self, tapd_client):
        """Test asset not found scenario"""
        with patch.object(tapd_client, '_execute_with_retry', side_effect=grpc.RpcError()):
            with patch('grpc.StatusCode.NOT_FOUND', grpc.StatusCode.NOT_FOUND):
                result = tapd_client.get_asset_info("nonexistent_asset")
                assert result is None

    def test_list_assets_success(self, tapd_client):
        """Test successful asset listing"""
        with patch.object(tapd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = [
                {"asset_id": "asset1", "name": "Asset 1"},
                {"asset_id": "asset2", "name": "Asset 2"}
            ]

            result = tapd_client.list_assets()
            assert len(result) == 2
            assert result[0]["asset_id"] == "asset1"

    def test_list_assets_failure(self, tapd_client):
        """Test asset listing failure"""
        with patch.object(tapd_client, '_execute_with_retry', side_effect=Exception("Listing failed")):
            with pytest.raises(Exception, match="Failed to list assets"):
                tapd_client.list_assets()

    def test_get_balance_success(self, tapd_client):
        """Test successful balance retrieval"""
        with patch.object(tapd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = {
                "asset_id": "test_asset_id",
                "balance": 1000,
                "address": "test_address"
            }

            result = tapd_client.get_balance("test_asset_id", "test_address")
            assert result["balance"] == 1000

    def test_get_balance_failure(self, tapd_client):
        """Test balance retrieval failure"""
        with patch.object(tapd_client, '_execute_with_retry', side_effect=Exception("Balance query failed")):
            with pytest.raises(Exception, match="Failed to get balance"):
                tapd_client.get_balance("test_asset_id", "test_address")

    def test_freeze_asset_success(self, tapd_client):
        """Test successful asset freezing"""
        freeze_request = {
            "asset_id": "test_asset_id",
            "amount": 500,
            "freeze_script": "freeze_script"
        }

        with patch.object(tapd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = "freeze_txid"

            result = tapd_client.freeze_asset(freeze_request)
            assert result == "freeze_txid"

    def test_freeze_asset_failure(self, tapd_client):
        """Test asset freezing failure"""
        freeze_request = {"asset_id": "test_asset_id", "amount": 500}

        with patch.object(tapd_client, '_execute_with_retry', side_effect=Exception("Freezing failed")):
            with pytest.raises(Exception, match="Failed to freeze asset"):
                tapd_client.freeze_asset(freeze_request)

    def test_unfreeze_asset_success(self, tapd_client):
        """Test successful asset unfreezing"""
        unfreeze_request = {
            "asset_id": "test_asset_id",
            "amount": 500,
            "freeze_script": "freeze_script"
        }

        with patch.object(tapd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = "unfreeze_txid"

            result = tapd_client.unfreeze_asset(unfreeze_request)
            assert result == "unfreeze_txid"

    def test_unfreeze_asset_failure(self, tapd_client):
        """Test asset unfreezing failure"""
        unfreeze_request = {"asset_id": "test_asset_id", "amount": 500}

        with patch.object(tapd_client, '_execute_with_retry', side_effect=Exception("Unfreezing failed")):
            with pytest.raises(Exception, match="Failed to unfreeze asset"):
                tapd_client.unfreeze_asset(unfreeze_request)

    def test_decode_proof_success(self, tapd_client):
        """Test successful proof decoding"""
        with patch.object(tapd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = {
                "asset_id": "test_asset_id",
                "amount": 1000,
                "owner": "test_owner"
            }

            result = tapd_client.decode_proof("test_proof")
            assert result["asset_id"] == "test_asset_id"

    def test_decode_proof_failure(self, tapd_client):
        """Test proof decoding failure"""
        with patch.object(tapd_client, '_execute_with_retry', side_effect=Exception("Decoding failed")):
            with pytest.raises(Exception, match="Failed to decode proof"):
                tapd_client.decode_proof("invalid_proof")

    def test_verify_proof_success(self, tapd_client):
        """Test successful proof verification"""
        with patch.object(tapd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = True

            result = tapd_client.verify_proof("test_proof")
            assert result is True

    def test_verify_proof_failure(self, tapd_client):
        """Test proof verification failure"""
        with patch.object(tapd_client, '_execute_with_retry', side_effect=Exception("Verification failed")):
            result = tapd_client.verify_proof("invalid_proof")
            assert result is False

    def test_circuit_breaker_integration(self, tapd_client):
        """Test circuit breaker integration"""
        assert tapd_client.circuit_breaker is not None
        assert tapd_client.circuit_breaker.failure_threshold == 5
        assert tapd_client.circuit_breaker.recovery_timeout == 60

    def test_retry_mechanism_integration(self, tapd_client):
        """Test retry mechanism integration"""
        with patch.object(tapd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = "success"

            result = tapd_client.health_check()
            assert result is True
            mock_retry.assert_called_once()

    def test_grpc_error_handling(self, tapd_client):
        """Test gRPC error handling"""
        with patch.object(tapd_client, '_execute_with_retry', side_effect=grpc.RpcError()):
            with pytest.raises(grpc.RpcError):
                tapd_client.get_asset_info("test_asset")

    def test_connection_with_tls(self):
        """Test connection with TLS"""
        config = ConnectionConfig(
            host="localhost",
            port=10029,
            tls_cert="/path/to/cert.pem",
            macaroon="/path/to/macaroon",
            timeout_seconds=30
        )

        with patch('grpc_clients.tapd_client.grpc.secure_channel') as mock_secure:
            with patch('builtins.open', mock_open_read("mock_cert")):
                with patch('grpc_clients.tapd_client.grpc.ssl_channel_credentials'):
                    client = TapdClient(config)
                    mock_secure.assert_called_once()

    def test_connection_without_tls(self):
        """Test connection without TLS"""
        config = ConnectionConfig(
            host="localhost",
            port=10029,
            tls_cert=None,
            macaroon=None,
            timeout_seconds=30
        )

        with patch('grpc_clients.tapd_client.grpc.insecure_channel') as mock_insecure:
            client = TapdClient(config)
            mock_insecure.assert_called_once()

    @pytest.mark.unit
    def test_client_independence(self, connection_config):
        """Test that multiple client instances are independent"""
        with patch('grpc_clients.tapd_client.grpc.insecure_channel'):
            with patch('grpc_clients.tapd_client.grpc.secure_channel'):
                client1 = TapdClient(connection_config)
                client2 = TapdClient(connection_config)

                assert client1 is not client2
                assert client1.circuit_breaker is not client2.circuit_breaker

    @pytest.mark.integration
    def test_integration_with_grpc_base(self, tapd_client):
        """Test integration with base gRPC client functionality"""
        assert hasattr(tapd_client, '_execute_with_retry')
        assert hasattr(tapd_client, 'health_check')
        assert hasattr(tapd_client, 'close')

    @pytest.mark.performance
    def test_method_performance(self, tapd_client):
        """Test method performance characteristics"""
        import time

        start_time = time.time()
        tapd_client.health_check()
        end_time = time.time()

        assert end_time - start_time < 1.0

    @pytest.mark.slow
    def test_slow_operations(self, tapd_client):
        """Test slower operations"""
        assert hasattr(tapd_client, 'list_assets')
        assert hasattr(tapd_client, 'get_asset_info')
        assert hasattr(tapd_client, 'transfer_asset')


# Helper function for mocking file operations
def mock_open_read(content):
    """Mock file open for reading"""
    mock_file = Mock()
    mock_file.read.return_value = content.encode()
    return mock_file