import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Database Configuration
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'mysql+pymysql://user:password@mariadb:3306/arkrelay')

    # Redis Configuration
    REDIS_URL: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # Flask Configuration
    FLASK_ENV: str = os.getenv('FLASK_ENV', 'development')
    FLASK_DEBUG: bool = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    SECRET_KEY: str = os.getenv('SECRET_KEY', 'your-secret-key-here')

    # Application Configuration
    APP_PORT: int = int(os.getenv('APP_PORT', 8000))
    APP_HOST: str = os.getenv('APP_HOST', '0.0.0.0')
    SERVICE_TYPE: str = os.getenv('SERVICE_TYPE', 'web')

    # Logging Configuration
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Bitcoin Network Configuration
    BITCOIN_NETWORK: str = os.getenv('BITCOIN_NETWORK', 'testnet')

    # ARK Configuration
    ARKD_HOST: str = os.getenv('ARKD_HOST', 'localhost')
    ARKD_PORT: int = int(os.getenv('ARKD_PORT', 10009))
    ARKD_TLS_CERT: Optional[str] = os.getenv('ARKD_TLS_CERT')
    ARKD_MACAROON: Optional[str] = os.getenv('ARKD_MACAROON')

    # TAPD Configuration
    TAPD_HOST: str = os.getenv('TAPD_HOST', 'localhost')
    TAPD_PORT: int = int(os.getenv('TAPD_PORT', 10029))
    TAPD_TLS_CERT: Optional[str] = os.getenv('TAPD_TLS_CERT')
    TAPD_MACAROON: Optional[str] = os.getenv('TAPD_MACAROON')

    # LND Configuration
    LND_HOST: str = os.getenv('LND_HOST', 'localhost')
    LND_PORT: int = int(os.getenv('LND_PORT', 10009))
    LND_TLS_CERT: Optional[str] = os.getenv('LND_TLS_CERT')
    LND_MACAROON: Optional[str] = os.getenv('LND_MACAROON')

    # Nostr Configuration
    NOSTR_RELAYS: list = os.getenv('NOSTR_RELAYS', 'wss://relay.damus.io,wss://nos.lol').split(',')
    NOSTR_PRIVATE_KEY: Optional[str] = os.getenv('NOSTR_PRIVATE_KEY')

    # Session Configuration
    SESSION_TIMEOUT_MINUTES: int = int(os.getenv('SESSION_TIMEOUT_MINUTES', 30))
    MAX_CONCURRENT_SESSIONS: int = int(os.getenv('MAX_CONCURRENT_SESSIONS', 100))

    # VTXO Configuration
    VTXO_EXPIRATION_HOURS: int = int(os.getenv('VTXO_EXPIRATION_HOURS', 24))
    VTXO_MIN_AMOUNT_SATS: int = int(os.getenv('VTXO_MIN_AMOUNT_SATS', 1000))

    # Fee Configuration
    FEE_SATS_PER_VBYTE: int = int(os.getenv('FEE_SATS_PER_VBYTE', 10))
    FEE_PERCENTAGE: float = float(os.getenv('FEE_PERCENTAGE', 0.001))

    # gRPC Configuration
    GRPC_MAX_MESSAGE_LENGTH: int = int(os.getenv('GRPC_MAX_MESSAGE_LENGTH', 4194304))  # 4MB
    GRPC_TIMEOUT_SECONDS: int = int(os.getenv('GRPC_TIMEOUT_SECONDS', 30))

    # Security Configuration
    ENCRYPTION_KEY: Optional[str] = os.getenv('ENCRYPTION_KEY')
    ENABLE_ENCRYPTION: bool = os.getenv('ENABLE_ENCRYPTION', 'true').lower() == 'true'

    # Monitoring Configuration
    ENABLE_METRICS: bool = os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
    METRICS_PORT: int = int(os.getenv('METRICS_PORT', 8080))

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