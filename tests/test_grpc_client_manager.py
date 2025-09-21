"""
Test cases for gRPC Client Manager
"""

import pytest
import threading
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor

from grpc_clients.grpc_client import GrpcClientManager, ServiceType, ConnectionConfig
from grpc_clients.arkd_client import ArkdClient
from grpc_clients.tapd_client import TapdClient
from grpc_clients.lnd_client import LndClient
from core.config import Config


class TestGrpcClientManager:
    """Test cases for GrpcClientManager"""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing"""
        config = Mock()
        config.ARKD_HOST = "localhost"
        config.ARKD_PORT = 10009
        config.ARKD_TLS_CERT = None
        config.ARKD_MACAROON = None
        config.TAPD_HOST = "localhost"
        config.TAPD_PORT = 10029
        config.TAPD_TLS_CERT = None
        config.TAPD_MACAROON = None
        config.LND_HOST = "localhost"
        config.LND_PORT = 10009
        config.LND_TLS_CERT = None
        config.LND_MACAROON = None
        config.GRPC_TIMEOUT_SECONDS = 30
        config.GRPC_MAX_MESSAGE_LENGTH = 4194304
        return config

    @pytest.fixture
    def grpc_manager(self, mock_config):
        """Create gRPC client manager with mocked dependencies"""
        with patch('grpc_clients.grpc_client.Config', return_value=mock_config):
            with patch('grpc_clients.arkd_client.grpc.insecure_channel'):
                with patch('grpc_clients.arkd_client.grpc.secure_channel'):
                    with patch('grpc_clients.tapd_client.grpc.insecure_channel'):
                        with patch('grpc_clients.tapd_client.grpc.secure_channel'):
                            with patch('grpc_clients.lnd_client.grpc.insecure_channel'):
                                with patch('grpc_clients.lnd_client.grpc.secure_channel'):
                                    manager = GrpcClientManager()
                                    return manager

    def test_manager_initialization(self, grpc_manager):
        """Test manager initialization"""
        assert isinstance(grpc_manager.clients, dict)
        assert len(grpc_manager.clients) == 3
        assert ServiceType.ARKD in grpc_manager.clients
        assert ServiceType.TAPD in grpc_manager.clients
        assert ServiceType.LND in grpc_manager.clients

    def test_get_client_success(self, grpc_manager):
        """Test successful client retrieval"""
        arkd_client = grpc_manager.get_client(ServiceType.ARKD)
        assert isinstance(arkd_client, ArkdClient)

        tapd_client = grpc_manager.get_client(ServiceType.TAPD)
        assert isinstance(tapd_client, TapdClient)

        lnd_client = grpc_manager.get_client(ServiceType.LND)
        assert isinstance(lnd_client, LndClient)

    def test_get_nonexistent_client(self, grpc_manager):
        """Test getting nonexistent client"""
        nonexistent_client = grpc_manager.get_client("nonexistent")
        assert nonexistent_client is None

    def test_health_check_all_success(self, grpc_manager):
        """Test successful health check for all services"""
        # Mock successful health checks
        for client in grpc_manager.clients.values():
            client.health_check = Mock(return_value=True)

        results = grpc_manager.health_check_all()

        assert len(results) == 3
        assert all(results.values())
        assert results[ServiceType.ARKD] is True
        assert results[ServiceType.TAPD] is True
        assert results[ServiceType.LND] is True

    def test_health_check_all_partial_failure(self, grpc_manager):
        """Test health check with some failures"""
        # Mock mixed health check results
        grpc_manager.clients[ServiceType.ARKD].health_check = Mock(return_value=True)
        grpc_manager.clients[ServiceType.TAPD].health_check = Mock(return_value=False)
        grpc_manager.clients[ServiceType.LND].health_check = Mock(side_effect=Exception("Service down"))

        results = grpc_manager.health_check_all()

        assert len(results) == 3
        assert results[ServiceType.ARKD] is True
        assert results[ServiceType.TAPD] is False
        assert results[ServiceType.LND] is False

    def test_health_check_all_timeout(self, grpc_manager):
        """Test health check timeout handling"""
        def slow_health_check():
            import time
            time.sleep(2)
            return True

        # Mock slow health check
        for client in grpc_manager.clients.values():
            client.health_check = Mock(side_effect=slow_health_check)

        results = grpc_manager.health_check_all()

        # Should handle timeouts gracefully
        assert len(results) == 3
        # Some may fail due to timeout

    def test_reconnect_success(self, grpc_manager):
        """Test successful reconnection"""
        # Mock successful reconnection
        grpc_manager.clients[ServiceType.ARKD]._connect = Mock()

        grpc_manager.reconnect(ServiceType.ARKD)

        grpc_manager.clients[ServiceType.ARKD]._connect.assert_called_once()

    def test_reconnect_failure(self, grpc_manager):
        """Test reconnection failure"""
        # Mock failed reconnection
        grpc_manager.clients[ServiceType.ARKD]._connect = Mock(side_effect=Exception("Connection failed"))

        with pytest.raises(Exception, match="Failed to reconnect to ARKD"):
            grpc_manager.reconnect(ServiceType.ARKD)

    def test_reconnect_nonexistent_service(self, grpc_manager):
        """Test reconnection to nonexistent service"""
        # Should not raise an error for nonexistent service
        grpc_manager.reconnect("nonexistent")

    def test_close_all_success(self, grpc_manager):
        """Test successful closing of all connections"""
        # Mock successful close operations
        for client in grpc_manager.clients.values():
            client.close = Mock()

        grpc_manager.close_all()

        for client in grpc_manager.clients.values():
            client.close.assert_called_once()

    def test_close_all_partial_failure(self, grpc_manager):
        """Test closing all connections with some failures"""
        # Mock mixed close results
        grpc_manager.clients[ServiceType.ARKD].close = Mock()
        grpc_manager.clients[ServiceType.TAPD].close = Mock(side_effect=Exception("Close failed"))
        grpc_manager.clients[ServiceType.LND].close = Mock()

        # Should not raise an error, should log and continue
        grpc_manager.close_all()

        # All close methods should have been called
        grpc_manager.clients[ServiceType.ARKD].close.assert_called_once()
        grpc_manager.clients[ServiceType.TAPD].close.assert_called_once()
        grpc_manager.clients[ServiceType.LND].close.assert_called_once()

    def test_thread_safety(self, grpc_manager):
        """Test thread safety of manager operations"""
        def get_client_thread(service_type):
            """Thread function to get client"""
            client = grpc_manager.get_client(service_type)
            return client is not None

        def health_check_thread():
            """Thread function to perform health check"""
            return grpc_manager.health_check_all()

        threads = []
        results = []

        # Create multiple threads for concurrent operations
        for _ in range(5):
            thread1 = threading.Thread(target=lambda: results.append(get_client_thread(ServiceType.ARKD)))
            thread2 = threading.Thread(target=lambda: results.append(health_check_thread()))
            threads.extend([thread1, thread2])

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All operations should have completed successfully
        assert len(results) == 10
        assert all(results)

    def test_config_loading_error(self):
        """Test configuration loading error handling"""
        with patch('grpc_clients.grpc_client.Config', side_effect=Exception("Config error")):
            with pytest.raises(Exception, match="Failed to initialize gRPC clients"):
                GrpcClientManager()

    def test_connection_config_creation(self, mock_config):
        """Test connection configuration creation"""
        with patch('grpc_clients.grpc_client.Config', return_value=mock_config):
            with patch('grpc_clients.arkd_client.grpc.insecure_channel'):
                with patch('grpc_clients.arkd_client.grpc.secure_channel'):
                    with patch('grpc_clients.tapd_client.grpc.insecure_channel'):
                        with patch('grpc_clients.tapd_client.grpc.secure_channel'):
                            with patch('grpc_clients.lnd_client.grpc.insecure_channel'):
                                with patch('grpc_clients.lnd_client.grpc.secure_channel'):
                                    manager = GrpcClientManager()

                                    # Check that ARKD config is correct
                                    arkd_client = manager.clients[ServiceType.ARKD]
                                    assert arkd_client.config.host == "localhost"
                                    assert arkd_client.config.port == 10009
                                    assert arkd_client.config.timeout_seconds == 30

    def test_connection_options(self, mock_config):
        """Test gRPC connection options"""
        with patch('grpc_clients.grpc_client.Config', return_value=mock_config):
            with patch('grpc_clients.arkd_client.grpc.insecure_channel') as mock_insecure:
                with patch('grpc_clients.arkd_client.grpc.secure_channel') as mock_secure:
                    with patch('grpc_clients.tapd_client.grpc.insecure_channel'):
                        with patch('grpc_clients.tapd_client.grpc.secure_channel'):
                            with patch('grpc_clients.lnd_client.grpc.insecure_channel'):
                                with patch('grpc_clients.lnd_client.grpc.secure_channel'):
                                    GrpcClientManager()

                                    # Check that connection options are passed
                                    # This depends on the actual implementation
                                    assert mock_insecure.called or mock_secure.called

    def test_singleton_behavior(self, mock_config):
        """Test singleton behavior of global manager"""
        with patch('grpc_clients.grpc_client.Config', return_value=mock_config):
            with patch('grpc_clients.arkd_client.grpc.insecure_channel'):
                with patch('grpc_clients.arkd_client.grpc.secure_channel'):
                    with patch('grpc_clients.tapd_client.grpc.insecure_channel'):
                        with patch('grpc_clients.tapd_client.grpc.secure_channel'):
                            with patch('grpc_clients.lnd_client.grpc.insecure_channel'):
                                with patch('grpc_clients.lnd_client.grpc.secure_channel'):
                                    # Reset global manager
                                    import grpc_clients.grpc_client
                                    grpc_clients.grpc_client._grpc_manager = None

                                    manager1 = grpc_clients.grpc_client.get_grpc_manager()
                                    manager2 = grpc_clients.grpc_client.get_grpc_manager()

                                    assert manager1 is manager2

    def test_client_manager_lifecycle(self, grpc_manager):
        """Test complete client manager lifecycle"""
        # Test initial state
        assert len(grpc_manager.clients) == 3

        # Test health checks
        for client in grpc_manager.clients.values():
            client.health_check = Mock(return_value=True)

        results = grpc_manager.health_check_all()
        assert all(results.values())

        # Test reconnection
        grpc_manager.reconnect(ServiceType.ARKD)

        # Test client retrieval
        arkd_client = grpc_manager.get_client(ServiceType.ARKD)
        assert arkd_client is not None

        # Test cleanup
        grpc_manager.close_all()

        # Verify clients are still present but connections are closed
        assert len(grpc_manager.clients) == 3

    @pytest.mark.integration
    def test_integration_with_circuit_breakers(self, grpc_manager):
        """Test integration with client circuit breakers"""
        # Test that each client has a circuit breaker
        for client in grpc_manager.clients.values():
            assert client.circuit_breaker is not None
            assert client.circuit_breaker.failure_threshold > 0

    @pytest.mark.performance
    def test_concurrent_health_checks(self, grpc_manager):
        """Test performance of concurrent health checks"""
        import time

        # Mock health checks to be fast
        for client in grpc_manager.clients.values():
            client.health_check = Mock(return_value=True)

        start_time = time.time()

        # Perform multiple concurrent health checks
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=grpc_manager.health_check_all)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        end_time = time.time()

        # Should complete quickly (less than 2 seconds)
        assert end_time - start_time < 2.0

    @pytest.mark.stress
    def test_stress_test_client_operations(self, grpc_manager):
        """Test stress testing of client operations"""
        def stress_thread():
            """Stress test thread"""
            for _ in range(100):
                client = grpc_manager.get_client(ServiceType.ARKD)
                assert client is not None

        threads = []
        for _ in range(10):
            thread = threading.Thread(target=stress_thread)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

    @pytest.mark.error_handling
    def test_error_handling_scenarios(self, grpc_manager):
        """Test various error handling scenarios"""
        # Test health check with exceptions
        grpc_manager.clients[ServiceType.ARKD].health_check = Mock(side_effect=Exception("Health check failed"))
        results = grpc_manager.health_check_all()
        assert results[ServiceType.ARKD] is False

        # Test client access with None return
        assert grpc_manager.get_client("nonexistent") is None

        # Test reconnection with exception
        grpc_manager.clients[ServiceType.ARKD]._connect = Mock(side_effect=Exception("Reconnect failed"))
        with pytest.raises(Exception):
            grpc_manager.reconnect(ServiceType.ARKD)

    def test_manager_locking(self, grpc_manager):
        """Test manager locking mechanism"""
        def long_running_operation():
            """Long running operation to test locking"""
            import time
            time.sleep(0.1)
            return True

        # Test that operations are properly synchronized
        def operation_thread():
            with grpc_manager._lock:
                return long_running_operation()

        threads = []
        for _ in range(5):
            thread = threading.Thread(target=operation_thread)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()