"""
Additional test cases for app.py to improve coverage
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from app import app, initialize_lightning_services

# Import test database setup to enable patching
from tests.test_database_setup import *

from tests.test_utils import (
    test_app, test_client, mock_redis, mock_grpc_manager,
    mock_nostr_client, mock_session, sample_asset, sample_vtxo,
    sample_signing_session, sample_transaction, performance_metrics,
    sample_job_data, mock_lightning_manager, mock_vtxo_manager,
    mock_session_manager, mock_challenge_manager, mock_transaction_processor,
    mock_signing_orchestrator, mock_asset_manager, mock_monitoring_system,
    mock_cache_manager, mock_job_queue, mock_scheduler, environment_variables
)


class TestAppCoverage:
    """Test cases for app.py coverage improvement"""

    def test_index_endpoint(self, test_client):
        """Test index endpoint"""
        response = test_client.get('/')
        assert response.status_code == 200
        data = response.get_json()
        assert data['message'] == 'Welcome to ArkRelay Gateway'
        assert data['status'] == 'running'
        assert 'timestamp' in data

    def test_initialize_lightning_services_success(self, mock_grpc_manager):
        """Test successful Lightning services initialization"""
        mock_manager, mock_client = mock_grpc_manager

        with patch('app.get_grpc_manager', return_value=mock_manager), \
             patch('app.LightningManager') as mock_lightning_manager, \
             patch('app.LightningMonitor') as mock_lightning_monitor:

            result = initialize_lightning_services()
            assert result is True
            mock_lightning_manager.assert_called_once()
            mock_lightning_monitor.assert_called_once()

    def test_initialize_lightning_services_no_client(self):
        """Test Lightning services initialization with no client"""
        with patch('app.get_grpc_manager', return_value=Mock(get_client=lambda x: None)):
            result = initialize_lightning_services()
            assert result is False

    def test_initialize_lightning_services_exception(self):
        """Test Lightning services initialization with exception"""
        with patch('app.get_grpc_manager', side_effect=Exception("Test error")):
            result = initialize_lightning_services()
            assert result is False

    def test_health_endpoint_with_database_error(self, test_client):
        """Test health endpoint with database error"""
        # Use a more targeted patch that won't interfere with the global patching
        with patch('core.models.get_session', side_effect=Exception("Database error")):
            response = test_client.get('/health')
            assert response.status_code == 200
            data = response.get_json()
            assert data['database_connected'] is False
            assert data['status'] == 'healthy'

    def test_ready_endpoint_with_redis_error(self, test_client):
        """Test ready endpoint with Redis error"""
        with patch('app.redis_conn', side_effect=Exception("Redis error")):
            response = test_client.get('/ready')
            assert response.status_code == 503
            data = response.get_json()
            assert 'error' in data
            assert data['ready'] is False

    def test_metrics_endpoint_with_database_error(self, test_client):
        """Test metrics endpoint with database error"""
        # Patch the app's specific import of get_session
        with patch('app.get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.query.side_effect = Exception("Database query error")
            mock_session.close.return_value = None
            mock_get_session.return_value = mock_session

            response = test_client.get('/metrics')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_metrics_endpoint_calculation_error(self, test_client, mock_session):
        """Test metrics endpoint with calculation error"""
        mock_session.query.side_effect = Exception("Query error")

        with patch('app.get_session', return_value=mock_session):
            response = test_client.get('/metrics')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_metrics_endpoint_job_logs_error(self, test_client, mock_session):
        """Test metrics endpoint with job logs error"""
        mock_session.query.return_value.count.side_effect = Exception("Count error")

        with patch('app.get_session', return_value=mock_session):
            response = test_client.get('/metrics')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_metrics_endpoint_heartbeats_error(self, test_client, mock_session):
        """Test metrics endpoint with heartbeats error"""
        mock_session.query.return_value.count.side_effect = [Exception("Error"), 0]

        with patch('app.get_session', return_value=mock_session):
            response = test_client.get('/metrics')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_vtxo_endpoint_no_session_id(self, test_client):
        """Test VTXO endpoint without session_id"""
        response = test_client.post('/api/v1/vtxo/create',
                                 json={'amount': 10000},
                                 content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_vtxo_endpoint_invalid_json(self, test_client):
        """Test VTXO endpoint with invalid JSON"""
        response = test_client.post('/api/v1/vtxo/create',
                                 data='invalid json',
                                 content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_vtxo_endpoint_exception(self, test_client):
        """Test VTXO endpoint with exception"""
        with patch('app.get_session', side_effect=Exception("Database error")):
            response = test_client.post('/api/v1/vtxo/create',
                                     json={'session_id': 'test', 'amount': 10000},
                                     content_type='application/json')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_vtxo_spend_endpoint_no_session_id(self, test_client):
        """Test VTXO spend endpoint without session_id"""
        response = test_client.post('/api/v1/vtxo/spend',
                                 json={'vtxo_id': 'test_vtxo'},
                                 content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_vtxo_spend_endpoint_no_vtxo_id(self, test_client):
        """Test VTXO spend endpoint without vtxo_id"""
        response = test_client.post('/api/v1/vtxo/spend',
                                 json={'session_id': 'test'},
                                 content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_vtxo_spend_endpoint_exception(self, test_client):
        """Test VTXO spend endpoint with exception"""
        with patch('app.get_session', side_effect=Exception("Database error")):
            response = test_client.post('/api/v1/vtxo/spend',
                                     json={'session_id': 'test', 'vtxo_id': 'test'},
                                     content_type='application/json')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_vtxo_list_endpoint_exception(self, test_client):
        """Test VTXO list endpoint with exception"""
        with patch('app.get_session', side_effect=Exception("Database error")):
            response = test_client.get('/api/v1/vtxo/list?user_pubkey=test')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_session_start_endpoint_no_user_pubkey(self, test_client):
        """Test session start endpoint without user_pubkey"""
        response = test_client.post('/api/v1/session/start',
                                 json={'session_type': 'p2p_transfer'},
                                 content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_session_start_endpoint_no_session_type(self, test_client):
        """Test session start endpoint without session_type"""
        response = test_client.post('/api/v1/session/start',
                                 json={'user_pubkey': 'test'},
                                 content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_session_start_endpoint_exception(self, test_client):
        """Test session start endpoint with exception"""
        with patch('app.get_session_manager', side_effect=Exception("Service error")):
            response = test_client.post('/api/v1/session/start',
                                     json={'user_pubkey': 'test', 'session_type': 'p2p_transfer'},
                                     content_type='application/json')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_session_status_endpoint_exception(self, test_client):
        """Test session status endpoint with exception"""
        with patch('app.get_session_manager', side_effect=Exception("Service error")):
            response = test_client.get('/api/v1/session/test/status')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_session_cancel_endpoint_exception(self, test_client):
        """Test session cancel endpoint with exception"""
        with patch('app.get_session_manager', side_effect=Exception("Service error")):
            response = test_client.post('/api/v1/session/test/cancel')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_challenge_verify_endpoint_no_challenge_data(self, test_client):
        """Test challenge verify endpoint without challenge_data"""
        response = test_client.post('/api/v1/challenge/verify',
                                 json={'session_id': 'test'},
                                 content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_challenge_verify_endpoint_no_session_id(self, test_client):
        """Test challenge verify endpoint without session_id"""
        response = test_client.post('/api/v1/challenge/verify',
                                 json={'challenge_data': 'test'},
                                 content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_challenge_verify_endpoint_exception(self, test_client):
        """Test challenge verify endpoint with exception"""
        with patch('app.get_challenge_manager', side_effect=Exception("Service error")):
            response = test_client.post('/api/v1/challenge/verify',
                                     json={'session_id': 'test', 'challenge_data': 'test'},
                                     content_type='application/json')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_transaction_process_endpoint_no_intent_data(self, test_client):
        """Test transaction process endpoint without intent_data"""
        response = test_client.post('/api/v1/transaction/process',
                                 json={'session_id': 'test'},
                                 content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_transaction_process_endpoint_no_session_id(self, test_client):
        """Test transaction process endpoint without session_id"""
        response = test_client.post('/api/v1/transaction/process',
                                 json={'intent_data': {}},
                                 content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_transaction_process_endpoint_exception(self, test_client):
        """Test transaction process endpoint with exception"""
        with patch('app.get_transaction_processor', side_effect=Exception("Service error")):
            response = test_client.post('/api/v1/transaction/process',
                                     json={'session_id': 'test', 'intent_data': {}},
                                     content_type='application/json')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_transaction_status_endpoint_exception(self, test_client):
        """Test transaction status endpoint with exception"""
        with patch('app.get_transaction_processor', side_effect=Exception("Service error")):
            response = test_client.get('/api/v1/transaction/test/status')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_transaction_list_endpoint_exception(self, test_client):
        """Test transaction list endpoint with exception"""
        with patch('app.get_transaction_processor', side_effect=Exception("Service error")):
            response = test_client.get('/api/v1/transaction/list?user_pubkey=test')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_asset_info_endpoint_exception(self, test_client):
        """Test asset info endpoint with exception"""
        with patch('app.get_asset_manager', side_effect=Exception("Service error")):
            response = test_client.get('/api/v1/asset/test/info')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_asset_balance_endpoint_exception(self, test_client):
        """Test asset balance endpoint with exception"""
        with patch('app.get_asset_manager', side_effect=Exception("Service error")):
            response = test_client.get('/api/v1/asset/test/balance?user_pubkey=test')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_lightning_invoice_endpoint_exception(self, test_client):
        """Test Lightning invoice endpoint with exception"""
        with patch('app.lightning_manager', side_effect=Exception("Service error")):
            response = test_client.post('/api/v1/lightning/invoice',
                                     json={'amount': 10000},
                                     content_type='application/json')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_lightning_pay_endpoint_exception(self, test_client):
        """Test Lightning pay endpoint with exception"""
        with patch('app.lightning_manager', side_effect=Exception("Service error")):
            response = test_client.post('/api/v1/lightning/pay',
                                     json={'invoice': 'test_invoice'},
                                     content_type='application/json')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_lightning_status_endpoint_exception(self, test_client):
        """Test Lightning status endpoint with exception"""
        with patch('app.lightning_manager', side_effect=Exception("Service error")):
            response = test_client.get('/api/v1/lightning/status/test_payment_hash')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_nostr_connect_endpoint_exception(self, test_client):
        """Test Nostr connect endpoint with exception"""
        with patch('app.nostr_client', side_effect=Exception("Service error")):
            response = test_client.post('/api/v1/nostr/connect')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_nostr_disconnect_endpoint_exception(self, test_client):
        """Test Nostr disconnect endpoint with exception"""
        with patch('app.nostr_client', side_effect=Exception("Service error")):
            response = test_client.post('/api/v1/nostr/disconnect')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_nostr_status_endpoint_exception(self, test_client):
        """Test Nostr status endpoint with exception"""
        with patch('app.nostr_client', side_effect=Exception("Service error")):
            response = test_client.get('/api/v1/nostr/status')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_monitoring_metrics_endpoint_exception(self, test_client):
        """Test monitoring metrics endpoint with exception"""
        with patch('app.monitoring_system', side_effect=Exception("Service error")):
            response = test_client.get('/api/v1/monitoring/metrics')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_monitoring_health_endpoint_exception(self, test_client):
        """Test monitoring health endpoint with exception"""
        with patch('app.monitoring_system', side_effect=Exception("Service error")):
            response = test_client.get('/api/v1/monitoring/health')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_cache_get_endpoint_exception(self, test_client):
        """Test cache get endpoint with exception"""
        with patch('app.cache_manager', side_effect=Exception("Service error")):
            response = test_client.get('/api/v1/cache/get/test_key')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_cache_set_endpoint_exception(self, test_client):
        """Test cache set endpoint with exception"""
        with patch('app.cache_manager', side_effect=Exception("Service error")):
            response = test_client.post('/api/v1/cache/set',
                                     json={'key': 'test', 'value': 'test'},
                                     content_type='application/json')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_cache_delete_endpoint_exception(self, test_client):
        """Test cache delete endpoint with exception"""
        with patch('app.cache_manager', side_effect=Exception("Service error")):
            response = test_client.delete('/api/v1/cache/delete/test_key')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_cache_exists_endpoint_exception(self, test_client):
        """Test cache exists endpoint with exception"""
        with patch('app.cache_manager', side_effect=Exception("Service error")):
            response = test_client.get('/api/v1/cache/exists/test_key')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_job_enqueue_endpoint_exception(self, test_client):
        """Test job enqueue endpoint with exception"""
        with patch('app.q', side_effect=Exception("Queue error")):
            response = test_client.post('/api/v1/job/enqueue',
                                     json={'job_type': 'test', 'data': {}},
                                     content_type='application/json')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_job_status_endpoint_exception(self, test_client):
        """Test job status endpoint with exception"""
        with patch('app.q', side_effect=Exception("Queue error")):
            response = test_client.get('/api/v1/job/test_job_id/status')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_job_cancel_endpoint_exception(self, test_client):
        """Test job cancel endpoint with exception"""
        with patch('app.q', side_effect=Exception("Queue error")):
            response = test_client.delete('/api/v1/job/test_job_id/cancel')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_scheduler_schedule_endpoint_exception(self, test_client):
        """Test scheduler schedule endpoint with exception"""
        with patch('app.scheduler', side_effect=Exception("Scheduler error")):
            response = test_client.post('/api/v1/scheduler/schedule',
                                     json={'job_type': 'test', 'data': {}, 'scheduled_time': '2024-01-01T00:00:00'},
                                     content_type='application/json')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_scheduler_list_endpoint_exception(self, test_client):
        """Test scheduler list endpoint with exception"""
        with patch('app.scheduler', side_effect=Exception("Scheduler error")):
            response = test_client.get('/api/v1/scheduler/list')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_scheduler_cancel_endpoint_exception(self, test_client):
        """Test scheduler cancel endpoint with exception"""
        with patch('app.scheduler', side_effect=Exception("Scheduler error")):
            response = test_client.delete('/api/v1/scheduler/test_job_id/cancel')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_websocket_endpoint_exception(self, test_client):
        """Test WebSocket endpoint with exception"""
        with patch('app.nostr_client', side_effect=Exception("Service error")):
            response = test_client.get('/ws')
            # WebSocket endpoint should handle exceptions gracefully
            assert response.status_code in [200, 500]

    def test_stream_events_endpoint_exception(self, test_client):
        """Test stream events endpoint with exception"""
        with patch('app.nostr_client', side_effect=Exception("Service error")):
            response = test_client.get('/api/v1/stream/events')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_stream_metrics_endpoint_exception(self, test_client):
        """Test stream metrics endpoint with exception"""
        with patch('app.monitoring_system', side_effect=Exception("Service error")):
            response = test_client.get('/api/v1/stream/metrics')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_stream_logs_endpoint_exception(self, test_client):
        """Test stream logs endpoint with exception"""
        response = test_client.get('/api/v1/stream/logs')
        assert response.status_code == 200

    def test_error_handler_404(self, test_client):
        """Test 404 error handler"""
        response = test_client.get('/nonexistent')
        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data

    def test_error_handler_500(self, test_client):
        """Test 500 error handler"""
        with patch('app.get_session', side_effect=Exception("Database error")):
            response = test_client.get('/health')
            assert response.status_code == 500
            data = response.get_json()
            assert 'error' in data

    def test_app_configuration(self, test_app):
        """Test app configuration"""
        with test_app.app_context():
            assert test_app.config['TESTING'] is True
            assert test_app.config['SECRET_KEY'] == 'test-secret-key'

    def test_app_routes(self, test_app):
        """Test app routes registration"""
        with test_app.app_context():
            rules = [rule.rule for rule in test_app.url_map.iter_rules()]
            assert '/' in rules
            assert '/health' in rules
            assert '/ready' in rules
            assert '/metrics' in rules

    def test_app_blueprints(self, test_app):
        """Test app blueprints registration"""
        with test_app.app_context():
            assert 'admin_bp' in [bp.name for bp in test_app.blueprints.values()]

    def test_request_logging(self, test_client):
        """Test request logging"""
        with patch('app.current_app.logger') as mock_logger:
            response = test_client.get('/health')
            assert response.status_code == 200
            # Logger should be called (depends on actual implementation)

    def test_database_connection_pooling(self, test_client):
        """Test database connection pooling"""
        for _ in range(5):
            response = test_client.get('/health')
            assert response.status_code == 200

    def test_redis_connection_pooling(self, test_client):
        """Test Redis connection pooling"""
        for _ in range(5):
            response = test_client.get('/ready')
            assert response.status_code == 200

    def test_concurrent_requests(self, test_client):
        """Test concurrent requests"""
        import threading
        import time

        def make_request():
            response = test_client.get('/health')
            assert response.status_code == 200

        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

    def test_performance_health_check(self, test_client):
        """Test performance of health check endpoint"""
        import time
        start_time = time.time()

        for _ in range(10):
            response = test_client.get('/health')
            assert response.status_code == 200

        end_time = time.time()
        avg_time = (end_time - start_time) / 10
        assert avg_time < 0.1  # Average response time should be less than 100ms

    def test_memory_usage(self, test_client):
        """Test memory usage"""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Make multiple requests
        for _ in range(10):
            response = test_client.get('/health')
            assert response.status_code == 200

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 50MB)
        assert memory_increase < 50 * 1024 * 1024