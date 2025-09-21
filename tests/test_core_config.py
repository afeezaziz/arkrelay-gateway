"""
Test cases for core config module
"""

import pytest
import os
from unittest.mock import patch, Mock
from core.config import Config


class TestConfig:
    """Test cases for Config class"""

    def test_config_initialization(self):
        """Test config initialization with default values"""
        config = Config()
        assert config is not None

    def test_config_database_url_default(self):
        """Test default database URL configuration"""
        config = Config()
        # Just verify it's set and is a valid URL
        assert config.DATABASE_URL is not None
        assert config.DATABASE_URL.startswith(('mysql://', 'mysql+pymysql://', 'postgresql://', 'sqlite://'))

    def test_config_database_url_env_override(self):
        """Test database URL environment override"""
        test_db_url = "postgresql://test:test@localhost/test"
        with patch.dict(os.environ, {'DATABASE_URL': test_db_url}):
            config = Config()
            assert config.DATABASE_URL == test_db_url

    def test_config_redis_url_default(self):
        """Test default Redis URL configuration"""
        config = Config()
        # Just verify it's set and is a valid Redis URL
        assert config.REDIS_URL is not None
        assert config.REDIS_URL.startswith('redis://')

    def test_config_redis_url_env_override(self):
        """Test Redis URL environment override"""
        test_redis_url = "redis://localhost:6379/1"
        with patch.dict(os.environ, {'REDIS_URL': test_redis_url}):
            config = Config()
            assert config.REDIS_URL == test_redis_url

    def test_config_arkd_host_default(self):
        """Test default ARKD host configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.ARKD_HOST == "localhost"

    def test_config_arkd_host_env_override(self):
        """Test ARKD host environment override"""
        test_host = "test.arkd.host"
        with patch.dict(os.environ, {'ARKD_HOST': test_host}):
            config = Config()
            assert config.ARKD_HOST == test_host

    def test_config_arkd_port_default(self):
        """Test default ARKD port configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.ARKD_PORT == 10009

    def test_config_arkd_port_env_override(self):
        """Test ARKD port environment override"""
        test_port = 9999
        with patch.dict(os.environ, {'ARKD_PORT': str(test_port)}):
            config = Config()
            assert config.ARKD_PORT == test_port

    def test_config_tapd_host_default(self):
        """Test default TAPD host configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.TAPD_HOST == "localhost"

    def test_config_tapd_host_env_override(self):
        """Test TAPD host environment override"""
        test_host = "test.tapd.host"
        with patch.dict(os.environ, {'TAPD_HOST': test_host}):
            config = Config()
            assert config.TAPD_HOST == test_host

    def test_config_tapd_port_default(self):
        """Test default TAPD port configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.TAPD_PORT == 10029

    def test_config_tapd_port_env_override(self):
        """Test TAPD port environment override"""
        test_port = 10039
        with patch.dict(os.environ, {'TAPD_PORT': str(test_port)}):
            config = Config()
            assert config.TAPD_PORT == test_port

    def test_config_lnd_host_default(self):
        """Test default LND host configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.LND_HOST == "localhost"

    def test_config_lnd_host_env_override(self):
        """Test LND host environment override"""
        test_host = "test.lnd.host"
        with patch.dict(os.environ, {'LND_HOST': test_host}):
            config = Config()
            assert config.LND_HOST == test_host

    def test_config_lnd_port_default(self):
        """Test default LND port configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.LND_PORT == 10009

    def test_config_lnd_port_env_override(self):
        """Test LND port environment override"""
        test_port = 9999
        with patch.dict(os.environ, {'LND_PORT': str(test_port)}):
            config = Config()
            assert config.LND_PORT == test_port

    def test_config_log_level_default(self):
        """Test default log level configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.LOG_LEVEL == "INFO"

    def test_config_log_level_env_override(self):
        """Test log level environment override"""
        test_level = "DEBUG"
        with patch.dict(os.environ, {'LOG_LEVEL': test_level}):
            config = Config()
            assert config.LOG_LEVEL == test_level

    def test_config_flask_env_default(self):
        """Test default Flask environment configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.FLASK_ENV == "development"

    def test_config_flask_env_env_override(self):
        """Test Flask environment environment override"""
        test_env = "production"
        with patch.dict(os.environ, {'FLASK_ENV': test_env}):
            config = Config()
            assert config.FLASK_ENV == test_env

    def test_config_secret_key_default(self):
        """Test default secret key configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.SECRET_KEY == "your-secret-key-here"

    def test_config_secret_key_env_override(self):
        """Test secret key environment override"""
        test_key = "test-secret-key"
        with patch.dict(os.environ, {'SECRET_KEY': test_key}):
            config = Config()
            assert config.SECRET_KEY == test_key

    def test_config_nostr_relays_default(self):
        """Test default Nostr relays configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert isinstance(config.NOSTR_RELAYS, list)
            assert len(config.NOSTR_RELAYS) > 0

    def test_config_nostr_relays_env_override(self):
        """Test Nostr relays environment override"""
        test_relays = "wss://relay1.example.com,wss://relay2.example.com"
        with patch.dict(os.environ, {'NOSTR_RELAYS': test_relays}):
            config = Config()
            assert len(config.NOSTR_RELAYS) == 2
            assert "wss://relay1.example.com" in config.NOSTR_RELAYS

    def test_config_grpc_timeout_default(self):
        """Test default gRPC timeout configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.GRPC_TIMEOUT_SECONDS == 30

    def test_config_grpc_timeout_env_override(self):
        """Test gRPC timeout environment override"""
        test_timeout = 60
        with patch.dict(os.environ, {'GRPC_TIMEOUT_SECONDS': str(test_timeout)}):
            config = Config()
            assert config.GRPC_TIMEOUT_SECONDS == test_timeout

    def test_config_grpc_max_message_length_default(self):
        """Test default gRPC max message length configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.GRPC_MAX_MESSAGE_LENGTH == 4194304

    def test_config_grpc_max_message_length_env_override(self):
        """Test gRPC max message length environment override"""
        test_length = 8388608
        with patch.dict(os.environ, {'GRPC_MAX_MESSAGE_LENGTH': str(test_length)}):
            config = Config()
            assert config.GRPC_MAX_MESSAGE_LENGTH == test_length

    def test_config_vtxo_expiry_minutes_default(self):
        """Test default VTXO expiry minutes configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.VTXO_EXPIRY_MINUTES == 60

    def test_config_vtxo_expiry_minutes_env_override(self):
        """Test VTXO expiry minutes environment override"""
        test_expiry = 120
        with patch.dict(os.environ, {'VTXO_EXPIRY_MINUTES': str(test_expiry)}):
            config = Config()
            assert config.VTXO_EXPIRY_MINUTES == test_expiry

    def test_config_session_timeout_minutes_default(self):
        """Test default session timeout minutes configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.SESSION_TIMEOUT_MINUTES == 30

    def test_config_session_timeout_minutes_env_override(self):
        """Test session timeout minutes environment override"""
        test_timeout = 15
        with patch.dict(os.environ, {'SESSION_TIMEOUT_MINUTES': str(test_timeout)}):
            config = Config()
            assert config.SESSION_TIMEOUT_MINUTES == test_timeout

    def test_config_challenge_timeout_minutes_default(self):
        """Test default challenge timeout minutes configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.CHALLENGE_TIMEOUT_MINUTES == 5

    def test_config_challenge_timeout_minutes_env_override(self):
        """Test challenge timeout minutes environment override"""
        test_timeout = 8
        with patch.dict(os.environ, {'CHALLENGE_TIMEOUT_MINUTES': str(test_timeout)}):
            config = Config()
            assert config.CHALLENGE_TIMEOUT_MINUTES == test_timeout

    def test_config_max_retry_attempts_default(self):
        """Test default max retry attempts configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.MAX_RETRY_ATTEMPTS == 3

    def test_config_max_retry_attempts_env_override(self):
        """Test max retry attempts environment override"""
        test_retries = 5
        with patch.dict(os.environ, {'MAX_RETRY_ATTEMPTS': str(test_retries)}):
            config = Config()
            assert config.MAX_RETRY_ATTEMPTS == test_retries

    def test_config_retry_delay_seconds_default(self):
        """Test default retry delay seconds configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.RETRY_DELAY_SECONDS == 1

    def test_config_retry_delay_seconds_env_override(self):
        """Test retry delay seconds environment override"""
        test_delay = 2
        with patch.dict(os.environ, {'RETRY_DELAY_SECONDS': str(test_delay)}):
            config = Config()
            assert config.RETRY_DELAY_SECONDS == test_delay

    def test_config_health_check_interval_seconds_default(self):
        """Test default health check interval seconds configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.HEALTH_CHECK_INTERVAL_SECONDS == 30

    def test_config_health_check_interval_seconds_env_override(self):
        """Test health check interval seconds environment override"""
        test_interval = 60
        with patch.dict(os.environ, {'HEALTH_CHECK_INTERVAL_SECONDS': str(test_interval)}):
            config = Config()
            assert config.HEALTH_CHECK_INTERVAL_SECONDS == test_interval

    def test_config_metrics_retention_days_default(self):
        """Test default metrics retention days configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.METRICS_RETENTION_DAYS == 30

    def test_config_metrics_retention_days_env_override(self):
        """Test metrics retention days environment override"""
        test_retention = 90
        with patch.dict(os.environ, {'METRICS_RETENTION_DAYS': str(test_retention)}):
            config = Config()
            assert config.METRICS_RETENTION_DAYS == test_retention

    def test_config_circuit_breaker_threshold_default(self):
        """Test default circuit breaker threshold configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.CIRCUIT_BREAKER_THRESHOLD == 5

    def test_config_circuit_breaker_threshold_env_override(self):
        """Test circuit breaker threshold environment override"""
        test_threshold = 10
        with patch.dict(os.environ, {'CIRCUIT_BREAKER_THRESHOLD': str(test_threshold)}):
            config = Config()
            assert config.CIRCUIT_BREAKER_THRESHOLD == test_threshold

    def test_config_circuit_breaker_timeout_seconds_default(self):
        """Test default circuit breaker timeout seconds configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.CIRCUIT_BREAKER_TIMEOUT_SECONDS == 60

    def test_config_circuit_breaker_timeout_seconds_env_override(self):
        """Test circuit breaker timeout seconds environment override"""
        test_timeout = 120
        with patch.dict(os.environ, {'CIRCUIT_BREAKER_TIMEOUT_SECONDS': str(test_timeout)}):
            config = Config()
            assert config.CIRCUIT_BREAKER_TIMEOUT_SECONDS == test_timeout

    def test_config_is_development_default(self):
        """Test default development mode configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.is_development() is True

    def test_config_is_development_env_override(self):
        """Test development mode environment override"""
        with patch.dict(os.environ, {'FLASK_ENV': 'production'}):
            config = Config()
            assert config.is_development() is False

    def test_config_is_production_default(self):
        """Test default production mode configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.is_production() is False

    def test_config_is_production_env_override(self):
        """Test production mode environment override"""
        with patch.dict(os.environ, {'FLASK_ENV': 'production'}):
            config = Config()
            assert config.is_production() is True

    def test_config_is_testing_default(self):
        """Test default testing mode configuration"""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            assert config.is_testing() is False

    def test_config_is_testing_env_override(self):
        """Test testing mode environment override"""
        with patch.dict(os.environ, {'FLASK_ENV': 'testing'}):
            config = Config()
            assert config.is_testing() is True

    def test_config_to_dict(self):
        """Test config to_dict method"""
        config = Config()
        config_dict = config.to_dict()
        assert isinstance(config_dict, dict)
        assert 'DATABASE_URL' in config_dict
        assert 'REDIS_URL' in config_dict
        assert 'ARKD_HOST' in config_dict

    def test_config_str_representation(self):
        """Test config string representation"""
        config = Config()
        config_str = str(config)
        assert 'Config' in config_str
        assert 'DATABASE_URL' in config_str

    def test_config_getattr_method(self):
        """Test config getattr method"""
        config = Config()
        assert hasattr(config, 'DATABASE_URL')
        assert hasattr(config, 'REDIS_URL')
        assert hasattr(config, 'ARKD_HOST')

    @pytest.mark.integration
    def test_config_integration_with_environment(self):
        """Test config integration with environment variables"""
        test_config = {
            'DATABASE_URL': 'sqlite:///test.db',
            'REDIS_URL': 'redis://localhost:6379/1',
            'ARKD_HOST': 'test.arkd.host',
            'TAPD_HOST': 'test.tapd.host',
            'LND_HOST': 'test.lnd.host',
            'LOG_LEVEL': 'DEBUG',
            'FLASK_ENV': 'testing'
        }

        with patch.dict(os.environ, test_config):
            config = Config()
            assert config.DATABASE_URL == 'sqlite:///test.db'
            assert config.REDIS_URL == 'redis://localhost:6379/1'
            assert config.ARKD_HOST == 'test.arkd.host'
            assert config.TAPD_HOST == 'test.tapd.host'
            assert config.LND_HOST == 'test.lnd.host'
            assert config.LOG_LEVEL == 'DEBUG'
            assert config.FLASK_ENV == 'testing'

    @pytest.mark.unit
    def test_config_validation_database_url(self):
        """Test config validation for database URL"""
        config = Config()
        assert config.DATABASE_URL is not None
        assert len(config.DATABASE_URL) > 0

    @pytest.mark.unit
    def test_config_validation_redis_url(self):
        """Test config validation for Redis URL"""
        config = Config()
        assert config.REDIS_URL is not None
        assert len(config.REDIS_URL) > 0

    @pytest.mark.unit
    def test_config_validation_hosts(self):
        """Test config validation for hosts"""
        config = Config()
        assert config.ARKD_HOST is not None
        assert config.TAPD_HOST is not None
        assert config.LND_HOST is not None

    @pytest.mark.unit
    def test_config_validation_ports(self):
        """Test config validation for ports"""
        config = Config()
        assert isinstance(config.ARKD_PORT, int)
        assert isinstance(config.TAPD_PORT, int)
        assert isinstance(config.LND_PORT, int)
        assert config.ARKD_PORT > 0
        assert config.TAPD_PORT > 0
        assert config.LND_PORT > 0