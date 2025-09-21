import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Database Configuration
    @property
    def DATABASE_URL(self) -> str:
        return os.getenv('DATABASE_URL', 'mysql+pymysql://user:password@mariadb:3306/arkrelay')

    # Redis Configuration
    @property
    def REDIS_URL(self) -> str:
        return os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # Flask Configuration
    @property
    def FLASK_ENV(self) -> str:
        return os.getenv('FLASK_ENV', 'development')

    @property
    def FLASK_DEBUG(self) -> bool:
        return os.getenv('FLASK_DEBUG', 'false').lower() == 'true'

    @property
    def SECRET_KEY(self) -> str:
        return os.getenv('SECRET_KEY', 'your-secret-key-here')

    # Application Configuration
    @property
    def APP_PORT(self) -> int:
        return int(os.getenv('APP_PORT', 8000))

    @property
    def APP_HOST(self) -> str:
        return os.getenv('APP_HOST', '0.0.0.0')

    @property
    def SERVICE_TYPE(self) -> str:
        return os.getenv('SERVICE_TYPE', 'web')

    # Logging Configuration
    @property
    def LOG_LEVEL(self) -> str:
        return os.getenv('LOG_LEVEL', 'INFO')

    @property
    def LOG_FORMAT(self) -> str:
        return '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Bitcoin Network Configuration
    @property
    def BITCOIN_NETWORK(self) -> str:
        return os.getenv('BITCOIN_NETWORK', 'testnet')

    # ARK Configuration
    @property
    def ARKD_HOST(self) -> str:
        return os.getenv('ARKD_HOST', 'localhost')

    @property
    def ARKD_PORT(self) -> int:
        return int(os.getenv('ARKD_PORT', 10009))

    @property
    def ARKD_TLS_CERT(self) -> Optional[str]:
        return os.getenv('ARKD_TLS_CERT')

    @property
    def ARKD_MACAROON(self) -> Optional[str]:
        return os.getenv('ARKD_MACAROON')

    # TAPD Configuration
    @property
    def TAPD_HOST(self) -> str:
        return os.getenv('TAPD_HOST', 'localhost')

    @property
    def TAPD_PORT(self) -> int:
        return int(os.getenv('TAPD_PORT', 10029))

    @property
    def TAPD_TLS_CERT(self) -> Optional[str]:
        return os.getenv('TAPD_TLS_CERT')

    @property
    def TAPD_MACAROON(self) -> Optional[str]:
        return os.getenv('TAPD_MACAROON')

    # LND Configuration
    @property
    def LND_HOST(self) -> str:
        return os.getenv('LND_HOST', 'localhost')

    @property
    def LND_PORT(self) -> int:
        return int(os.getenv('LND_PORT', 10009))

    @property
    def LND_TLS_CERT(self) -> Optional[str]:
        return os.getenv('LND_TLS_CERT')

    @property
    def LND_MACAROON(self) -> Optional[str]:
        return os.getenv('LND_MACAROON')

    # Nostr Configuration
    @property
    def NOSTR_RELAYS(self) -> list:
        return os.getenv('NOSTR_RELAYS', 'wss://relay.damus.io,wss://nos.lol').split(',')

    @property
    def NOSTR_PRIVATE_KEY(self) -> Optional[str]:
        return os.getenv('NOSTR_PRIVATE_KEY')

    # Session Configuration
    @property
    def SESSION_TIMEOUT_MINUTES(self) -> int:
        return int(os.getenv('SESSION_TIMEOUT_MINUTES', 30))

    @property
    def MAX_CONCURRENT_SESSIONS(self) -> int:
        return int(os.getenv('MAX_CONCURRENT_SESSIONS', 100))

    @property
    def CHALLENGE_TIMEOUT_MINUTES(self) -> int:
        return int(os.getenv('CHALLENGE_TIMEOUT_MINUTES', 5))

    # VTXO Configuration
    @property
    def VTXO_EXPIRATION_HOURS(self) -> int:
        return int(os.getenv('VTXO_EXPIRATION_HOURS', 24))

    @property
    def VTXO_EXPIRY_MINUTES(self) -> int:
        return int(os.getenv('VTXO_EXPIRY_MINUTES', 60))  # For backwards compatibility

    @property
    def VTXO_MIN_AMOUNT_SATS(self) -> int:
        return int(os.getenv('VTXO_MIN_AMOUNT_SATS', 1000))

    # Fee Configuration
    @property
    def FEE_SATS_PER_VBYTE(self) -> int:
        return int(os.getenv('FEE_SATS_PER_VBYTE', 10))

    @property
    def FEE_PERCENTAGE(self) -> float:
        return float(os.getenv('FEE_PERCENTAGE', 0.001))

    # gRPC Configuration
    @property
    def GRPC_MAX_MESSAGE_LENGTH(self) -> int:
        return int(os.getenv('GRPC_MAX_MESSAGE_LENGTH', 4194304))  # 4MB

    @property
    def GRPC_TIMEOUT_SECONDS(self) -> int:
        return int(os.getenv('GRPC_TIMEOUT_SECONDS', 30))

    # Retry Configuration
    @property
    def MAX_RETRY_ATTEMPTS(self) -> int:
        return int(os.getenv('MAX_RETRY_ATTEMPTS', 3))

    @property
    def RETRY_DELAY_SECONDS(self) -> int:
        return int(os.getenv('RETRY_DELAY_SECONDS', 1))

    # Health Check Configuration
    @property
    def HEALTH_CHECK_INTERVAL_SECONDS(self) -> int:
        return int(os.getenv('HEALTH_CHECK_INTERVAL_SECONDS', 30))

    @property
    def METRICS_RETENTION_DAYS(self) -> int:
        return int(os.getenv('METRICS_RETENTION_DAYS', 30))

    # Circuit Breaker Configuration
    @property
    def CIRCUIT_BREAKER_THRESHOLD(self) -> int:
        return int(os.getenv('CIRCUIT_BREAKER_THRESHOLD', 5))

    @property
    def CIRCUIT_BREAKER_TIMEOUT_SECONDS(self) -> int:
        return int(os.getenv('CIRCUIT_BREAKER_TIMEOUT_SECONDS', 60))

    # Security Configuration
    @property
    def ENCRYPTION_KEY(self) -> Optional[str]:
        return os.getenv('ENCRYPTION_KEY')

    @property
    def ENABLE_ENCRYPTION(self) -> bool:
        return os.getenv('ENABLE_ENCRYPTION', 'true').lower() == 'true'

    # Monitoring Configuration
    @property
    def ENABLE_METRICS(self) -> bool:
        return os.getenv('ENABLE_METRICS', 'true').lower() == 'true'

    @property
    def METRICS_PORT(self) -> int:
        return int(os.getenv('METRICS_PORT', 8080))

    @property
    def MONITORING_AUTO_START(self) -> bool:
        return os.getenv('MONITORING_AUTO_START', 'true').lower() == 'true'

    @property
    def PERFORMANCE_OPTIMIZATION(self) -> bool:
        return os.getenv('PERFORMANCE_OPTIMIZATION', 'true').lower() == 'true'

    # Alerting Configuration
    @property
    def ALERTING_ENABLED(self) -> bool:
        return os.getenv('ALERTING_ENABLED', 'true').lower() == 'true'

    @property
    def SLACK_WEBHOOK_URL(self) -> Optional[str]:
        return os.getenv('SLACK_WEBHOOK_URL')

    # Cache Configuration
    @property
    def CACHE_ENABLED(self) -> bool:
        return os.getenv('CACHE_ENABLED', 'true').lower() == 'true'

    @property
    def CACHE_DEFAULT_TTL(self) -> int:
        return int(os.getenv('CACHE_DEFAULT_TTL', 300))  # 5 minutes

    # Database Pool Configuration
    @property
    def DB_POOL_SIZE(self) -> int:
        return int(os.getenv('DB_POOL_SIZE', 10))

    @property
    def DB_POOL_MAX_OVERFLOW(self) -> int:
        return int(os.getenv('DB_POOL_MAX_OVERFLOW', 20))

    @property
    def DB_POOL_TIMEOUT(self) -> int:
        return int(os.getenv('DB_POOL_TIMEOUT', 30))

    # Admin Configuration
    @property
    def ADMIN_API_KEY(self) -> Optional[str]:
        return os.getenv('ADMIN_API_KEY')

    @property
    def ADMIN_ENABLED(self) -> bool:
        return os.getenv('ADMIN_ENABLED', 'true').lower() == 'true'

    @classmethod
    def validate(cls) -> bool:
        required_vars = [
            'DATABASE_URL',
            'REDIS_URL',
            'SECRET_KEY',
        ]

        for var in required_vars:
            if not getattr(cls, var):
                raise ValueError(f"Required environment variable {var} is not set")

        return True

    @classmethod
    def get_arkd_connection_params(cls) -> dict:
        return {
            'host': cls.ARKD_HOST,
            'port': cls.ARKD_PORT,
            'tls_cert': cls.ARKD_TLS_CERT,
            'macaroon': cls.ARKD_MACAROON,
        }

    @classmethod
    def get_tapd_connection_params(cls) -> dict:
        return {
            'host': cls.TAPD_HOST,
            'port': cls.TAPD_PORT,
            'tls_cert': cls.TAPD_TLS_CERT,
            'macaroon': cls.TAPD_MACAROON,
        }

    @classmethod
    def get_lnd_connection_params(cls) -> dict:
        return {
            'host': cls.LND_HOST,
            'port': cls.LND_PORT,
            'tls_cert': cls.LND_TLS_CERT,
            'macaroon': cls.LND_MACAROON,
        }

    def is_development(self) -> bool:
        return self.FLASK_ENV == 'development'

    def is_production(self) -> bool:
        return self.FLASK_ENV == 'production'

    def is_testing(self) -> bool:
        return self.FLASK_ENV == 'testing'

    def to_dict(self) -> dict:
        return {
            attr: getattr(self, attr)
            for attr in dir(self)
            if not attr.startswith('_') and not callable(getattr(self, attr))
        }

    def __str__(self) -> str:
        return f"Config(DATABASE_URL={self.DATABASE_URL}, REDIS_URL={self.REDIS_URL}, ARKD_HOST={self.ARKD_HOST})"

    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

class DevelopmentConfig(Config):
    FLASK_DEBUG = True
    LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
    FLASK_DEBUG = False
    LOG_LEVEL = 'INFO'

class TestingConfig(Config):
    FLASK_DEBUG = True
    LOG_LEVEL = 'DEBUG'
    DATABASE_URL = 'sqlite:///:memory:'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}