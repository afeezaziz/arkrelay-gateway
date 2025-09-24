"""
Enhanced load testing scenarios for Ark Relay Gateway
"""

import pytest
import time
import threading
import asyncio
import queue
import statistics
import json
from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Any

from core.config import Config

# Import test database setup to enable patching
from tests.test_database_setup import *


class TestLoadTesting:
    """Enhanced load testing suite for Ark Relay Gateway"""

    @pytest.fixture
    def load_test_config(self):
        """Load test configuration"""
        return {
            'ramp_up_time': 30,  # seconds
            'steady_state_time': 120,  # seconds
            'ramp_down_time': 30,  # seconds
            'max_users': 1000,
            'think_time': 1,  # seconds between requests
            'error_rate_threshold': 0.05,  # 5% error rate max
            'response_time_p95_threshold': 2.0,  # 2 seconds
            'throughput_threshold': 100,  # requests per second
            'memory_limit_mb': 512,
            'cpu_limit_percent': 90
        }

    @pytest.fixture
    def mock_core_services(self):
        """Mock core services for load testing"""
        with patch('grpc_clients.arkd_client.ArkdClient') as mock_arkd, \
             patch('grpc_clients.lnd_client.LndClient') as mock_lnd, \
             patch('grpc_clients.tapd_client.TapdClient') as mock_tapd, \
             patch('core.session_manager.SigningSessionManager') as mock_session, \
             patch('core.asset_manager.AssetManager') as mock_asset, \
             patch('core.transaction_processor.TransactionProcessor') as mock_tx_processor, \
             patch('core.signing_orchestrator.SigningOrchestrator') as mock_orchestrator:

            # Configure high-performance mocks
            for mock_client in [mock_arkd, mock_lnd, mock_tapd]:
                client = Mock()
                client.health_check.return_value = True
                mock_client.return_value = client

            # Configure ARKD mock with VTXO operations
            arkd_mock = mock_arkd.return_value
            arkd_mock.create_vtxos.return_value = {
                'tx_id': f'tx_{time.time()}',
                'vtxos': [{'id': f'vtxo_{i}', 'amount': 1000} for i in range(2)]
            }
            arkd_mock.list_vtxos.return_value = []
            arkd_mock.get_vtxo_status.return_value = {'status': 'confirmed'}

            # Configure LND mock with payment operations
            lnd_mock = mock_lnd.return_value
            lnd_mock.add_invoice.return_value = {'payment_request': f'lnbc{time.time()}'}
            lnd_mock.send_payment.return_value = {'status': 'complete', 'fee_msat': 1000}
            lnd_mock.get_balance.return_value = {'confirmed_balance': 1000000}

            # Configure TAPD mock with asset operations
            tapd_mock = mock_tapd.return_value
            tapd_mock.list_assets.return_value = []
            tapd_mock.mint_asset.return_value = {'asset_id': f'asset_{time.time()}'}
            tapd_mock.transfer_asset.return_value = {'tx_id': f'tx_{time.time()}'}

            # Configure session manager
            session_mock = mock_session.return_value
            session_mock.create_signing_session.return_value = {
                'session_id': f'session_{time.time()}',
                'status': 'created'
            }
            session_mock.get_session.return_value = {
                'session_id': 'test_session',
                'status': 'active'
            }

            # Configure asset manager
            asset_mock = mock_asset.return_value
            asset_mock.mint_assets.return_value = [{'asset_id': 'test_asset', 'amount': 1000}]
            asset_mock.get_user_balance.return_value = 10000

            # Configure transaction processor
            tx_processor_mock = mock_tx_processor.return_value
            tx_processor_mock.process_p2p_transfer.return_value = {
                'tx_id': f'tx_{time.time()}',
                'status': 'completed'
            }
            tx_processor_mock.validate_transaction.return_value = True

            # Configure signing orchestrator
            orchestrator_mock = mock_orchestrator.return_value
            orchestrator_mock.start_signing_ceremony.return_value = {
                'session_id': 'test_session',
                'status': 'in_progress'
            }
            orchestrator_mock.execute_signing_step.return_value = True

            yield {
                'arkd': arkd_mock,
                'lnd': lnd_mock,
                'tapd': tapd_mock,
                'session': session_mock,
                'asset': asset_mock,
                'tx_processor': tx_processor_mock,
                'orchestrator': orchestrator_mock
            }

    @pytest.mark.load
    def test_ramp_up_load_test(self, load_test_config, mock_core_services):
        """Test system behavior during ramp-up phase"""
        results = []
        start_time = time.time()
        ramp_up_end = start_time + load_test_config['ramp_up_time']

        def simulate_user(user_id: int, result_queue: queue.Queue):
            """Simulate a user during ramp-up"""
            try:
                # Calculate when this user should start based on ramp-up
                user_start_time = start_time + (user_id / load_test_config['max_users']) * load_test_config['ramp_up_time']

                # Wait for scheduled start time
                wait_time = user_start_time - time.time()
                if wait_time > 0:
                    time.sleep(wait_time)

                # Perform user operations
                operation_start = time.time()

                # Create signing session
                mock_core_services['session'].create_signing_session(
                    f'user_{user_id}',
                    {'type': 'transfer', 'amount': 10000},
                    f'Test transfer {user_id}'
                )

                # Create VTXOs
                mock_core_services['arkd'].create_vtxos(100000, 'gbtc')

                # Add invoice
                mock_core_services['lnd'].add_invoice(100000)

                operation_end = time.time()
                response_time = operation_end - operation_start

                result_queue.put({
                    'user_id': user_id,
                    'start_time': operation_start,
                    'end_time': operation_end,
                    'response_time': response_time,
                    'success': True
                })

            except Exception as e:
                result_queue.put({
                    'user_id': user_id,
                    'error': str(e),
                    'success': False
                })

        # Start user simulation threads
        result_queue = queue.Queue()
        threads = []

        for user_id in range(load_test_config['max_users']):
            thread = threading.Thread(target=simulate_user, args=(user_id, result_queue))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Collect results
        while not result_queue.empty():
            results.append(result_queue.get())

        # Analyze results
        successful_requests = [r for r in results if r['success']]
        failed_requests = [r for r in results if not r['success']]

        success_rate = len(successful_requests) / len(results) if results else 0
        avg_response_time = statistics.mean([r['response_time'] for r in successful_requests]) if successful_requests else 0
        p95_response_time = statistics.quantiles([r['response_time'] for r in successful_requests], n=20)[18] if len(successful_requests) >= 20 else avg_response_time

        # Load test assertions
        assert success_rate > (1 - load_test_config['error_rate_threshold'])
        assert avg_response_time < load_test_config['response_time_p95_threshold']
        assert p95_response_time < load_test_config['response_time_p95_threshold'] * 2

    @pytest.mark.load
    def test_steady_state_load_test(self, load_test_config, mock_core_services):
        """Test system under steady-state load"""
        results = []
        start_time = time.time()
        end_time = start_time + load_test_config['steady_state_time']

        def steady_state_worker(worker_id: int, result_queue: queue.Queue):
            """Worker for steady-state load testing"""
            while time.time() < end_time:
                try:
                    operation_start = time.time()

                    # Simulate realistic user workflow
                    workflow_operations = [
                        lambda: mock_core_services['session'].create_signing_session(
                            f'user_{worker_id}_{int(time.time())}',
                            {'type': 'transfer', 'amount': 10000},
                            f'Steady state transfer {worker_id}'
                        ),
                        lambda: mock_core_services['arkd'].create_vtxos(100000, 'gbtc'),
                        lambda: mock_core_services['lnd'].add_invoice(100000),
                        lambda: mock_core_services['asset'].get_user_balance(f'user_{worker_id}'),
                        lambda: mock_core_services['tx_processor'].validate_transaction(
                            'test_tx_data', 1000, 'test_pubkey'
                        )
                    ]

                    # Execute random operation
                    import random
                    operation = random.choice(workflow_operations)
                    operation()

                    operation_end = time.time()
                    response_time = operation_end - operation_start

                    result_queue.put({
                        'worker_id': worker_id,
                        'timestamp': operation_start,
                        'response_time': response_time,
                        'success': True
                    })

                    # Think time
                    time.sleep(load_test_config['think_time'])

                except Exception as e:
                    result_queue.put({
                        'worker_id': worker_id,
                        'timestamp': time.time(),
                        'error': str(e),
                        'success': False
                    })

        # Start steady-state workers
        result_queue = queue.Queue()
        threads = []
        num_workers = min(50, load_test_config['max_users'] // 10)  # Use subset for steady state

        for worker_id in range(num_workers):
            thread = threading.Thread(target=steady_state_worker, args=(worker_id, result_queue))
            threads.append(thread)
            thread.start()

        # Wait for steady state period
        time.sleep(load_test_config['steady_state_time'])

        # Signal threads to stop (they check end_time)
        for thread in threads:
            thread.join(timeout=5)

        # Collect results
        while not result_queue.empty():
            results.append(result_queue.get())

        # Analyze steady-state performance
        successful_requests = [r for r in results if r['success']]
        failed_requests = [r for r in results if not r['success']]

        if successful_requests:
            response_times = [r['response_time'] for r in successful_requests]
            avg_response_time = statistics.mean(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else avg_response_time
            p99_response_time = statistics.quantiles(response_times, n=100)[98] if len(response_times) >= 100 else avg_response_time

            # Calculate throughput (requests per second)
            total_time = load_test_config['steady_state_time']
            throughput = len(successful_requests) / total_time

            # Calculate error rate
            error_rate = len(failed_requests) / len(results) if results else 0

            # Steady-state assertions
            assert error_rate < load_test_config['error_rate_threshold']
            assert avg_response_time < load_test_config['response_time_p95_threshold']
            assert p95_response_time < load_test_config['response_time_p95_threshold'] * 2
            assert p99_response_time < load_test_config['response_time_p95_threshold'] * 3
            assert throughput > load_test_config['throughput_threshold']

    @pytest.mark.load
    def test_spike_load_test(self, load_test_config, mock_core_services):
        """Test system behavior under sudden spike load"""
        baseline_users = 10
        spike_users = 100
        spike_duration = 60  # seconds

        results = []
        start_time = time.time()
        spike_start = start_time + 30  # Start spike after 30 seconds
        spike_end = spike_start + spike_duration

        def baseline_user(user_id: int, result_queue: queue.Queue):
            """Simulate baseline user activity"""
            while time.time() < spike_end + 30:  # Continue after spike
                try:
                    operation_start = time.time()

                    # Normal operations
                    mock_core_services['session'].create_signing_session(
                        f'baseline_user_{user_id}',
                        {'type': 'transfer', 'amount': 1000},
                        f'Baseline transfer {user_id}'
                    )
                    mock_core_services['arkd'].health_check()

                    operation_end = time.time()
                    response_time = operation_end - operation_start

                    result_queue.put({
                        'user_type': 'baseline',
                        'timestamp': operation_start,
                        'response_time': response_time,
                        'success': True
                    })

                    time.sleep(2)  # Baseline users are less active

                except Exception as e:
                    result_queue.put({
                        'user_type': 'baseline',
                        'timestamp': time.time(),
                        'error': str(e),
                        'success': False
                    })

        def spike_user(user_id: int, result_queue: queue.Queue):
            """Simulate spike user activity"""
            # Wait for spike start
            wait_time = spike_start - time.time()
            if wait_time > 0:
                time.sleep(wait_time)

            # Intensive activity during spike
            while time.time() < spike_end:
                try:
                    operation_start = time.time()

                    # High-intensity operations
                    mock_core_services['session'].create_signing_session(
                        f'spike_user_{user_id}',
                        {'type': 'transfer', 'amount': 50000},
                        f'Spike transfer {user_id}'
                    )
                    mock_core_services['arkd'].create_vtxos(250000, 'gbtc')
                    mock_core_services['lnd'].add_invoice(250000)
                    mock_core_services['tx_processor'].process_p2p_transfer(f'session_{user_id}')

                    operation_end = time.time()
                    response_time = operation_end - operation_start

                    result_queue.put({
                        'user_type': 'spike',
                        'timestamp': operation_start,
                        'response_time': response_time,
                        'success': True
                    })

                    time.sleep(0.5)  # Spike users are very active

                except Exception as e:
                    result_queue.put({
                        'user_type': 'spike',
                        'timestamp': time.time(),
                        'error': str(e),
                        'success': False
                    })

        # Start baseline users
        result_queue = queue.Queue()
        threads = []

        for user_id in range(baseline_users):
            thread = threading.Thread(target=baseline_user, args=(user_id, result_queue))
            threads.append(thread)
            thread.start()

        # Start spike users
        for user_id in range(spike_users):
            thread = threading.Thread(target=spike_user, args=(user_id, result_queue))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Collect and analyze results
        while not result_queue.empty():
            results.append(result_queue.get())

        baseline_results = [r for r in results if r['user_type'] == 'baseline']
        spike_results = [r for r in results if r['user_type'] == 'spike']

        # Analyze baseline performance before, during, and after spike
        baseline_before_spike = [r for r in baseline_results if r['timestamp'] < spike_start]
        baseline_during_spike = [r for r in baseline_results if spike_start <= r['timestamp'] < spike_end]
        baseline_after_spike = [r for r in baseline_results if r['timestamp'] >= spike_end]

        if baseline_before_spike and baseline_during_spike:
            before_avg = statistics.mean([r['response_time'] for r in baseline_before_spike if r['success']])
            during_avg = statistics.mean([r['response_time'] for r in baseline_during_spike if r['success']])

            # Baseline performance should not degrade significantly during spike
            performance_degradation = during_avg / before_avg if before_avg > 0 else 1
            assert performance_degradation < 3.0  # Performance should not degrade more than 3x

    @pytest.mark.load
    def test_sustained_load_test(self, load_test_config, mock_core_services):
        """Test system under sustained high load"""
        duration = 300  # 5 minutes
        concurrent_users = 100

        results = []
        start_time = time.time()
        end_time = start_time + duration

        def sustained_worker(worker_id: int, result_queue: queue.Queue):
            """Worker for sustained load testing"""
            operations_count = 0

            while time.time() < end_time:
                try:
                    operation_start = time.time()

                    # Complex workflow to stress the system
                    mock_core_services['session'].create_signing_session(
                        f'sustained_user_{worker_id}',
                        {'type': 'transfer', 'amount': 15000},
                        f'Sustained transfer {worker_id}'
                    )
                    mock_core_services['arkd'].create_vtxos(200000, 'gbtc')
                    mock_core_services['lnd'].add_invoice(200000)
                    mock_core_services['asset'].mint_assets(f'user_{worker_id}', 'BTC', 1000)
                    mock_core_services['tx_processor'].validate_transaction(
                        'sustained_tx_data', 15000, 'test_pubkey'
                    )
                    mock_core_services['orchestrator'].start_signing_ceremony(f'session_{worker_id}')

                    operation_end = time.time()
                    response_time = operation_end - operation_start
                    operations_count += 1

                    result_queue.put({
                        'worker_id': worker_id,
                        'timestamp': operation_start,
                        'response_time': response_time,
                        'operations_count': operations_count,
                        'success': True
                    })

                    # Variable think time
                    import random
                    time.sleep(random.uniform(0.5, 1.5))

                except Exception as e:
                    result_queue.put({
                        'worker_id': worker_id,
                        'timestamp': time.time(),
                        'error': str(e),
                        'success': False
                    })

        # Start sustained workers
        result_queue = queue.Queue()
        threads = []

        for worker_id in range(concurrent_users):
            thread = threading.Thread(target=sustained_worker, args=(worker_id, result_queue))
            threads.append(thread)
            thread.start()

        # Wait for sustained period
        time.sleep(duration)

        # Signal threads to stop
        for thread in threads:
            thread.join(timeout=10)

        # Collect results
        while not result_queue.empty():
            results.append(result_queue.get())

        # Analyze sustained load performance
        successful_requests = [r for r in results if r['success']]
        failed_requests = [r for r in results if not r['success']]

        if successful_requests:
            # Analyze performance over time
            time_windows = []
            window_size = 60  # 1 minute windows

            for i in range(0, duration, window_size):
                window_start = start_time + i
                window_end = window_start + window_size
                window_results = [r for r in successful_requests
                                if window_start <= r['timestamp'] < window_end]

                if window_results:
                    window_avg_response = statistics.mean([r['response_time'] for r in window_results])
                    window_throughput = len(window_results) / window_size
                    time_windows.append({
                        'window': i // window_size,
                        'avg_response_time': window_avg_response,
                        'throughput': window_throughput
                    })

            # Check for performance degradation over time
            if len(time_windows) > 1:
                first_window = time_windows[0]
                last_window = time_windows[-1]

                # Response time should not degrade significantly
                response_degradation = last_window['avg_response_time'] / first_window['avg_response_time']
                assert response_degradation < 2.0  # Response time should not double

                # Throughput should remain relatively stable
                throughput_degradation = first_window['throughput'] / last_window['throughput'] if last_window['throughput'] > 0 else 1
                assert throughput_degradation < 2.0  # Throughput should not halve

            # Overall performance metrics
            overall_success_rate = len(successful_requests) / len(results) if results else 0
            assert overall_success_rate > (1 - load_test_config['error_rate_threshold'])

    @pytest.mark.load
    def test_memory_leak_under_load(self, load_test_config, mock_core_services):
        """Test for memory leaks under sustained load"""
        import psutil
        import gc

        process = psutil.Process()
        initial_memory = process.memory_info().rss

        # Sustained load to detect memory leaks
        duration = 120  # 2 minutes
        start_time = time.time()

        def memory_stress_worker(result_queue: queue.Queue):
            """Worker that creates objects to test memory management"""
            objects_created = []

            while time.time() < start_time + duration:
                try:
                    # Create objects and perform operations
                    session_result = mock_core_services['session'].create_signing_session(
                        f'memory_user_{int(time.time())}',
                        {'type': 'transfer', 'amount': 10000},
                        f'Memory test transfer'
                    )
                    objects_created.append(session_result)

                    vtxo_result = mock_core_services['arkd'].create_vtxos(100000, 'gbtc')
                    objects_created.append(vtxo_result)

                    # Periodically clean up
                    if len(objects_created) > 100:
                        objects_created.clear()
                        gc.collect()

                    time.sleep(0.1)

                except Exception as e:
                    result_queue.put({'error': str(e)})
                    break

        # Start memory stress workers
        result_queue = queue.Queue()
        threads = []
        num_workers = 10

        for _ in range(num_workers):
            thread = threading.Thread(target=memory_stress_worker, args=(result_queue,))
            threads.append(thread)
            thread.start()

        # Monitor memory during test
        memory_samples = []
        sample_interval = 10  # Sample every 10 seconds

        while time.time() < start_time + duration:
            current_memory = process.memory_info().rss
            memory_samples.append({
                'timestamp': time.time(),
                'memory_usage': current_memory,
                'memory_increase': current_memory - initial_memory
            })
            time.sleep(sample_interval)

        # Wait for threads to complete
        for thread in threads:
            thread.join()

        # Force garbage collection
        gc.collect()
        final_memory = process.memory_info().rss

        # Analyze memory usage
        memory_increases = [sample['memory_increase'] for sample in memory_samples]
        max_memory_increase = max(memory_increases) if memory_increases else 0
        final_memory_increase = final_memory - initial_memory

        # Memory leak assertions
        assert max_memory_increase < load_test_config['memory_limit_mb'] * 1024 * 1024
        assert final_memory_increase < load_test_config['memory_limit_mb'] * 1024 * 1024 * 0.5  # Should recover after GC

        # Check for steady memory growth (potential leak)
        if len(memory_samples) > 5:
            # Calculate trend
            recent_samples = memory_samples[-5:]
            trend_slope = (recent_samples[-1]['memory_increase'] - recent_samples[0]['memory_increase']) / len(recent_samples)
            assert trend_slope < 1024 * 1024  # Memory growth should be less than 1MB per sample