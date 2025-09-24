"""
Pytest configuration and fixtures
"""

# Load shared fixtures from test_database_setup across the test suite
pytest_plugins = ["tests.test_database_setup"]

import pytest
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_config import configure_test_environment

# Add core and grpc_clients to path
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'core'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'grpc_clients'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'nostr_clients'))


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Configure test environment for all tests"""
    configure_test_environment()


@pytest.fixture
def mock_arkd_client():
    """Mock ARKD client for testing"""
    from unittest.mock import Mock
    from grpc_clients import ServiceType

    mock_client = Mock()
    mock_client.health_check.return_value = True
    mock_client.create_vtxos.return_value = []
    mock_client.list_vtxos.return_value = []
    return mock_client


@pytest.fixture
def mock_tapd_client():
    """Mock TAPD client for testing"""
    from unittest.mock import Mock

    mock_client = Mock()
    mock_client.health_check.return_value = True
    mock_client.list_assets.return_value = []
    mock_client.get_asset_balances.return_value = {}
    return mock_client


@pytest.fixture
def mock_lnd_client():
    """Mock LND client for testing"""
    from unittest.mock import Mock
    from grpc_clients.lnd_client import LightningBalance, OnchainBalance, LightningInvoice as LndLightningInvoice, Payment
    from datetime import datetime

    mock_client = Mock()
    mock_client.health_check.return_value = True
    mock_client.get_total_balance.return_value = {
        'lightning_local_balance': 100000,
        'remote_balance': 50000,
        'onchain_total': 1000000,
        'total_wallet_balance': 1100000
    }

    # Mock Lightning balance
    mock_client.get_lightning_balance.return_value = LightningBalance(
        local_balance=100000,
        remote_balance=50000,
        pending_open_local=0,
        pending_open_remote=0,
        pending_htlc_local=0,
        pending_htlc_remote=0
    )

    # Mock onchain balance
    mock_client.get_onchain_balance.return_value = OnchainBalance(
        total_balance=1000000,
        confirmed_balance=950000,
        unconfirmed_balance=50000
    )

    # Mock invoice creation
    mock_client.add_invoice.return_value = LndLightningInvoice(
        payment_request="lnbc1000n1p3k3m2pp5test",
        r_hash="test_r_hash",
        payment_hash="test_payment_hash",
        value=1000,
        settled=False,
        creation_date=datetime.now(),
        expiry=3600,
        memo="Test invoice"
    )

    # Mock payment
    mock_client.send_payment.return_value = Payment(
        payment_hash="test_payment_hash",
        value=1000,
        fee=1,
        payment_preimage="test_preimage",
        payment_request="lnbc1000n1p3k3m2pp5test",
        status="complete",
        creation_time=datetime.now(),
        completion_time=datetime.now()
    )

    # Mock channel listing
    mock_client.list_channels.return_value = []

    # Mock invoice lookup
    mock_client.lookup_invoice.return_value = None

    return mock_client


@pytest.fixture
def lightning_manager(mock_lnd_client):
    """Lightning manager fixture"""
    from lightning_manager import LightningManager
    return LightningManager(mock_lnd_client)


@pytest.fixture
def lightning_monitor(lightning_manager):
    """Lightning monitor fixture"""
    from lightning_monitor import LightningMonitor
    return LightningMonitor(lightning_manager)


@pytest.fixture
def lightning_error_handler():
    """Lightning error handler fixture"""
    from lightning_errors import LightningErrorHandler
    return LightningErrorHandler()


@pytest.fixture
def sample_lightning_lift_request():
    """Sample Lightning lift request fixture"""
    from lightning_manager import LightningLiftRequest
    return LightningLiftRequest(
        user_pubkey="test_user_pubkey",
        asset_id="gbtc",
        amount_sats=10000,
        memo="Test lift"
    )


@pytest.fixture
def sample_lightning_land_request():
    """Sample Lightning land request fixture"""
    from lightning_manager import LightningLandRequest
    return LightningLandRequest(
        user_pubkey="test_user_pubkey",
        asset_id="gbtc",
        amount_sats=10000,
        lightning_invoice="lnbc1000n1p3k3m2pp5test_invoice"
    )


@pytest.fixture
def test_database_session():
    """Test database session fixture"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models import Base

    # Create in-memory database
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    session = Session()

    # Add some test data
    from models import AssetBalance
    test_balance = AssetBalance(
        user_pubkey="test_user_pubkey",
        asset_id="gbtc",
        balance=50000
    )
    session.add(test_balance)
    session.commit()

    yield session

    # Cleanup
    session.close()
    engine.dispose()