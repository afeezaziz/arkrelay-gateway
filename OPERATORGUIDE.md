# ArkRelay Operator Guide

This guide is for operators and the internal team. It covers setup, day-to-day operations, monitoring, backups, troubleshooting, and runbooks.

- Web/API: `app.py`
- Admin API: `core/admin_api.py` (requires `X-Admin-Key`)
- Monitoring: `core/monitoring.py`
- Performance/Cache: `core/cache_manager.py`
- Background Jobs: `core/tasks.py` via RQ
- External services: `grpc_clients/` (ARKD, TAPD, LND)

---

## 1. Environments and Dependencies

- Python 3.12+, Redis, MariaDB
- Optional: Docker Compose for local dev (`docker-compose.dev.yml`)
- Configure `.env` using `.env.example` as a baseline
  - Required: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`
  - Admin: `ADMIN_API_KEY`
  - Daemons: `ARKD_*`, `TAPD_*`, `LND_*`
  - Monitoring: `ENABLE_METRICS`, `METRICS_PORT`
  - Nostr: `NOSTR_RELAYS`, `NOSTR_PRIVATE_KEY`

---

## 2. Install & Launch

- Install
  ```bash
  uv sync  # or pip install -r requirements.txt
  ```
- Initialize DB
  ```bash
  alembic upgrade head
  # or
  python -c "from core.models import create_tables; create_tables()"
  ```
- Run services
  - API: `gunicorn app:app -b 0.0.0.0:8000 --workers 4`
  - Workers: `rq worker --url $REDIS_URL`
  - Scheduler: `python scheduler.py`
- Docker (dev):
  ```bash
  docker compose -f docker-compose.dev.yml up --build
  ```

Service auto-starts (via `initialize_services()` in `app.py`):
- Monitoring (`MONITORING_AUTO_START=true` by default)
- Performance optimizer (`PERFORMANCE_OPTIMIZATION=true`)
- Lightning services (`LIGHTNING_AUTO_START=true`)
- VTXO services (`VTXO_AUTO_START=true`)
- Nostr (`NOSTR_AUTO_START=false` by default)

---

## 3. Health, Readiness, and Status

- `GET /ready` — readiness gate
- `GET /health` — DB + Redis + gRPC status
- `GET /health/comprehensive` — full system health (monitoring must be running)
- `GET /queue-status` — RQ stats
- `GET /stats` — roll-up system stats

If monitoring is running:
- `GET /monitoring/stats`
- `GET /monitoring/alerts`
- `GET /monitoring/cache/stats`

---

## 4. Monitoring & Metrics

- Prometheus exporter on `METRICS_PORT` (8080 default)
- Metrics include:
  - Business: sessions, transactions, vtxos
  - System: CPU/memory/disk
  - Queue: queued jobs
  - Service health gauges
- Alerts (in `core/monitoring.py`):
  - High CPU, memory, low disk
  - Service down, job failure rate
  - Low VTXO inventory

Admin API for monitoring:
- `GET /admin/health/comprehensive`
- `GET /admin/metrics/system?hours=24`
- `GET /admin/alerts`
- `GET /admin/alerts/rules`
- `POST /admin/alerts/rules/{rule_name}/toggle`

---

## 5. Operations Tasks

- Reconnect gRPC clients: `GET /grpc/reconnect/{arkd|tapd|lnd}`
- Start/stop Nostr service: `POST /nostr/start`, `POST /nostr/stop`
- Start/stop VTXO monitors: `POST /vtxos/monitor/start`, `POST /vtxos/monitor/stop`
- Cleanup expired items:
  - Sessions/challenges: `POST /sessions/cleanup`
  - VTXOs: `POST /assets/cleanup-vtxos` or `POST /vtxos/cleanup`

Admin maintenance:
- Cleanup old data (logs/metrics): `POST /admin/maintenance/cleanup` body: `{ "days": 30, "dry_run": true }`
- Recent logs (proxy via job logs): `GET /admin/logs/recent?limit=100&level=failed|running|completed`
- Database stats: `GET /admin/database/stats`
- Services snapshot: `GET /admin/services/status`

---

## 6. Backups & Restore

- Create DB backup (MariaDB/MySQL): `POST /admin/backup/create` body: `{ "type": "full" | "schema" }`
  - Responds with `/tmp/<backup_id>.sql` details
- Suggested production backup strategy:
  - Nightly full dumps + hourly binlogs (outside of app via managed DB tooling)
  - Encrypt and store to durable storage (S3/GCS) with rotation policy
- Restore (operator task):
  - Follow DB provider’s restore steps (import .sql, point app to restored DB URL)

---

## 7. Logging

- Structured JSON logs via `core/monitoring.py` to `logs/arkrelay.log` and `logs/arkrelay_errors.log`
- Gunicorn access/error logs should be centralized (stdout > collector)
- Ensure log rotation in production

---

## 8. Security & Secrets

- `ADMIN_API_KEY`: required for all `/admin/*` endpoints
- Do not store `NOSTR_PRIVATE_KEY` or macaroons in the repo; inject via env/secret manager
- Limit network access to DB, Redis, and gRPC daemons; use mTLS if possible
- Shield admin endpoints behind an internal network/VPN and WAF where applicable

---

## 9. Scaling & Performance

- API:
  - Gunicorn workers: start with `workers = CPU*2`, tune via latency and CPU
  - Enable async workers only if needed (I/O heavy)
- DB Pool (`DatabaseConnectionPool` in `core/cache_manager.py`):
  - Tune pool size/overflow via env and workload patterns
- Redis:
  - Monitor memory and eviction policy; persist if needed
  - RQ worker concurrency = #workers * threads (start small, increase gradually)
- Caching:
  - Use the cache decorators for expensive queries
  - Validate cache invalidation on mutable paths

---

## 10. Runbooks (Common Incidents)

- High CPU / Memory / Disk
  - Check `/admin/metrics/system`, `/admin/alerts`
  - Scale instances or tune workers
- Redis unavailable
  - `GET /queue-status` fails or Redis errors in logs
  - Restart Redis, drain dead workers, re-enqueue as needed
- DB connectivity issues
  - `GET /health` and `/admin/health/comprehensive` show DB unhealthy
  - Failover to replica / fix credentials / increase pool timeout
- gRPC daemons unhealthy
  - `GET /health` and `/grpc/arkd|tapd|lnd` helpers
  - `GET /grpc/reconnect/{service}` and validate daemon hosts/ports/certs
- Low VTXO inventory
  - `/vtxos/inventory/{asset_id}` and `/vtxos/stats`
  - Trigger replenishment: `POST /vtxos/batch/create` or automated monitor
- High job failure rate
  - `/admin/jobs/statistics` and recent logs via `/admin/logs/recent`
  - Investigate failing task types; rollback recent changes

---

## 11. Deployment Guidance

- Environment-based configs via `.env` or secret manager
- Container orchestration (K8s/systemd):
  - Separate processes: API, RQ worker(s), Scheduler
  - Liveness/readiness: `/ready` for probes
  - Logging to stdout; sidecar/agent for shipping
- DB migrations: CI stage running `alembic upgrade head`

---

## 12. Change Management

- CI: run `uv run pytest -q` as a gate (stable subset)
- Track app version and changelog
- Feature flags via env when feasible (e.g., auto-start toggles)

---

## 13. Reference Admin Endpoints

- Health: `/admin/health/comprehensive`
- Metrics: `/admin/metrics/system`, `/admin/dashboard/summary`
- Services/DB: `/admin/services/status`, `/admin/database/stats`
- Alerts: `/admin/alerts`, `/admin/alerts/rules`, toggle
- Maintenance: `/admin/maintenance/cleanup`
- Backup: `/admin/backup/create`
- Performance profile: `/admin/performance/profile`
- Restart stub: `/admin/restart/service`

Include header: `X-Admin-Key: <ADMIN_API_KEY>` on all `/admin/*` requests.
