# ArkRelay Gateway

A Flask-based gateway service for managing background tasks, scheduling, and system monitoring using Redis Queue and MariaDB.

## Features

- **Web Gateway**: Flask-based REST API with endpoints for job management and monitoring
- **Task Queue**: Redis Queue (RQ) for background job processing
- **Scheduler**: Periodic task scheduling for system monitoring and maintenance
- **Database Integration**: MariaDB with SQLAlchemy ORM for persistent storage
- **System Monitoring**: Real-time system metrics and heartbeat monitoring
- **Job Tracking**: Comprehensive logging and status tracking for all tasks
- **gRPC Client Layer**: Unified interface for ARKD, TAPD, and LND daemon communication
- **Circuit Breaker**: Fault tolerance and graceful degradation for gRPC services
- **Service Health Monitoring**: Real-time health checks for all backend daemons

## Architecture

- **Web Service**: Flask application (`app.py`) - Port 8000
- **Worker Service**: RQ worker for processing background tasks
- **Scheduler Service**: Periodic task scheduler (`scheduler.py`)
- **Database**: MariaDB for persistent storage
- **Queue**: Redis for job queuing and scheduling

## Installation

### Prerequisites
- Python 3.12+
- Redis server
- MariaDB server

### Setup
1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd arkrelay/gateway
   ```

2. **Install dependencies**:
   ```bash
   # Using uv (recommended)
   uv sync

   # Or using pip
   pip install -r requirements.txt
   ```

3. **Environment Configuration**:
   Create a `.env` file with the following environment variables:
   ```env
   # Database Configuration
   DATABASE_URL=mysql+pymysql://user:password@mariadb:3306/arkrelay

   # Redis Configuration
   REDIS_URL=redis://redis:6379/0
   ```

4. **Database Setup**:
   ```bash
   # Run database migrations
   alembic upgrade head

   # Or create tables directly
   python -c "from models import create_tables; create_tables()"
   ```

## Usage

### Starting the Services

1. **Web Service**:
   ```bash
   python app.py
   ```
   Or using gunicorn:
   ```bash
   gunicorn app:app -b 0.0.0.0:8000
   ```

2. **Scheduler Service**:
   ```bash
   python scheduler.py
   ```

3. **Worker Service**:
   ```bash
   rq worker
   ```

### API Endpoints

#### Health & Status
- `GET /` - Gateway information
- `GET /health` - System health check
- `GET /queue-status` - Queue statistics

#### Job Management
- `GET /enqueue-demo` - Enqueue a demo job
- `POST /enqueue-user-process` - Enqueue user processing job
- `GET /jobs` - List recent jobs
- `GET /jobs/<job_id>` - Get specific job details
- `GET /stats` - System statistics and job metrics

#### Monitoring
- `GET /metrics` - System metrics (CPU, memory, disk)
- `GET /heartbeats` - Service heartbeat status

### Example API Usage

#### Enqueue a User Processing Job
```bash
curl -X POST http://localhost:8000/enqueue-user-process \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "12345",
    "action_type": "process",
    "data": {"key": "value", "items": [1, 2, 3]}
  }'
```

#### Check Queue Status
```bash
curl http://localhost:8000/queue-status
```

#### Get System Statistics
```bash
curl http://localhost:8000/stats
```

### Scheduled Tasks

The scheduler automatically runs the following periodic tasks:

- **System Stats**: Every 5 minutes - Logs CPU, memory, and disk usage
- **Heartbeat**: Every 1 minute - Service health monitoring
- **Cleanup**: Every hour - Cleanup and maintenance operations

## Database Schema

### job_logs
- `id` (Primary Key)
- `job_type` - Type of job (e.g., 'sample_task', 'cleanup', 'user_process')
- `job_id` - Unique job identifier
- `status` - Job status (pending, running, completed, failed)
- `message` - Job description or error message
- `result_data` - JSON results
- `created_at`, `updated_at` - Timestamps
- `duration_seconds` - Job execution time

### system_metrics
- `id` (Primary Key)
- `cpu_percent` - CPU usage percentage
- `memory_percent` - Memory usage percentage
- `memory_available_mb` - Available memory in MB
- `disk_percent` - Disk usage percentage
- `disk_free_gb` - Free disk space in GB
- `timestamp` - Metric timestamp

### heartbeats
- `id` (Primary Key)
- `service_name` - Service identifier
- `is_alive` - Service status
- `message` - Heartbeat message
- `timestamp` - Heartbeat timestamp

## Task Functions

### Available Tasks
- `sample_task(message)` - Demo task with logging
- `log_system_stats()` - Collect and log system metrics
- `cleanup_old_logs()` - Simulate cleanup operations
- `send_heartbeat()` - Service heartbeat monitoring
- `process_user_data(user_id, action_type, data)` - Process user data

## Configuration

### Environment Variables
- `DATABASE_URL` - MariaDB connection string
- `REDIS_URL` - Redis connection string
- `FLASK_ENV` - Flask environment (development/production)

### Docker Deployment

The project is designed to work with Docker Compose. Typical deployment:

```yaml
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=mysql+pymysql://user:password@mariadb:3306/arkrelay
      - REDIS_URL=redis://redis:6379/0

  scheduler:
    build: .
    command: python scheduler.py
    environment:
      - DATABASE_URL=mysql+pymysql://user:password@mariadb:3306/arkrelay
      - REDIS_URL=redis://redis:6379/0

  worker:
    build: .
    command: rq worker
    environment:
      - DATABASE_URL=mysql+pymysql://user:password@mariadb:3306/arkrelay
      - REDIS_URL=redis://redis:6379/0
```

## Development

### Running Tests
```bash
# Run all tests
uv run pytest

# Run unit tests only
uv run pytest -m unit

# Run with coverage
uv run pytest --cov=.

# Run specific test file
uv run pytest test_tasks.py
```

**Current Test Status:**
- **Unit Tests**: 41/67 passing (61.2% success rate)
- **Total Test Suite**: 1,093 comprehensive tests
- **Coverage Areas**: Flask app, Core config, Lightning integration, Session management, and more

### Code Quality
```bash
# Lint code
flake8 .

# Type checking
mypy .
```

## Monitoring

### Health Checks
- Web service: `GET /health`
- Redis connection: Automatic ping verification
- Database connection: SQL query test

### Metrics Collection
- CPU usage percentage
- Memory usage and availability
- Disk usage and free space
- Job queue statistics
- Success/failure rates

## License

Add your license information here.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Support

For issues and questions, please create an issue in the repository.