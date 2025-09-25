# Configuration Reference

This document lists all environment variables recognized by the ArkRelay Gateway (see `core/config.py`), their defaults, and what they control.

Notes
- Defaults are suitable for local development.
- Secrets (e.g., `SECRET_KEY`, macaroons, TLS cert paths) should be provided via a secure secret manager in production.

## Core Application

- DATABASE_URL (default: mysql+pymysql://user:password@mariadb:3306/arkrelay)
  - SQLAlchemy connection URL for MariaDB/MySQL
- REDIS_URL (default: redis://localhost:6379/0)
  - Redis connection string used by RQ and caching
- FLASK_ENV (default: development)
  - Flask environment: development | production | testing
- FLASK_DEBUG (default: false)
  - Enables Flask debug mode (do not enable in production)
- SECRET_KEY (default: your-secret-key-here)
  - Flask secret key (CSRF/session). Must be set in production
- APP_PORT (default: 8000)
  - HTTP port for the Flask app
- APP_HOST (default: 0.0.0.0)
  - HTTP bind address
- SERVICE_TYPE (default: web)
  - Process role hint (web | worker | scheduler | services)
- LOG_LEVEL (default: INFO)
  - Logging level (DEBUG, INFO, WARN, ERROR)
- LOG_FORMAT (default: "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
  - Python logging format string

## Bitcoin & External Daemons

- BITCOIN_NETWORK (default: testnet)
  - Bitcoin network id (testnet | regtest | mainnet)

- ARKD_HOST (default: localhost)
- ARKD_PORT (default: 10009)
- ARKD_TLS_CERT (default: none)
- ARKD_MACAROON (default: none)
  - Connection parameters for arkd gRPC

- TAPD_HOST (default: localhost)
- TAPD_PORT (default: 10029)
- TAPD_TLS_CERT (default: none)
- TAPD_MACAROON (default: none)
  - Connection parameters for tapd gRPC

- LND_HOST (default: localhost)
- LND_PORT (default: 10009)
- LND_TLS_CERT (default: none)
- LND_MACAROON (default: none)
  - Connection parameters for lnd gRPC

## Nostr

- NOSTR_RELAYS (default: wss://relay.damus.io,wss://nos.lol)
  - Comma-separated relay list
- NOSTR_PRIVATE_KEY (default: none)
  - Hex-encoded private key for gateway identity (do not commit to repo)

## Sessions & Challenges

- SESSION_TIMEOUT_MINUTES (default: 30)
  - Lifetime for a signing session
- CHALLENGE_TIMEOUT_MINUTES (default: 5)
  - Lifetime for a single challenge request
- MAX_CONCURRENT_SESSIONS (default: 100)
  - Soft ceiling for session concurrency

## VTXO & Fees

- VTXO_EXPIRATION_HOURS (default: 24)
  - Global VTXO lifetime
- VTXO_EXPIRY_MINUTES (default: 60)
  - Backwards-compatibility knob for older flows
- VTXO_MIN_AMOUNT_SATS (default: 1000)
  - Minimum denomination for VTXOs
- FEE_SATS_PER_VBYTE (default: 10)
  - Fee estimate used for on-chain operations
- FEE_PERCENTAGE (default: 0.001)
  - Gateway fee fraction for certain operations

## gRPC, Retries, and Timeouts

- GRPC_MAX_MESSAGE_LENGTH (default: 4194304)
  - Max gRPC message size (bytes)
- GRPC_TIMEOUT_SECONDS (default: 30)
  - Client timeout for gRPC calls
- MAX_RETRY_ATTEMPTS (default: 3)
  - Retry attempts for transient errors
- RETRY_DELAY_SECONDS (default: 1)
  - Backoff base delay

## Health & Monitoring

- HEALTH_CHECK_INTERVAL_SECONDS (default: 30)
  - Interval for internal health checks
- METRICS_RETENTION_DAYS (default: 30)
  - How long to retain metrics in storage (if persisted)
- ENABLE_METRICS (default: true)
  - Toggle Prometheus metrics exporter
- METRICS_PORT (default: 8080)
  - Prometheus metrics HTTP port
- MONITORING_AUTO_START (default: true)
  - Auto-start monitoring threads at boot
- PERFORMANCE_OPTIMIZATION (default: true)
  - Enable performance helpers (caching, pooling tuning)

## Circuit Breaker & Alerting

- CIRCUIT_BREAKER_THRESHOLD (default: 5)
  - Error count threshold before opening circuit
- CIRCUIT_BREAKER_TIMEOUT_SECONDS (default: 60)
  - Cooldown interval before half-open state
- ALERTING_ENABLED (default: true)
  - Toggle internal alert generation
- SLACK_WEBHOOK_URL (default: none)
  - Slack webhook for alert delivery (if implemented)

## Security & Caching

- ENCRYPTION_KEY (default: none)
  - Optional application-level encryption key
- ENABLE_ENCRYPTION (default: true)
  - Toggle application encryption features
- ADMIN_API_KEY (default: none)
  - Required header `X-Admin-Key` for `/admin/*` endpoints
- ADMIN_ENABLED (default: true)
  - Toggle `/admin/*` routes
- CACHE_ENABLED (default: true)
  - Enables cache decorators and cache usage
- CACHE_DEFAULT_TTL (default: 300)
  - Default TTL for cache entries (seconds)

## Database Pooling

- DB_POOL_SIZE (default: 10)
  - SQLAlchemy pool size
- DB_POOL_MAX_OVERFLOW (default: 20)
  - Max overflow connections beyond pool size
- DB_POOL_TIMEOUT (default: 30)
  - Acquire timeout (seconds)

## Helpful Examples

Example `.env` for local development:

```env
DATABASE_URL=mysql+pymysql://user:password@mariadb:3306/arkrelay
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=dev-secret
FLASK_ENV=development
APP_PORT=8000

# External daemons
ARKD_HOST=localhost
ARKD_PORT=10009
TAPD_HOST=localhost
TAPD_PORT=10029
LND_HOST=localhost
LND_PORT=10009

# Nostr
NOSTR_RELAYS=wss://relay.damus.io,wss://nos.lol

# Admin / Monitoring
ADMIN_API_KEY=changeme
ENABLE_METRICS=true
METRICS_PORT=8080
```
