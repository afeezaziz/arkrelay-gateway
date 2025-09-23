"""
Test utilities and fixtures for Ark Relay Gateway
"""

import pytest
import os
import json
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import app
from core.models import Base, Asset, Vtxo, SigningSession, Transaction, get_session
from core.config import Config


class TestConfig:
    """Test configuration class"""

    def __init__(self):
        self.DATABASE_URL = 'sqlite:///:memory:'
        self.REDIS_URL = 'redis://localhost:6379/1'
        self.ARKD_HOST = 'localhost'
        self.ARKD_PORT = 10009
        self.TAPD_HOST = 'localhost'
        self.TAPD_PORT = 10029
        self.LND_HOST = 'localhost'
        self.LND_PORT = 10009
        self.LOG_LEVEL = 'DEBUG'
        self.FLASK_ENV = 'testing'
        self.SECRET_KEY = 'test-secret-key'
        self.NOSTR_RELAYS = ['wss://test.relay.com']
        self.GRPC_TIMEOUT_SECONDS = 30
        self.GRPC_MAX_MESSAGE_LENGTH = 4194304
        self.VTXO_EXPIRY_MINUTES = 60
        self.SESSION_TIMEOUT_MINUTES = 30
        self.CHALLENGE_TIMEOUT_MINUTES = 5
        self.MAX_RETRY_ATTEMPTS = 3
        self.RETRY_DELAY_SECONDS = 1
        self.HEALTH_CHECK_INTERVAL_SECONDS = 30
        self.METRICS_RETENTION_DAYS = 30
        self.CIRCUIT_BREAKER_THRESHOLD = 5
        self.CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60

    def is_development(self):
        return False

    def is_production(self):
        return False

    def is_testing(self):
        return True


@pytest.fixture
def test_config():
    """Test configuration fixture"""
    return TestConfig()


@pytest.fixture
def test_app():
    """Create test Flask app"""
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SECRET_KEY'] = 'test-secret-key'

    with app.app_context():
        yield app


@pytest.fixture
def test_client(test_app):
    """Create test client"""
    return test_app.test_client()


@pytest.fixture
def test_db():
    """Create test database"""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    mock_redis = Mock()
    mock_redis.ping.return_value = True
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = 1
    mock_redis.exists.return_value = 0
    mock_redis.ttl.return_value = 3600
    mock_redis.expire.return_value = True
    return mock_redis


@pytest.fixture
def mock_grpc_manager():
    """Mock gRPC manager"""
    mock_manager = Mock()
    mock_client = Mock()
    mock_manager.get_client.return_value = mock_client
    mock_manager.is_available.return_value = True
    return mock_manager, mock_client


@pytest.fixture
def mock_nostr_client():
    """Mock Nostr client"""
    mock_client = Mock()
    mock_client.connect.return_value = True
    mock_client.publish_event.return_value = True
    mock_client.subscribe_to_events.return_value = True
    mock_client.disconnect.return_value = True
    return mock_client


@pytest.fixture
def sample_asset():
    """Sample asset for testing"""
    return Asset(
        asset_id="gbtc",
        name="Bitcoin",
        ticker="BTC",
        decimal_places=8,
        total_supply=21000000,
        is_active=True
    )


@pytest.fixture
def sample_vtxo():
    """Sample VTXO for testing"""
    return Vtxo(
        vtxo_id="test_vtxo_id",
        txid="test_tx_id",
        vout=0,
        amount_sats=50000,
        script_pubkey=b"test_script_pubkey",
        asset_id="gbtc",
        user_pubkey="test_user_pubkey",
        status="available",
        expires_at=datetime.now() + timedelta(hours=1)
    )


@pytest.fixture
def sample_signing_session():
    """Sample signing session for testing"""
    return SigningSession(
        session_id="test_session_id",
        user_pubkey="test_user_pubkey",
        session_type="p2p_transfer",
        status="initiated",
        intent_data={"type": "transfer", "amount": 10000},
        context="Test context",
        expires_at=datetime.now() + timedelta(minutes=10)
    )


