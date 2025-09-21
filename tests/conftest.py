"""
Pytest configuration and fixtures
"""

import pytest
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_config import configure_test_environment


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

    mock_client = Mock()
    mock_client.health_check.return_value = True
    mock_client.get_total_balance.return_value = {
        'lightning_local_balance': 0,
        'remote_balance': 0,
        'onchain_total': 0,
        'total_wallet_balance': 0
    }
    return mock_client