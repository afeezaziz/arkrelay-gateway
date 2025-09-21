"""
Test cases for LND gRPC client
"""

import pytest
import grpc
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal

from grpc_clients.lnd_client import LndClient
from grpc_clients.grpc_client import ConnectionConfig, ServiceType


class TestLndClient:
    """Test cases for LndClient"""

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
    def lnd_client(self, connection_config):
        """Create LND client instance"""
        with patch('grpc_clients.lnd_client.grpc.insecure_channel'):
            with patch('grpc_clients.lnd_client.grpc.secure_channel'):
                client = LndClient(connection_config)
                # Mock the stub creation
                client.stub = Mock()
                return client

    def test_client_initialization(self, connection_config):
        """Test LND client initialization"""
        with patch('grpc_clients.lnd_client.grpc.insecure_channel'):
            with patch('grpc_clients.lnd_client.grpc.secure_channel'):
                client = LndClient(connection_config)
                assert client.service_type == ServiceType.LND
                assert client.config == connection_config
                assert client.circuit_breaker is not None

    def test_health_check_success(self, lnd_client):
        """Test successful health check"""
        with patch.object(lnd_client, '_health_check_impl') as mock_health:
            mock_health.return_value = True
            result = lnd_client.health_check()
            assert result is True

    def test_health_check_failure(self, lnd_client):
        """Test failed health check"""
        with patch.object(lnd_client, '_health_check_impl', side_effect=Exception("Service unavailable")):
            result = lnd_client.health_check()
            assert result is False

    def test_get_info_success(self, lnd_client):
        """Test successful node info retrieval"""
        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = {
                "version": "0.15.0-beta",
                "identity_pubkey": "test_pubkey",
                "alias": "test_node",
                "synced_to_chain": True,
                "block_height": 800000
            }

            result = lnd_client.get_info()
            assert result["version"] == "0.15.0-beta"
            assert result["identity_pubkey"] == "test_pubkey"
            assert result["synced_to_chain"] is True

    def test_get_info_failure(self, lnd_client):
        """Test node info retrieval failure"""
        with patch.object(lnd_client, '_execute_with_retry', side_effect=Exception("Info retrieval failed")):
            with pytest.raises(Exception, match="Failed to get node info"):
                lnd_client.get_info()

    def test_get_wallet_balance_success(self, lnd_client):
        """Test successful wallet balance retrieval"""
        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = {
                "total_balance": 1000000,
                "confirmed_balance": 950000,
                "unconfirmed_balance": 50000
            }

            result = lnd_client.get_wallet_balance()
            assert result["total_balance"] == 1000000
            assert result["confirmed_balance"] == 950000

    def test_get_wallet_balance_failure(self, lnd_client):
        """Test wallet balance retrieval failure"""
        with patch.object(lnd_client, '_execute_with_retry', side_effect=Exception("Balance retrieval failed")):
            with pytest.raises(Exception, match="Failed to get wallet balance"):
                lnd_client.get_wallet_balance()

    def test_get_channel_balance_success(self, lnd_client):
        """Test successful channel balance retrieval"""
        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = {
                "balance": 500000,
                "pending_open_balance": 0,
                "local_balance": 300000,
                "remote_balance": 200000
            }

            result = lnd_client.get_channel_balance()
            assert result["balance"] == 500000
            assert result["local_balance"] == 300000

    def test_get_channel_balance_failure(self, lnd_client):
        """Test channel balance retrieval failure"""
        with patch.object(lnd_client, '_execute_with_retry', side_effect=Exception("Channel balance failed")):
            with pytest.raises(Exception, match="Failed to get channel balance"):
                lnd_client.get_channel_balance()

    def test_list_channels_success(self, lnd_client):
        """Test successful channel listing"""
        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = [
                {
                    "channel_id": "channel1",
                    "remote_pubkey": "remote1",
                    "capacity": 1000000,
                    "local_balance": 600000,
                    "remote_balance": 400000,
                    "active": True
                },
                {
                    "channel_id": "channel2",
                    "remote_pubkey": "remote2",
                    "capacity": 500000,
                    "local_balance": 300000,
                    "remote_balance": 200000,
                    "active": False
                }
            ]

            result = lnd_client.list_channels()
            assert len(result) == 2
            assert result[0]["channel_id"] == "channel1"
            assert result[0]["active"] is True
            assert result[1]["active"] is False

    def test_list_channels_failure(self, lnd_client):
        """Test channel listing failure"""
        with patch.object(lnd_client, '_execute_with_retry', side_effect=Exception("Channel listing failed")):
            with pytest.raises(Exception, match="Failed to list channels"):
                lnd_client.list_channels()

    def test_open_channel_success(self, lnd_client):
        """Test successful channel opening"""
        channel_request = {
            "node_pubkey": "remote_pubkey",
            "local_funding_amount": 1000000,
            "push_sat": 10000
        }

        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = {
                "funding_txid": "funding_txid",
                "funding_output_index": 0,
                "channel_point": "funding_txid:0"
            }

            result = lnd_client.open_channel(channel_request)
            assert result["funding_txid"] == "funding_txid"

    def test_open_channel_failure(self, lnd_client):
        """Test channel opening failure"""
        channel_request = {"node_pubkey": "remote_pubkey"}

        with patch.object(lnd_client, '_execute_with_retry', side_effect=Exception("Channel opening failed")):
            with pytest.raises(Exception, match="Failed to open channel"):
                lnd_client.open_channel(channel_request)

    def test_close_channel_success(self, lnd_client):
        """Test successful channel closing"""
        close_request = {
            "channel_point": "funding_txid:0",
            "force": False
        }

        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = "closing_txid"

            result = lnd_client.close_channel(close_request)
            assert result == "closing_txid"

    def test_close_channel_failure(self, lnd_client):
        """Test channel closing failure"""
        close_request = {"channel_point": "funding_txid:0"}

        with patch.object(lnd_client, '_execute_with_retry', side_effect=Exception("Channel closing failed")):
            with pytest.raises(Exception, match="Failed to close channel"):
                lnd_client.close_channel(close_request)

    def test_send_payment_success(self, lnd_client):
        """Test successful payment sending"""
        payment_request = {
            "payment_request": "lnbc1000n1p3...",
            "amount": 100000,
            "fee_limit": 1000
        }

        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = {
                "payment_hash": "payment_hash",
                "payment_preimage": "preimage",
                "value": 100000,
                "fee": 100,
                "status": "SUCCEEDED"
            }

            result = lnd_client.send_payment(payment_request)
            assert result["status"] == "SUCCEEDED"
            assert result["value"] == 100000

    def test_send_payment_failure(self, lnd_client):
        """Test payment sending failure"""
        payment_request = {"payment_request": "lnbc1000n1p3..."}

        with patch.object(lnd_client, '_execute_with_retry', side_effect=Exception("Payment failed")):
            with pytest.raises(Exception, match="Failed to send payment"):
                lnd_client.send_payment(payment_request)

    def test_add_invoice_success(self, lnd_client):
        """Test successful invoice creation"""
        invoice_request = {
            "value": 100000,
            "memo": "Test invoice"
        }

        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = {
                "r_hash": "r_hash",
                "payment_request": "lnbc1000n1p3...",
                "add_index": 1,
                "payment_addr": "payment_addr"
            }

            result = lnd_client.add_invoice(invoice_request)
            assert result["r_hash"] == "r_hash"
            assert "payment_request" in result

    def test_add_invoice_failure(self, lnd_client):
        """Test invoice creation failure"""
        invoice_request = {"value": 100000}

        with patch.object(lnd_client, '_execute_with_retry', side_effect=Exception("Invoice creation failed")):
            with pytest.raises(Exception, match="Failed to add invoice"):
                lnd_client.add_invoice(invoice_request)

    def test_lookup_invoice_success(self, lnd_client):
        """Test successful invoice lookup"""
        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = {
                "r_hash": "r_hash",
                "value": 100000,
                "settled": True,
                "memo": "Test invoice"
            }

            result = lnd_client.lookup_invoice("r_hash")
            assert result["value"] == 100000
            assert result["settled"] is True

    def test_lookup_invoice_not_found(self, lnd_client):
        """Test invoice not found scenario"""
        with patch.object(lnd_client, '_execute_with_retry', side_effect=grpc.RpcError()):
            with patch('grpc.StatusCode.NOT_FOUND', grpc.StatusCode.NOT_FOUND):
                result = lnd_client.lookup_invoice("nonexistent_r_hash")
                assert result is None

    def test_list_invoices_success(self, lnd_client):
        """Test successful invoice listing"""
        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = [
                {
                    "r_hash": "r_hash1",
                    "value": 100000,
                    "settled": True,
                    "memo": "Invoice 1"
                },
                {
                    "r_hash": "r_hash2",
                    "value": 200000,
                    "settled": False,
                    "memo": "Invoice 2"
                }
            ]

            result = lnd_client.list_invoices()
            assert len(result) == 2
            assert result[0]["settled"] is True
            assert result[1]["settled"] is False

    def test_list_invoices_failure(self, lnd_client):
        """Test invoice listing failure"""
        with patch.object(lnd_client, '_execute_with_retry', side_effect=Exception("Invoice listing failed")):
            with pytest.raises(Exception, match="Failed to list invoices"):
                lnd_client.list_invoices()

    def test_list_payments_success(self, lnd_client):
        """Test successful payment listing"""
        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = [
                {
                    "payment_hash": "payment_hash1",
                    "value": 100000,
                    "fee": 100,
                    "status": "SUCCEEDED"
                },
                {
                    "payment_hash": "payment_hash2",
                    "value": 200000,
                    "fee": 200,
                    "status": "FAILED"
                }
            ]

            result = lnd_client.list_payments()
            assert len(result) == 2
            assert result[0]["status"] == "SUCCEEDED"
            assert result[1]["status"] == "FAILED"

    def test_list_payments_failure(self, lnd_client):
        """Test payment listing failure"""
        with patch.object(lnd_client, '_execute_with_retry', side_effect=Exception("Payment listing failed")):
            with pytest.raises(Exception, match="Failed to list payments"):
                lnd_client.list_payments()

    def test_new_address_success(self, lnd_client):
        """Test successful address generation"""
        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = "test_address"

            result = lnd_client.new_address()
            assert result == "test_address"

    def test_new_address_failure(self, lnd_client):
        """Test address generation failure"""
        with patch.object(lnd_client, '_execute_with_retry', side_effect=Exception("Address generation failed")):
            with pytest.raises(Exception, match="Failed to generate new address"):
                lnd_client.new_address()

    def test_send_coins_success(self, lnd_client):
        """Test successful coin sending"""
        coins_request = {
            "addr": "destination_address",
            "amount": 100000,
            "target_conf": 6
        }

        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = "txid"

            result = lnd_client.send_coins(coins_request)
            assert result == "txid"

    def test_send_coins_failure(self, lnd_client):
        """Test coin sending failure"""
        coins_request = {"addr": "destination_address", "amount": 100000}

        with patch.object(lnd_client, '_execute_with_retry', side_effect=Exception("Coin sending failed")):
            with pytest.raises(Exception, match="Failed to send coins"):
                lnd_client.send_coins(coins_request)

    def test_get_transactions_success(self, lnd_client):
        """Test successful transaction listing"""
        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = [
                {
                    "tx_hash": "tx_hash1",
                    "amount": 100000,
                    "num_confirmations": 6,
                    "block_hash": "block_hash",
                    "block_height": 800000
                }
            ]

            result = lnd_client.get_transactions()
            assert len(result) == 1
            assert result[0]["tx_hash"] == "tx_hash1"

    def test_get_transactions_failure(self, lnd_client):
        """Test transaction listing failure"""
        with patch.object(lnd_client, '_execute_with_retry', side_effect=Exception("Transaction listing failed")):
            with pytest.raises(Exception, match="Failed to get transactions"):
                lnd_client.get_transactions()

    def test_circuit_breaker_integration(self, lnd_client):
        """Test circuit breaker integration"""
        assert lnd_client.circuit_breaker is not None
        assert lnd_client.circuit_breaker.failure_threshold == 5
        assert lnd_client.circuit_breaker.recovery_timeout == 60

    def test_retry_mechanism_integration(self, lnd_client):
        """Test retry mechanism integration"""
        with patch.object(lnd_client, '_execute_with_retry') as mock_retry:
            mock_retry.return_value = "success"

            result = lnd_client.health_check()
            assert result is True
            mock_retry.assert_called_once()

    def test_grpc_error_handling(self, lnd_client):
        """Test gRPC error handling"""
        with patch.object(lnd_client, '_execute_with_retry', side_effect=grpc.RpcError()):
            with pytest.raises(grpc.RpcError):
                lnd_client.get_info()

    def test_connection_with_tls(self):
        """Test connection with TLS"""
        config = ConnectionConfig(
            host="localhost",
            port=10009,
            tls_cert="/path/to/cert.pem",
            macaroon="/path/to/macaroon",
            timeout_seconds=30
        )

        with patch('grpc_clients.lnd_client.grpc.secure_channel') as mock_secure:
            with patch('builtins.open', mock_open_read("mock_cert")):
                with patch('grpc_clients.lnd_client.grpc.ssl_channel_credentials'):
                    client = LndClient(config)
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

        with patch('grpc_clients.lnd_client.grpc.insecure_channel') as mock_insecure:
            client = LndClient(config)
            mock_insecure.assert_called_once()

    @pytest.mark.unit
    def test_client_independence(self, connection_config):
        """Test that multiple client instances are independent"""
        with patch('grpc_clients.lnd_client.grpc.insecure_channel'):
            with patch('grpc_clients.lnd_client.grpc.secure_channel'):
                client1 = LndClient(connection_config)
                client2 = LndClient(connection_config)

                assert client1 is not client2
                assert client1.circuit_breaker is not client2.circuit_breaker

    @pytest.mark.integration
    def test_integration_with_grpc_base(self, lnd_client):
        """Test integration with base gRPC client functionality"""
        assert hasattr(lnd_client, '_execute_with_retry')
        assert hasattr(lnd_client, 'health_check')
        assert hasattr(lnd_client, 'close')

    @pytest.mark.performance
    def test_method_performance(self, lnd_client):
        """Test method performance characteristics"""
        import time

        start_time = time.time()
        lnd_client.health_check()
        end_time = time.time()

        assert end_time - start_time < 1.0

    @pytest.mark.slow
    def test_slow_operations(self, lnd_client):
        """Test slower operations"""
        assert hasattr(lnd_client, 'list_channels')
        assert hasattr(lnd_client, 'list_invoices')
        assert hasattr(lnd_client, 'get_transactions')


# Helper function for mocking file operations
def mock_open_read(content):
    """Mock file open for reading"""
    mock_file = Mock()
    mock_file.read.return_value = content.encode()
    return mock_file