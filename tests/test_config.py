"""
Test configuration for gRPC client tests
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Test configuration
TEST_CONFIG = {
    # Use testnet daemons for testing
    'ARKD_HOST': 'localhost',
    'ARKD_PORT': 10009,
    'TAPD_HOST': 'localhost',
    'TAPD_PORT': 10029,
    'LND_HOST': 'localhost',
    'LND_PORT': 10009,

    # Test database
    'DATABASE_URL': 'sqlite:///:memory:',
    'REDIS_URL': 'redis://localhost:6379/1',

    # Test settings
    'FLASK_ENV': 'testing',
    'LOG_LEVEL': 'DEBUG',

    # Security
    'SECRET_KEY': 'test-secret-key',
    'ENCRYPTION_KEY': 'test-encryption-key',

    # gRPC settings
    'GRPC_TIMEOUT_SECONDS': 5,
    'GRPC_MAX_MESSAGE_LENGTH': 1024 * 1024,  # 1MB for tests
}

def configure_test_environment():
    """Configure environment for testing"""
    for key, value in TEST_CONFIG.items():
        os.environ[key] = str(value)