@pytest.fixture
def sample_transaction():
    """Sample transaction for testing"""
    return Transaction(
        txid="test_tx_id",
        session_id="test_session_id",
        tx_type="ark_tx",
        raw_tx="test_raw_tx",
        amount_sats=10000,
        fee_sats=100,
        status="pending"
    )


@pytest.fixture
def mock_session():
    """Mock database session"""
    mock_session = Mock()
    mock_session.execute.return_value = None
    mock_session.commit.return_value = None
    mock_session.rollback.return_value = None
    mock_session.query.return_value.count.return_value = 0
    mock_session.query.return_value.order_by.return_value.limit.return_value.all.return_value = []
    return mock_session


@pytest.fixture
def auth_headers():
    """Authorization headers for testing"""
    return {
        'Authorization': 'Bearer test-token',
        'Content-Type': 'application/json'
    }


@pytest.fixture
def sample_user_data():
    """Sample user data for testing"""
    return {
        'user_pubkey': 'test_user_pubkey',
        'amount': 10000,
        'asset_id': 'gbtc',
        'recipient_pubkey': 'recipient_pubkey'
    }


@pytest.fixture
def sample_intent_data():
    """Sample intent data for testing"""
    return {
        'type': 'p2p_transfer',
        'user_pubkey': 'test_user_pubkey',
        'amount': 10000,
        'asset_id': 'gbtc',
        'recipient_pubkey': 'recipient_pubkey'
    }


@pytest.fixture
def performance_metrics():
    """Sample performance metrics for testing"""
    return {
        'cpu_percent': 25.5,
        'memory_percent': 60.2,
        'memory_available_mb': 8192.0,
        'disk_percent': 45.8,
        'disk_free_gb': 256.0,
        'timestamp': datetime.now()
    }


@pytest.fixture
def sample_job_data():
    """Sample job data for testing"""
    return {
        'job_id': 'test_job_id',
        'job_type': 'vtxo_replenishment',
        'status': 'running',
        'message': 'Test job message'
    }


@pytest.fixture
def mock_lightning_manager():
    """Mock Lightning manager"""
    mock_manager = Mock()
    mock_manager.create_invoice.return_value = ('payment_hash', 'bolt11_invoice')
    mock_manager.pay_invoice.return_value = {'preimage': 'test_preimage'}
    mock_manager.get_invoice_status.return_value = 'paid'
    return mock_manager


@pytest.fixture
def mock_vtxo_manager():
    """Mock VTXO manager"""
    mock_manager = Mock()
    mock_manager.create_vtxo.return_value = 'vtxo_id'
    mock_manager.spend_vtxo.return_value = True
    mock_manager.get_vtxo_info.return_value = {
        'vtxo_id': 'test_vtxo',
        'amount': 10000,
        'status': 'available'
    }
    return mock_manager


@pytest.fixture
def mock_session_manager():
    """Mock session manager"""
    mock_manager = Mock()
    mock_manager.create_session.return_value = 'session_id'
    mock_manager.get_session.return_value = {
        'session_id': 'test_session',
        'status': 'active',
        'user_pubkey': 'test_user'
    }
    mock_manager.update_session.return_value = True
    return mock_manager


@pytest.fixture
def mock_challenge_manager():
    """Mock challenge manager"""
    mock_manager = Mock()
    mock_manager.create_challenge.return_value = 'challenge_id'
    mock_manager.verify_challenge.return_value = True
    mock_manager.get_challenge.return_value = {
        'challenge_id': 'test_challenge',
        'status': 'pending'
    }
    return mock_manager


@pytest.fixture
def mock_transaction_processor():
    """Mock transaction processor"""
    mock_processor = Mock()
    mock_processor.process_transaction.return_value = 'tx_id'
    mock_processor.get_transaction_status.return_value = 'completed'
    mock_processor.get_user_transactions.return_value = []
    return mock_processor


