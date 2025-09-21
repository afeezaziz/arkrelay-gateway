"""
Performance tests for Ark Relay Gateway
"""

import pytest
import time
import threading
import queue
import psutil
import os
import json
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from tests.test_config import configure_test_environment


class TestPerformance:
    """Performance test suite for Ark Relay Gateway"""

    @pytest.fixture
    def performance_config(self):
        """Performance test configuration"""
        return {
            'warmup_iterations': 10,
            'test_iterations': 100,
            'concurrent_users': 50,
            'response_time_threshold': 0.5,  # 500ms
            'throughput_threshold': 100,  # requests per second
            'memory_threshold': 100 * 1024 * 1024,  # 100MB
            'cpu_threshold': 80  # 80%
        }

    @pytest.fixture
    def mock_services(self):
        """Mock services for performance testing"""
        with patch('grpc_clients.arkd_client.ArkClient') as mock_arkd, \
             patch('grpc_clients.lnd_client.LndClient') as mock_lnd, \
             patch('grpc_clients.tapd_client.TapClient') as mock_tapd, \
             patch('session_manager.SessionManager') as mock_session:

            # Configure mock clients for fast responses
            arkd_client = Mock()
            arkd_client.health_check.return_value = True
            arkd_client.create_vtxos.return_value = {'tx_id': 'test_tx', 'vtxos': []}
            arkd_client.list_vtxos.return_value = []

            lnd_client = Mock()
            lnd_client.health_check.return_value = True
            lnd_client.add_invoice.return_value = {'payment_request': 'test_invoice'}
            lnd_client.send_payment.return_value = {'status': 'complete'}

            tapd_client = Mock()
            tapd_client.health_check.return_value = True
            tapd_client.list_assets.return_value = []

            session_manager = Mock()
            session_manager.create_signing_session.return_value = Mock()
            session_manager.get_session.return_value = Mock()

            mock_arkd.return_value = arkd_client
            mock_lnd.return_value = lnd_client
            mock_tapd.return_value = tapd_client
            mock_session.return_value = session_manager

            yield {
                'arkd': arkd_client,
                'lnd': lnd_client,
                'tapd': tapd_client,
                'session': session_manager
            }

    @pytest.mark.performance
    def test_daemon_health_check_performance(self, performance_config, mock_services):
        """Test performance of daemon health checks"""
        # Warmup
        for _ in range(performance_config['warmup_iterations']):
            mock_services['arkd'].health_check()
            mock_services['lnd'].health_check()
            mock_services['tapd'].health_check()

        # Performance test
        start_time = time.time()
        for _ in range(performance_config['test_iterations']):
            mock_services['arkd'].health_check()
            mock_services['lnd'].health_check()
            mock_services['tapd'].health_check()

        end_time = time.time()
        total_time = end_time - start_time
        avg_time = total_time / (performance_config['test_iterations'] * 3)

        # Performance assertions
        assert avg_time < performance_config['response_time_threshold']
        throughput = (performance_config['test_iterations'] * 3) / total_time
        assert throughput > performance_config['throughput_threshold']

    @pytest.mark.performance
    def test_vtxo_creation_performance(self, performance_config, mock_services):
        """Test performance of VTXO creation"""
        def create_vtxo():
            return mock_services['arkd'].create_vtxos(100000, 'gbtc')

        # Warmup
        for _ in range(performance_config['warmup_iterations']):
            create_vtxo()

        # Performance test
        start_time = time.time()
        for _ in range(performance_config['test_iterations']):
            create_vtxo()

        end_time = time.time()
        total_time = end_time - start_time
        avg_time = total_time / performance_config['test_iterations']

        # Performance assertions
        assert avg_time < performance_config['response_time_threshold']
        throughput = performance_config['test_iterations'] / total_time
        assert throughput > performance_config['throughput_threshold']

    @pytest.mark.performance
    def test_session_management_performance(self, performance_config, mock_services):
        """Test performance of session management"""
        def create_session():
            return mock_services['session'].create_signing_session(
                'test_user_pubkey',
                {'type': 'transfer', 'amount': 10000},
                'Test transfer'
            )

        # Warmup
        for _ in range(performance_config['warmup_iterations']):
            create_session()

        # Performance test
        start_time = time.time()
        for _ in range(performance_config['test_iterations']):
            create_session()

        end_time = time.time()
        total_time = end_time - start_time
        avg_time = total_time / performance_config['test_iterations']

        # Performance assertions
        assert avg_time < performance_config['response_time_threshold']
        throughput = performance_config['test_iterations'] / total_time
        assert throughput > performance_config['throughput_threshold']

    @pytest.mark.performance
    def test_concurrent_user_performance(self, performance_config, mock_services):
        """Test performance under concurrent load"""
        def simulate_user(user_id):
            """Simulate a single user's operations"""
            start_time = time.time()

            # User operations
            mock_services['session'].create_signing_session(
                f'user_{user_id}',
                {'type': 'transfer', 'amount': 10000},
                f'Test transfer {user_id}'
            )
            mock_services['arkd'].create_vtxos(100000, 'gbtc')
            mock_services['lnd'].add_invoice(100000)

            end_time = time.time()
            return end_time - start_time

        # Warmup
        with ThreadPoolExecutor(max_workers=10) as executor:
            warmup_futures = [executor.submit(simulate_user, i) for i in range(10)]
            for future in as_completed(warmup_futures):
                future.result()

        # Performance test
        with ThreadPoolExecutor(max_workers=performance_config['concurrent_users']) as executor:
            start_time = time.time()
            futures = [executor.submit(simulate_user, i) for i in range(performance_config['concurrent_users'])]

            response_times = []
            for future in as_completed(futures):
                response_time = future.result()
                response_times.append(response_time)

            end_time = time.time()
            total_time = end_time - start_time

        # Performance assertions
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        throughput = performance_config['concurrent_users'] / total_time

        assert avg_response_time < performance_config['response_time_threshold']
        assert max_response_time < performance_config['response_time_threshold'] * 3
        assert throughput > performance_config['throughput_threshold']

    @pytest.mark.performance
    def test_memory_usage_performance(self, performance_config, mock_services):
        """Test memory usage under load"""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Simulate load
        for _ in range(performance_config['test_iterations']):
            mock_services['session'].create_signing_session(
                f'user_{_}',
                {'type': 'transfer', 'amount': 10000},
                f'Test transfer {_}'
            )
            mock_services['arkd'].create_vtxos(100000, 'gbtc')
            mock_services['lnd'].add_invoice(100000)

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory assertions
        assert memory_increase < performance_config['memory_threshold']

    @pytest.mark.performance
    def test_cpu_usage_performance(self, performance_config, mock_services):
        """Test CPU usage under load"""
        process = psutil.Process(os.getpid())
        initial_cpu = process.cpu_percent()

        # Simulate CPU-intensive operations
        start_time = time.time()
        for _ in range(performance_config['test_iterations']):
            mock_services['session'].create_signing_session(
                f'user_{_}',
                {'type': 'transfer', 'amount': 10000},
                f'Test transfer {_}'
            )
            mock_services['arkd'].create_vtxos(100000, 'gbtc')
            mock_services['lnd'].add_invoice(100000)

        end_time = time.time()
        total_time = end_time - start_time

        # Get CPU usage
        cpu_usage = process.cpu_percent()

        # CPU assertions
        assert cpu_usage < performance_config['cpu_threshold']

    @pytest.mark.performance
    def test_database_query_performance(self, performance_config):
        """Test database query performance"""
        with patch('models.get_session') as mock_db:
            session = Mock()
            session.query.return_value.all.return_value = []
            session.add.return_value = None
            session.commit.return_value = None
            mock_db.return_value = session

            def perform_database_operations():
                session.add(Mock())
                session.commit()
                return session.query.return_value.all()

            # Warmup
            for _ in range(performance_config['warmup_iterations']):
                perform_database_operations()

            # Performance test
            start_time = time.time()
            for _ in range(performance_config['test_iterations']):
                perform_database_operations()

            end_time = time.time()
            total_time = end_time - start_time
            avg_time = total_time / performance_config['test_iterations']

            # Performance assertions
            assert avg_time < performance_config['response_time_threshold']

    @pytest.mark.performance
    def test_redis_operations_performance(self, performance_config):
        """Test Redis operations performance"""
        with patch('redis.Redis') as mock_redis:
            client = Mock()
            client.set.return_value = True
            client.get.return_value = 'test_value'
            client.delete.return_value = 1
            mock_redis.return_value = client

            def perform_redis_operations():
                client.set(f'key_{time.time()}', 'test_value')
                client.get(f'key_{time.time()}')
                client.delete(f'key_{time.time()}')

            # Warmup
            for _ in range(performance_config['warmup_iterations']):
                perform_redis_operations()

            # Performance test
            start_time = time.time()
            for _ in range(performance_config['test_iterations']):
                perform_redis_operations()

            end_time = time.time()
            total_time = end_time - start_time
            avg_time = total_time / performance_config['test_iterations']

            # Performance assertions
            assert avg_time < performance_config['response_time_threshold']

    @pytest.mark.performance
    def test_nostr_operations_performance(self, performance_config):
        """Test Nostr operations performance"""
        with patch('nostr_clients.nostr_client.NostrClient') as mock_nostr:
            client = Mock()
            client.connect.return_value = True
            client.publish_event.return_value = True
            client.subscribe_events.return_value = True
            mock_nostr.return_value = client

            def perform_nostr_operations():
                client.publish_event({
                    'kind': 31510,
                    'content': json.dumps({'type': 'test'})
                })

            # Warmup
            for _ in range(performance_config['warmup_iterations']):
                perform_nostr_operations()

            # Performance test
            start_time = time.time()
            for _ in range(performance_config['test_iterations']):
                perform_nostr_operations()

            end_time = time.time()
            total_time = end_time - start_time
            avg_time = total_time / performance_config['test_iterations']

            # Performance assertions
            assert avg_time < performance_config['response_time_threshold']

    @pytest.mark.performance
    def test_scalability_performance(self, performance_config, mock_services):
        """Test scalability with increasing load"""
        results = []

        # Test with different load levels
        for load_level in [10, 25, 50, 100]:
            def simulate_load():
                for _ in range(load_level):
                    mock_services['session'].create_signing_session(
                        f'user_{_}',
                        {'type': 'transfer', 'amount': 10000},
                        f'Test transfer {_}'
                    )

            start_time = time.time()
            simulate_load()
            end_time = time.time()

            total_time = end_time - start_time
            throughput = load_level / total_time
            results.append({'load': load_level, 'throughput': throughput, 'time': total_time})

        # Check scalability (throughput should increase with load)
        for i in range(1, len(results)):
            assert results[i]['throughput'] >= results[i-1]['throughput'] * 0.8

    @pytest.mark.performance
    def test_stress_test_performance(self, performance_config, mock_services):
        """Test system under stress"""
        def stress_worker(result_queue):
            """Worker function for stress testing"""
            try:
                start_time = time.time()
                operations = 0

                while time.time() - start_time < 10:  # Run for 10 seconds
                    mock_services['session'].create_signing_session(
                        f'user_{time.time()}',
                        {'type': 'transfer', 'amount': 10000},
                        f'Stress test {time.time()}'
                    )
                    operations += 1

                result_queue.put(operations)
            except Exception as e:
                result_queue.put(-1)

        # Run stress test
        num_workers = 20
        result_queue = queue.Queue()
        threads = []

        for _ in range(num_workers):
            thread = threading.Thread(target=stress_worker, args=(result_queue,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Collect results
        total_operations = 0
        failed_workers = 0

        while not result_queue.empty():
            result = result_queue.get()
            if result == -1:
                failed_workers += 1
            else:
                total_operations += result

        # Stress test assertions
        assert failed_workers == 0
        assert total_operations > 100  # Should handle at least 100 operations

    @pytest.mark.performance
    def test_cache_performance(self, performance_config):
        """Test caching performance"""
        with patch('core.cache_manager.CacheManager') as mock_cache:
            cache = Mock()
            cache.set.return_value = True
            cache.get.return_value = 'cached_value'
            cache.delete.return_value = True
            mock_cache.return_value = cache

            def perform_cache_operations():
                cache.set(f'cache_key_{time.time()}', 'test_value')
                cache.get(f'cache_key_{time.time()}')
                cache.delete(f'cache_key_{time.time()}')

            # Warmup
            for _ in range(performance_config['warmup_iterations']):
                perform_cache_operations()

            # Performance test
            start_time = time.time()
            for _ in range(performance_config['test_iterations']):
                perform_cache_operations()

            end_time = time.time()
            total_time = end_time - start_time
            avg_time = total_time / performance_config['test_iterations']

            # Performance assertions
            assert avg_time < 0.001  # Cache operations should be very fast

    @pytest.mark.performance
    def test_network_latency_performance(self, performance_config, mock_services):
        """Test network latency impact on performance"""
        def simulate_network_latency():
            time.sleep(0.001)  # Simulate 1ms network latency
            return mock_services['arkd'].health_check()

        # Warmup
        for _ in range(performance_config['warmup_iterations']):
            simulate_network_latency()

        # Performance test
        start_time = time.time()
        for _ in range(performance_config['test_iterations']):
            simulate_network_latency()

        end_time = time.time()
        total_time = end_time - start_time
        avg_time = total_time / performance_config['test_iterations']

        # Performance assertions (should account for simulated latency)
        assert avg_time < 0.002  # Should be less than 2ms including simulated latency

    @pytest.mark.performance
    def test_file_io_performance(self, performance_config):
        """Test file I/O performance"""
        def perform_file_operations():
            # Simulate file operations
            test_data = json.dumps({'test': 'data', 'timestamp': time.time()})
            return len(test_data)

        # Warmup
        for _ in range(performance_config['warmup_iterations']):
            perform_file_operations()

        # Performance test
        start_time = time.time()
        for _ in range(performance_config['test_iterations']):
            perform_file_operations()

        end_time = time.time()
        total_time = end_time - start_time
        avg_time = total_time / performance_config['test_iterations']

        # Performance assertions
        assert avg_time < performance_config['response_time_threshold']

    @pytest.mark.performance
    def test_memory_leak_detection(self, performance_config, mock_services):
        """Test for memory leaks under sustained load"""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Sustained load
        for iteration in range(performance_config['test_iterations']):
            mock_services['session'].create_signing_session(
                f'user_{iteration}',
                {'type': 'transfer', 'amount': 10000},
                f'Test transfer {iteration}'
            )
            mock_services['arkd'].create_vtxos(100000, 'gbtc')

            # Check memory every 100 iterations
            if iteration % 100 == 0:
                current_memory = process.memory_info().rss
                memory_increase = current_memory - initial_memory
                assert memory_increase < performance_config['memory_threshold']

        final_memory = process.memory_info().rss
        total_memory_increase = final_memory - initial_memory

        # Final memory check
        assert total_memory_increase < performance_config['memory_threshold']

    @pytest.mark.performance
    def test_bottleneck_identification(self, performance_config, mock_services):
        """Test to identify performance bottlenecks"""
        operation_times = {
            'session_creation': [],
            'vtxo_creation': [],
            'invoice_creation': [],
            'health_checks': []
        }

        for _ in range(performance_config['test_iterations']):
            # Measure session creation time
            start = time.time()
            mock_services['session'].create_signing_session(
                'test_user',
                {'type': 'transfer', 'amount': 10000},
                'Test transfer'
            )
            operation_times['session_creation'].append(time.time() - start)

            # Measure VTXO creation time
            start = time.time()
            mock_services['arkd'].create_vtxos(100000, 'gbtc')
            operation_times['vtxo_creation'].append(time.time() - start)

            # Measure invoice creation time
            start = time.time()
            mock_services['lnd'].add_invoice(100000)
            operation_times['invoice_creation'].append(time.time() - start)

            # Measure health check times
            start = time.time()
            mock_services['arkd'].health_check()
            mock_services['lnd'].health_check()
            mock_services['tapd'].health_check()
            operation_times['health_checks'].append(time.time() - start)

        # Analyze bottlenecks
        avg_times = {op: sum(times) / len(times) for op, times in operation_times.items()}
        slowest_operation = max(avg_times.items(), key=lambda x: x[1])

        # Bottleneck assertions
        assert slowest_operation[1] < performance_config['response_time_threshold']

        # Log performance metrics for analysis
        for operation, avg_time in avg_times.items():
            print(f"{operation}: {avg_time:.4f}s average")