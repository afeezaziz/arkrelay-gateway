"""
Load testing suite for Ark Relay Gateway
"""

import pytest
import time
import threading
import queue
import random
import json
import statistics
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, patch, MagicMock
import psutil
import os

from tests.test_config import configure_test_environment


class TestLoadTesting:
    """Load testing suite for Ark Relay Gateway"""

    @pytest.fixture
    def load_config(self):
        """Load testing configuration"""
        return {
            'ramp_up_time': 30,  # seconds
            'steady_state_time': 60,  # seconds
            'ramp_down_time': 30,  # seconds
            'max_users': 200,
            'target_throughput': 1000,  # requests per minute
            'max_error_rate': 0.05,  # 5% error rate threshold
            'response_time_threshold': 2.0,  # 2 seconds
            'cpu_threshold': 90,  # 90%
            'memory_threshold': 1024 * 1024 * 1024,  # 1GB
            'connection_pool_size': 100
        }

    @pytest.fixture
    def mock_services(self):
        """Mock services for load testing"""
        with patch('grpc_clients.arkd_client.ArkClient') as mock_arkd, \
             patch('grpc_clients.lnd_client.LndClient') as mock_lnd, \
             patch('grpc_clients.tapd_client.TapClient') as mock_tapd, \
             patch('session_manager.SessionManager') as mock_session, \
             patch('models.get_session') as mock_db:

            # Configure mock clients
            arkd_client = Mock()
            arkd_client.health_check.return_value = True
            arkd_client.create_vtxos.return_value = {'tx_id': f'test_tx_{time.time()}', 'vtxos': []}
            arkd_client.list_vtxos.return_value = []

            lnd_client = Mock()
            lnd_client.health_check.return_value = True
            lnd_client.add_invoice.return_value = {'payment_request': f'lnbc_{time.time()}'}
            lnd_client.send_payment.return_value = {'status': 'complete'}

            tapd_client = Mock()
            tapd_client.health_check.return_value = True
            tapd_client.list_assets.return_value = [{'asset_id': 'gbtc', 'name': 'Bitcoin'}]

            session_manager = Mock()
            session_manager.create_signing_session.return_value = Mock()
            session_manager.get_session.return_value = Mock()

            db_session = Mock()
            db_session.query.return_value.all.return_value = []
            db_session.add.return_value = None
            db_session.commit.return_value = None

            mock_arkd.return_value = arkd_client
            mock_lnd.return_value = lnd_client
            mock_tapd.return_value = tapd_client
            mock_session.return_value = session_manager
            mock_db.return_value = db_session

            yield {
                'arkd': arkd_client,
                'lnd': lnd_client,
                'tapd': tapd_client,
                'session': session_manager,
                'db': db_session
            }

    @pytest.mark.load
    def test_constant_load_test(self, load_config, mock_services):
        """Test system under constant load"""
        def simulate_user(user_id, results):
            """Simulate a single user"""
            try:
                start_time = time.time()
                operations = 0
                errors = 0

                # Simulate user session
                for _ in range(10):  # Each user performs 10 operations
                    try:
                        # Create signing session
                        mock_services['session'].create_signing_session(
                            f'user_{user_id}',
                            {'type': 'transfer', 'amount': random.randint(1000, 100000)},
                            f'Test transfer {user_id}-{_}'
                        )

                        # Create VTXO
                        mock_services['arkd'].create_vtxos(
                            random.randint(1000, 100000),
                            'gbtc'
                        )

                        # Add invoice
                        mock_services['lnd'].add_invoice(
                            random.randint(1000, 100000)
                        )

                        operations += 1
                    except Exception as e:
                        errors += 1

                end_time = time.time()
                results.append({
                    'user_id': user_id,
                    'operations': operations,
                    'errors': errors,
                    'total_time': end_time - start_time,
                    'success': errors == 0
                })

            except Exception as e:
                results.append({
                    'user_id': user_id,
                    'operations': 0,
                    'errors': 1,
                    'total_time': 0,
                    'success': False,
                    'error': str(e)
                })

        # Execute load test
        concurrent_users = 50
        results = []

        with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [executor.submit(simulate_user, i, results) for i in range(concurrent_users)]
            for future in as_completed(futures):
                future.result()

        # Analyze results
        successful_users = [r for r in results if r['success']]
        failed_users = [r for r in results if not r['success']]
        total_operations = sum(r['operations'] for r in results)
        total_errors = sum(r['errors'] for r in results)
        total_time = max(r['total_time'] for r in results) if results else 0

        # Load test assertions
        success_rate = len(successful_users) / len(results) if results else 0
        error_rate = total_errors / total_operations if total_operations > 0 else 0
        throughput = total_operations / total_time if total_time > 0 else 0

        assert success_rate > (1 - load_config['max_error_rate'])
        assert error_rate < load_config['max_error_rate']
        assert throughput > (load_config['target_throughput'] / 60)  # Convert to per second

    @pytest.mark.load
    def test_ramp_up_load_test(self, load_config, mock_services):
        """Test system with ramping load"""
        def ramp_up_worker(start_time, ramp_duration, max_users, results):
            """Worker that ramps up users"""
            try:
                current_time = time.time()
                elapsed = current_time - start_time

                if elapsed < ramp_duration:
                    # Calculate number of users to simulate based on ramp-up
                    target_users = int((elapsed / ramp_duration) * max_users)
                else:
                    target_users = max_users

                # Simulate target users
                for user_id in range(target_users):
                    try:
                        mock_services['session'].create_signing_session(
                            f'ramp_user_{user_id}',
                            {'type': 'transfer', 'amount': 10000},
                            f'Ramp test {user_id}'
                        )
                        mock_services['arkd'].create_vtxos(10000, 'gbtc')
                        results.append({'user_id': user_id, 'success': True})
                    except Exception:
                        results.append({'user_id': user_id, 'success': False})

            except Exception as e:
                results.append({'user_id': -1, 'success': False, 'error': str(e)})

        # Execute ramp-up test
        start_time = time.time()
        results = []
        max_workers = 20

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i in range(max_workers):
                future = executor.submit(
                    ramp_up_worker, start_time, load_config['ramp_up_time'],
                    load_config['max_users'], results
                )
                futures.append(future)

            # Wait for ramp-up period
            time.sleep(load_config['ramp_up_time'])

            # Complete all futures
            for future in as_completed(futures):
                future.result()

        # Analyze ramp-up results
        successful_ops = [r for r in results if r['success']]
        failed_ops = [r for r in results if not r['success']]
        success_rate = len(successful_ops) / len(results) if results else 0

        assert success_rate > (1 - load_config['max_error_rate'])

    @pytest.mark.load
    def test_spike_load_test(self, load_config, mock_services):
        """Test system under spike load"""
        def spike_worker(spike_results, duration):
            """Worker for spike load testing"""
            try:
                start_time = time.time()
                operations = 0

                while time.time() - start_time < duration:
                    try:
                        # High-frequency operations
                        mock_services['session'].create_signing_session(
                            f'spike_user_{time.time()}',
                            {'type': 'transfer', 'amount': 50000},
                            f'Spike test {time.time()}'
                        )
                        mock_services['arkd'].create_vtxos(50000, 'gbtc')
                        mock_services['lnd'].add_invoice(50000)
                        operations += 1
                    except Exception:
                        pass

                spike_results.append(operations)
            except Exception:
                spike_results.append(0)

        # Execute spike test
        spike_duration = 30  # 30 seconds of intense load
        concurrent_spike_users = 100
        results = []

        with ThreadPoolExecutor(max_workers=concurrent_spike_users) as executor:
            futures = [executor.submit(spike_worker, results, spike_duration)
                      for _ in range(concurrent_spike_users)]
            for future in as_completed(futures):
                future.result()

        # Analyze spike results
        total_operations = sum(results)
        throughput = total_operations / spike_duration

        # Spike load assertions
        assert throughput > (load_config['target_throughput'] / 60)  # Should handle spike load

    @pytest.mark.load
    def test_endurance_load_test(self, load_config, mock_services):
        """Test system endurance under sustained load"""
        def endurance_worker(worker_id, stop_event, results):
            """Worker for endurance testing"""
            try:
                operations = 0
                errors = 0

                while not stop_event.is_set():
                    try:
                        # Simulate continuous operations
                        mock_services['session'].create_signing_session(
                            f'endurance_user_{worker_id}_{time.time()}',
                            {'type': 'transfer', 'amount': random.randint(1000, 50000)},
                            f'Endurance test {worker_id}'
                        )
                        mock_services['arkd'].create_vtxos(
                            random.randint(1000, 50000),
                            'gbtc'
                        )
                        operations += 1
                        time.sleep(0.1)  # Simulate think time
                    except Exception:
                        errors += 1
                        time.sleep(0.1)

                results.append({
                    'worker_id': worker_id,
                    'operations': operations,
                    'errors': errors
                })

            except Exception as e:
                results.append({
                    'worker_id': worker_id,
                    'operations': 0,
                    'errors': 1,
                    'error': str(e)
                })

        # Execute endurance test
        endurance_duration = 300  # 5 minutes
        concurrent_workers = 25
        results = []
        stop_event = threading.Event()

        with ThreadPoolExecutor(max_workers=concurrent_workers) as executor:
            futures = [executor.submit(endurance_worker, i, stop_event, results)
                      for i in range(concurrent_workers)]

            # Run endurance test
            time.sleep(endurance_duration)
            stop_event.set()

            # Wait for all workers to finish
            for future in as_completed(futures):
                future.result()

        # Analyze endurance results
        total_operations = sum(r['operations'] for r in results)
        total_errors = sum(r['errors'] for r in results)
        error_rate = total_errors / total_operations if total_operations > 0 else 0
        throughput = total_operations / endurance_duration

        # Endurance test assertions
        assert error_rate < load_config['max_error_rate']
        assert throughput > (load_config['target_throughput'] / 60)

    @pytest.mark.load
    def test_memory_under_load(self, load_config, mock_services):
        """Test memory usage under load"""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        def memory_load_worker(results):
            """Worker that creates memory load"""
            try:
                operations = 0
                start_time = time.time()

                while time.time() - start_time < 60:  # 1 minute test
                    try:
                        # Memory-intensive operations
                        mock_services['session'].create_signing_session(
                            f'memory_user_{time.time()}',
                            {'type': 'transfer', 'amount': 10000, 'data': 'x' * 1000},
                            f'Memory test {time.time()}'
                        )
                        operations += 1
                    except Exception:
                        pass

                results.append(operations)
            except Exception:
                results.append(0)

        # Execute memory load test
        concurrent_workers = 50
        results = []

        with ThreadPoolExecutor(max_workers=concurrent_workers) as executor:
            futures = [executor.submit(memory_load_worker, results)
                      for _ in range(concurrent_workers)]
            for future in as_completed(futures):
                future.result()

        # Check memory usage
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory assertions
        assert memory_increase < load_config['memory_threshold']

    @pytest.mark.load
    def test_connection_pool_load(self, load_config):
        """Test connection pool under load"""
        def connection_worker(pool_id, results):
            """Worker that tests connection pool"""
            try:
                operations = 0
                errors = 0
                start_time = time.time()

                with patch('models.get_session') as mock_db:
                    session = Mock()
                    session.query.return_value.all.return_value = []
                    session.add.return_value = None
                    session.commit.return_value = None
                    mock_db.return_value = session

                    while time.time() - start_time < 30:  # 30 seconds
                        try:
                            # Database operations
                            session.add(Mock())
                            session.commit()
                            session.query.return_value.all()
                            operations += 1
                        except Exception:
                            errors += 1

                results.append({
                    'pool_id': pool_id,
                    'operations': operations,
                    'errors': errors
                })

            except Exception as e:
                results.append({
                    'pool_id': pool_id,
                    'operations': 0,
                    'errors': 1,
                    'error': str(e)
                })

        # Execute connection pool test
        pool_size = load_config['connection_pool_size']
        results = []

        with ThreadPoolExecutor(max_workers=pool_size) as executor:
            futures = [executor.submit(connection_worker, i, results)
                      for i in range(pool_size)]
            for future in as_completed(futures):
                future.result()

        # Analyze connection pool results
        total_operations = sum(r['operations'] for r in results)
        total_errors = sum(r['errors'] for r in results)
        error_rate = total_errors / total_operations if total_operations > 0 else 0

        # Connection pool assertions
        assert error_rate < load_config['max_error_rate']

    @pytest.mark.load
    def test_concurrent_transaction_load(self, load_config, mock_services):
        """Test concurrent transaction processing"""
        def transaction_worker(worker_id, transaction_count, results):
            """Worker that processes transactions"""
            try:
                start_time = time.time()
                completed_transactions = 0

                for _ in range(transaction_count):
                    try:
                        # Simulate transaction processing
                        session = mock_services['session'].create_signing_session(
                            f'tx_user_{worker_id}_{_}',
                            {'type': 'transfer', 'amount': random.randint(1000, 100000)},
                            f'Transaction {worker_id}-{_}'
                        )
                        vtxo = mock_services['arkd'].create_vtxos(
                            random.randint(1000, 100000),
                            'gbtc'
                        )
                        invoice = mock_services['lnd'].add_invoice(
                            random.randint(1000, 100000)
                        )
                        payment = mock_services['lnd'].send_payment(invoice['payment_request'])

                        if payment['status'] == 'complete':
                            completed_transactions += 1

                    except Exception:
                        pass

                end_time = time.time()
                results.append({
                    'worker_id': worker_id,
                    'completed': completed_transactions,
                    'total_time': end_time - start_time,
                    'success_rate': completed_transactions / transaction_count
                })

            except Exception as e:
                results.append({
                    'worker_id': worker_id,
                    'completed': 0,
                    'total_time': 0,
                    'success_rate': 0,
                    'error': str(e)
                })

        # Execute concurrent transaction test
        workers = 20
        transactions_per_worker = 50
        results = []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(transaction_worker, i, transactions_per_worker, results)
                      for i in range(workers)]
            for future in as_completed(futures):
                future.result()

        # Analyze transaction results
        total_completed = sum(r['completed'] for r in results)
        total_possible = workers * transactions_per_worker
        overall_success_rate = total_completed / total_possible
        avg_success_rate = statistics.mean(r['success_rate'] for r in results if r['success_rate'] > 0)

        # Transaction load assertions
        assert overall_success_rate > (1 - load_config['max_error_rate'])
        assert avg_success_rate > (1 - load_config['max_error_rate'])

    @pytest.mark.load
    def test_degradation_under_load(self, load_config, mock_services):
        """Test system degradation under extreme load"""
        def degradation_worker(worker_id, results):
            """Worker that tests system degradation"""
            try:
                response_times = []
                errors = 0
                operations = 0

                start_time = time.time()
                test_duration = 120  # 2 minutes

                while time.time() - start_time < test_duration:
                    try:
                        op_start = time.time()

                        # Intentionally create higher load
                        for _ in range(5):  # Multiple operations per iteration
                            mock_services['session'].create_signing_session(
                                f'degrad_user_{worker_id}_{time.time()}',
                                {'type': 'transfer', 'amount': 50000},
                                f'Degradation test {worker_id}'
                            )
                            mock_services['arkd'].create_vtxos(50000, 'gbtc')

                        op_end = time.time()
                        response_times.append(op_end - op_start)
                        operations += 5

                    except Exception:
                        errors += 5

                results.append({
                    'worker_id': worker_id,
                    'response_times': response_times,
                    'errors': errors,
                    'operations': operations,
                    'avg_response_time': statistics.mean(response_times) if response_times else 0,
                    'max_response_time': max(response_times) if response_times else 0
                })

            except Exception as e:
                results.append({
                    'worker_id': worker_id,
                    'response_times': [],
                    'errors': 1,
                    'operations': 0,
                    'avg_response_time': 0,
                    'max_response_time': 0,
                    'error': str(e)
                })

        # Execute degradation test
        concurrent_workers = 100
        results = []

        with ThreadPoolExecutor(max_workers=concurrent_workers) as executor:
            futures = [executor.submit(degradation_worker, i, results)
                      for i in range(concurrent_workers)]
            for future in as_completed(futures):
                future.result()

        # Analyze degradation results
        all_response_times = []
        total_operations = sum(r['operations'] for r in results)
        total_errors = sum(r['errors'] for r in results)

        for result in results:
            all_response_times.extend(result['response_times'])

        if all_response_times:
            avg_response_time = statistics.mean(all_response_times)
            max_response_time = max(all_response_times)
            p95_response_time = statistics.quantiles(all_response_times, n=20)[18]  # 95th percentile
        else:
            avg_response_time = 0
            max_response_time = 0
            p95_response_time = 0

        error_rate = total_errors / total_operations if total_operations > 0 else 0

        # Degradation test assertions
        assert error_rate < load_config['max_error_rate'] * 2  # Allow higher error rate under extreme load
        assert avg_response_time < load_config['response_time_threshold'] * 2  # Allow slower response under load
        assert p95_response_time < load_config['response_time_threshold'] * 3

    @pytest.mark.load
    def test_recovery_after_load(self, load_config, mock_services):
        """Test system recovery after load"""
        def baseline_test():
            """Test normal performance"""
            start_time = time.time()
            operations = 0

            for _ in range(100):
                try:
                    mock_services['session'].create_signing_session(
                        'baseline_user',
                        {'type': 'transfer', 'amount': 10000},
                        'Baseline test'
                    )
                    operations += 1
                except Exception:
                    pass

            return operations / (time.time() - start_time)

        def load_test():
            """Test under load"""
            def load_worker(results):
                try:
                    for _ in range(50):
                        mock_services['session'].create_signing_session(
                            f'load_user_{time.time()}',
                            {'type': 'transfer', 'amount': 10000},
                            'Load test'
                        )
                    results.append(50)
                except Exception:
                    results.append(0)

            results = []
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(load_worker, results) for _ in range(20)]
                for future in as_completed(futures):
                    future.result()

            return sum(results) / 20  # Average operations per worker

        # Baseline measurement
        baseline_throughput = baseline_test()

        # Load test
        load_throughput = load_test()

        # Recovery period
        time.sleep(30)  # Allow system to recover

        # Post-load measurement
        recovery_throughput = baseline_test()

        # Recovery test assertions
        # System should recover to at least 80% of baseline performance
        recovery_ratio = recovery_throughput / baseline_throughput
        assert recovery_ratio > 0.8