@pytest.fixture
def mock_signing_orchestrator():
    """Mock signing orchestrator"""
    mock_orchestrator = Mock()
    mock_orchestrator.start_signing_ceremony.return_value = 'ceremony_id'
    mock_orchestrator.execute_signing_step.return_value = True
    mock_orchestrator.get_ceremony_status.return_value = {
        'ceremony_id': 'test_ceremony',
        'status': 'completed'
    }
    return mock_orchestrator


@pytest.fixture
def mock_asset_manager():
    """Mock asset manager"""
    mock_manager = Mock()
    mock_manager.get_asset.return_value = {
        'asset_id': 'gbtc',
        'name': 'Bitcoin',
        'ticker': 'BTC'
    }
    mock_manager.get_user_balance.return_value = 10000
    mock_manager.update_balance.return_value = True
    return mock_manager


@pytest.fixture
def mock_monitoring_system():
    """Mock monitoring system"""
    mock_system = Mock()
    mock_system.record_metrics.return_value = True
    mock_system.get_metrics.return_value = {
        'cpu_percent': 25.5,
        'memory_percent': 60.2
    }
    mock_system.get_health_status.return_value = 'healthy'
    return mock_system


@pytest.fixture
def mock_cache_manager():
    """Mock cache manager"""
    mock_manager = Mock()
    mock_manager.get.return_value = None
    mock_manager.set.return_value = True
    mock_manager.delete.return_value = True
    mock_manager.exists.return_value = False
    return mock_manager


@pytest.fixture
def sample_error_response():
    """Sample error response for testing"""
    return {
        'error': 'Test error',
        'status_code': 400,
        'message': 'This is a test error'
    }


@pytest.fixture
def sample_success_response():
    """Sample success response for testing"""
    return {
        'status': 'success',
        'data': {
            'id': 'test_id',
            'created_at': datetime.now().isoformat()
        }
    }


@pytest.fixture
def timing_data():
    """Timing data for performance testing"""
    start_time = time.time()
    yield {'start_time': start_time}
    end_time = time.time()
    return {'duration': end_time - start_time}


@pytest.fixture
def sample_websocket_message():
    """Sample WebSocket message for testing"""
    return {
        'type': 'message',
        'data': {
            'event_type': 'test_event',
            'payload': {'key': 'value'}
        }
    }


@pytest.fixture
def sample_log_entry():
    """Sample log entry for testing"""
    return {
        'timestamp': datetime.now(),
        'level': 'INFO',
        'message': 'Test log message',
        'module': 'test_module'
    }


@pytest.fixture
def mock_job_queue():
    """Mock job queue"""
    mock_queue = Mock()
    mock_queue.enqueue.return_value = Mock(id='test_job_id')
    mock_queue.fetch_job.return_value = Mock(
        id='test_job_id',
        get_status=lambda: 'completed',
        result={'success': True}
    )
    return mock_queue


@pytest.fixture
def mock_scheduler():
    """Mock scheduler"""
    mock_scheduler = Mock()
    mock_scheduler.schedule.return_value = Mock(id='test_scheduled_job')
    mock_scheduler.get_jobs.return_value = []
    mock_scheduler.cancel.return_value = True
    return mock_scheduler


@pytest.fixture
def environment_variables():
    """Environment variables for testing"""
    original_env = os.environ.copy()

    test_env = {
        'DATABASE_URL': 'sqlite:///test.db',
        'REDIS_URL': 'redis://localhost:6379/1',
        'ARKD_HOST': 'test.arkd.host',
        'TAPD_HOST': 'test.tapd.host',
        'LND_HOST': 'test.lnd.host',
        'LOG_LEVEL': 'DEBUG',
        'FLASK_ENV': 'testing',
        'SECRET_KEY': 'test-secret-key'
    }

    os.environ.update(test_env)
    yield test_env

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)