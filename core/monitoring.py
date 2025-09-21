"""
Comprehensive monitoring and operations system for ArkRelay Gateway.
Implements advanced logging, metrics collection, alerting, and system health monitoring.
"""

import logging
import json
import time
import threading
import psutil
import socket
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from redis import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import requests
import os

from core.config import Config
from core.models import (
    JobLog, SystemMetrics, Heartbeat,
    SigningSession, Vtxo, Transaction,
    Asset, get_session
)

# Configure logging with structured format
class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging"""

    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # Add extra fields if provided
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)

# Setup structured logging
def setup_comprehensive_logging():
    """Setup comprehensive logging system with multiple handlers"""

    # Create logger
    logger = logging.getLogger('arkrelay')
    logger.setLevel(getattr(logging, Config.LOG_LEVEL))

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler with structured format
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(StructuredFormatter())
    logger.addHandler(console_handler)

    # File handler for persistent logs
    file_handler = logging.FileHandler('logs/arkrelay.log')
    file_handler.setFormatter(StructuredFormatter())
    logger.addHandler(file_handler)

    # Error file handler for errors only
    error_handler = logging.FileHandler('logs/arkrelay_errors.log')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(StructuredFormatter())
    logger.addHandler(error_handler)

    return logger

# Prometheus metrics
class PrometheusMetrics:
    """Prometheus metrics collection"""

    def __init__(self):
        # Business metrics
        self.transactions_processed = Counter(
            'arkrelay_transactions_processed_total',
            'Total number of transactions processed',
            ['transaction_type', 'status']
        )

        self.sessions_created = Counter(
            'arkrelay_sessions_created_total',
            'Total number of signing sessions created',
            ['session_type']
        )

        self.vtxos_created = Counter(
            'arkrelay_vtxos_created_total',
            'Total number of VTXOs created',
            ['asset_id']
        )

        self.vtxos_assigned = Counter(
            'arkrelay_vtxos_assigned_total',
            'Total number of VTXOs assigned to users',
            ['asset_id']
        )

        # Performance metrics
        self.request_duration = Histogram(
            'arkrelay_request_duration_seconds',
            'Request processing duration',
            ['endpoint', 'method']
        )

        self.database_query_duration = Histogram(
            'arkrelay_database_query_duration_seconds',
            'Database query duration',
            ['query_type']
        )

        # System metrics
        self.system_cpu_percent = Gauge(
            'arkrelay_system_cpu_percent',
            'System CPU usage percentage'
        )

        self.system_memory_percent = Gauge(
            'arkrelay_system_memory_percent',
            'System memory usage percentage'
        )

        self.system_disk_percent = Gauge(
            'arkrelay_system_disk_percent',
            'System disk usage percentage'
        )

        # Service health
        self.service_health = Gauge(
            'arkrelay_service_health',
            'Service health status (1=healthy, 0=unhealthy)',
            ['service_name']
        )

        self.active_sessions = Gauge(
            'arkrelay_active_sessions_total',
            'Number of active signing sessions',
            ['session_type']
        )

        self.queued_jobs = Gauge(
            'arkrelay_queued_jobs_total',
            'Number of queued jobs'
        )

        self.failed_jobs = Counter(
            'arkrelay_failed_jobs_total',
            'Total number of failed jobs',
            ['job_type']
        )

@dataclass
class AlertRule:
    """Alert rule configuration"""
    name: str
    metric_name: str
    threshold: float
    comparison: str  # 'gt', 'lt', 'eq'
    duration_minutes: int
    severity: str  # 'low', 'medium', 'high', 'critical'
    message_template: str
    enabled: bool = True

@dataclass
class Alert:
    """Alert instance"""
    rule_name: str
    severity: str
    message: str
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = None

class AlertingSystem:
    """Advanced alerting system"""

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.logger = logging.getLogger('arkrelay.alerting')
        self.alert_rules: List[AlertRule] = []
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self.monitoring_thread = None
        self.running = False

        self._setup_default_alert_rules()

    def _setup_default_alert_rules(self):
        """Setup default alert rules"""
        self.alert_rules = [
            AlertRule(
                name="high_cpu_usage",
                metric_name="cpu_percent",
                threshold=80.0,
                comparison="gt",
                duration_minutes=5,
                severity="high",
                message_template="High CPU usage: {value}% for {duration} minutes"
            ),
            AlertRule(
                name="high_memory_usage",
                metric_name="memory_percent",
                threshold=85.0,
                comparison="gt",
                duration_minutes=5,
                severity="high",
                message_template="High memory usage: {value}% for {duration} minutes"
            ),
            AlertRule(
                name="low_disk_space",
                metric_name="disk_percent",
                threshold=90.0,
                comparison="gt",
                duration_minutes=1,
                severity="critical",
                message_template="Low disk space: {value}% remaining"
            ),
            AlertRule(
                name="service_down",
                metric_name="service_health",
                threshold=0.5,
                comparison="lt",
                duration_minutes=2,
                severity="critical",
                message_template="Service {service} is down"
            ),
            AlertRule(
                name="high_job_failure_rate",
                metric_name="job_failure_rate",
                threshold=10.0,
                comparison="gt",
                duration_minutes=10,
                severity="medium",
                message_template="High job failure rate: {value}% over last 10 minutes"
            ),
            AlertRule(
                name="vtxo_inventory_low",
                metric_name="vtxo_inventory_ratio",
                threshold=0.2,
                comparison="lt",
                duration_minutes=5,
                severity="medium",
                message_template="Low VTXO inventory for asset {asset}: {value}% remaining"
            )
        ]

    def start_monitoring(self):
        """Start alert monitoring thread"""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            return

        self.running = True
        self.monitoring_thread = threading.Thread(target=self._monitor_alerts)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        self.logger.info("Alert monitoring started")

    def stop_monitoring(self):
        """Stop alert monitoring"""
        self.running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        self.logger.info("Alert monitoring stopped")

    def _monitor_alerts(self):
        """Monitor alerts in background thread"""
        while self.running:
            try:
                self._check_all_rules()
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                self.logger.error(f"Error in alert monitoring: {e}")
                time.sleep(60)  # Wait longer on error

    def _check_all_rules(self):
        """Check all alert rules"""
        for rule in self.alert_rules:
            if not rule.enabled:
                continue

            try:
                self._check_rule(rule)
            except Exception as e:
                self.logger.error(f"Error checking alert rule {rule.name}: {e}")

    def _check_rule(self, rule: AlertRule):
        """Check a specific alert rule"""
        # Get current metric value
        current_value = self._get_metric_value(rule)
        if current_value is None:
            return

        # Check if threshold is exceeded
        threshold_exceeded = self._check_threshold(current_value, rule.threshold, rule.comparison)

        if threshold_exceeded:
            # Check if this is a new or ongoing alert
            alert_key = f"{rule.name}_{rule.metric_name}"

            if alert_key not in self.active_alerts:
                # New alert
                alert = Alert(
                    rule_name=rule.name,
                    severity=rule.severity,
                    message=rule.message_template.format(value=current_value, duration=rule.duration_minutes),
                    triggered_at=datetime.utcnow(),
                    metadata={'metric_value': current_value, 'threshold': rule.threshold}
                )

                self.active_alerts[alert_key] = alert
                self._trigger_alert(alert)
            else:
                # Update existing alert
                alert = self.active_alerts[alert_key]
                alert.metadata['metric_value'] = current_value
                alert.metadata['last_checked'] = datetime.utcnow().isoformat()

        else:
            # Check if we should resolve the alert
            alert_key = f"{rule.name}_{rule.metric_name}"
            if alert_key in self.active_alerts:
                alert = self.active_alerts[alert_key]
                alert.resolved_at = datetime.utcnow()
                self._resolve_alert(alert)
                del self.active_alerts[alert_key]
                self.alert_history.append(alert)

    def _get_metric_value(self, rule: AlertRule) -> Optional[float]:
        """Get current metric value for a rule"""
        try:
            if rule.metric_name == "cpu_percent":
                return psutil.cpu_percent(interval=1)
            elif rule.metric_name == "memory_percent":
                return psutil.virtual_memory().percent
            elif rule.metric_name == "disk_percent":
                return psutil.disk_usage('/').percent
            elif rule.metric_name == "service_health":
                # Check service health from database
                session = get_session()
                try:
                    recent_heartbeats = session.query(Heartbeat).filter(
                        Heartbeat.timestamp >= datetime.utcnow() - timedelta(minutes=2)
                    ).all()
                    return len(recent_heartbeats) / 3.0  # Normalize to 0-1
                finally:
                    session.close()
            elif rule.metric_name == "job_failure_rate":
                # Calculate job failure rate
                session = get_session()
                try:
                    recent_jobs = session.query(JobLog).filter(
                        JobLog.created_at >= datetime.utcnow() - timedelta(minutes=10)
                    ).all()
                    if not recent_jobs:
                        return 0.0

                    failed_jobs = sum(1 for job in recent_jobs if job.status == 'failed')
                    return (failed_jobs / len(recent_jobs)) * 100
                finally:
                    session.close()
            elif rule.metric_name == "vtxo_inventory_ratio":
                # Check VTXO inventory levels
                session = get_session()
                try:
                    # This is a simplified check - in reality, you'd check per asset
                    total_vtxos = session.query(Vtxo).count()
                    available_vtxos = session.query(Vtxo).filter(Vtxo.status == 'available').count()

                    if total_vtxos == 0:
                        return 0.0

                    return available_vtxos / total_vtxos
                finally:
                    session.close()
        except Exception as e:
            self.logger.error(f"Error getting metric value for {rule.metric_name}: {e}")
            return None

    def _check_threshold(self, value: float, threshold: float, comparison: str) -> bool:
        """Check if value exceeds threshold"""
        if comparison == "gt":
            return value > threshold
        elif comparison == "lt":
            return value < threshold
        elif comparison == "eq":
            return abs(value - threshold) < 0.001
        return False

    def _trigger_alert(self, alert: Alert):
        """Trigger an alert"""
        self.logger.warning(f"ALERT [{alert.severity.upper()}] {alert.message}")

        # Store alert in Redis for web UI
        alert_data = {
            'rule_name': alert.rule_name,
            'severity': alert.severity,
            'message': alert.message,
            'triggered_at': alert.triggered_at.isoformat(),
            'metadata': alert.metadata
        }

        self.redis.lpush('arkrelay:alerts:active', json.dumps(alert_data))
        self.redis.ltrim('arkrelay:alerts:active', 0, 99)  # Keep last 100 alerts

        # Send to external alerting systems if configured
        self._send_external_alert(alert)

    def _resolve_alert(self, alert: Alert):
        """Resolve an alert"""
        self.logger.info(f"Alert resolved: {alert.message}")

        # Update Redis
        self.redis.lrem('arkrelay:alerts:active', 1, json.dumps({
            'rule_name': alert.rule_name,
            'severity': alert.severity,
            'message': alert.message,
            'triggered_at': alert.triggered_at.isoformat(),
            'metadata': alert.metadata
        }))

    def _send_external_alert(self, alert: Alert):
        """Send alert to external systems (Slack, email, etc.)"""
        # Example: Send to Slack webhook
        slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
        if slack_webhook:
            try:
                message = {
                    'text': f"🚨 [{alert.severity.upper()}] {alert.message}",
                    'attachments': [
                        {
                            'color': self._get_severity_color(alert.severity),
                            'fields': [
                                {'title': 'Rule', 'value': alert.rule_name, 'short': True},
                                {'title': 'Triggered At', 'value': alert.triggered_at.isoformat(), 'short': True}
                            ]
                        }
                    ]
                }

                requests.post(slack_webhook, json=message, timeout=10)
            except Exception as e:
                self.logger.error(f"Failed to send Slack alert: {e}")

    def _get_severity_color(self, severity: str) -> str:
        """Get color for Slack message based on severity"""
        colors = {
            'low': '#36a64f',      # green
            'medium': '#ff9500',   # orange
            'high': '#ff0000',     # red
            'critical': '#990000'  # dark red
        }
        return colors.get(severity, '#808080')

    def get_active_alerts(self) -> List[Dict]:
        """Get currently active alerts"""
        try:
            alerts_data = self.redis.lrange('arkrelay:alerts:active', 0, -1)
            return [json.loads(alert) for alert in alerts_data]
        except Exception as e:
            self.logger.error(f"Error getting active alerts: {e}")
            return []

    def add_custom_alert_rule(self, rule: AlertRule):
        """Add a custom alert rule"""
        self.alert_rules.append(rule)
        self.logger.info(f"Added custom alert rule: {rule.name}")

class HealthChecker:
    """Comprehensive health checking system"""

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.logger = logging.getLogger('arkrelay.health')
        self.prometheus_metrics = PrometheusMetrics()

        # Start Prometheus metrics server
        if Config.ENABLE_METRICS:
            try:
                start_http_server(Config.METRICS_PORT)
                self.logger.info(f"Prometheus metrics server started on port {Config.METRICS_PORT}")
            except Exception as e:
                self.logger.error(f"Failed to start Prometheus metrics server: {e}")

    def check_database_health(self) -> Dict[str, Any]:
        """Check database connectivity and performance"""
        start_time = time.time()
        session = get_session()

        try:
            # Test basic connectivity
            result = session.execute(text("SELECT 1")).fetchone()
            db_connected = result[0] == 1

            # Test performance with a more complex query
            perf_start = time.time()
            session.execute(text("SELECT COUNT(*) FROM job_logs WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)"))
            query_time = (time.time() - perf_start) * 1000  # Convert to ms

            # Get table sizes
            tables_info = []
            tables = ['job_logs', 'system_metrics', 'heartbeats', 'signing_sessions', 'vtxos']
            for table in tables:
                try:
                    count_result = session.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()
                    tables_info.append({'name': table, 'count': count_result[0]})
                except Exception:
                    continue

            status = {
                'healthy': db_connected,
                'query_time_ms': round(query_time, 2),
                'tables': tables_info,
                'timestamp': datetime.utcnow().isoformat()
            }

            # Update Prometheus metrics
            self.prometheus_metrics.database_query_duration.observe(
                query_time / 1000, 'health_check'
            )

            return status

        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            return {
                'healthy': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
        finally:
            session.close()

    def check_redis_health(self) -> Dict[str, Any]:
        """Check Redis connectivity and performance"""
        try:
            start_time = time.time()
            self.redis.ping()
            ping_time = (time.time() - start_time) * 1000

            # Get Redis info
            info = self.redis.info()

            status = {
                'healthy': True,
                'ping_time_ms': round(ping_time, 2),
                'used_memory_mb': info.get('used_memory', 0) / (1024 * 1024),
                'connected_clients': info.get('connected_clients', 0),
                'total_commands_processed': info.get('total_commands_processed', 0),
                'timestamp': datetime.utcnow().isoformat()
            }

            return status

        except Exception as e:
            self.logger.error(f"Redis health check failed: {e}")
            return {
                'healthy': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    def check_grpc_services_health(self) -> Dict[str, Any]:
        """Check gRPC services health"""
        try:
            from grpc_clients import get_grpc_manager, ServiceType
            grpc_manager = get_grpc_manager()

            services_health = grpc_manager.health_check_all()

            # Update Prometheus metrics
            for service_name, is_healthy in services_health.items():
                self.prometheus_metrics.service_health.labels(
                    service_name=service_name.lower()
                ).set(1 if is_healthy else 0)

            return {
                'healthy': all(services_health.values()),
                'services': {
                    'arkd': services_health.get(ServiceType.ARKD, False),
                    'tapd': services_health.get(ServiceType.TAPD, False),
                    'lnd': services_health.get(ServiceType.LND, False)
                },
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            self.logger.error(f"gRPC services health check failed: {e}")
            return {
                'healthy': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    def check_nostr_health(self) -> Dict[str, Any]:
        """Check Nostr service health"""
        try:
            from nostr_clients.nostr_client import get_nostr_client
            nostr_client = get_nostr_client()

            if not nostr_client:
                return {
                    'healthy': False,
                    'error': 'Nostr client not initialized',
                    'timestamp': datetime.utcnow().isoformat()
                }

            stats = nostr_client.get_stats()

            return {
                'healthy': stats.get('running', False),
                'connected_relays': stats.get('connected_relays', 0),
                'events_received': stats.get('events_received', 0),
                'events_published': stats.get('events_published', 0),
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Nostr health check failed: {e}")
            return {
                'healthy': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    def comprehensive_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check of all services"""
        health_status = {
            'overall_healthy': True,
            'checks': {},
            'timestamp': datetime.utcnow().isoformat()
        }

        # Run all health checks
        checks = [
            ('database', self.check_database_health),
            ('redis', self.check_redis_health),
            ('grpc_services', self.check_grpc_services_health),
            ('nostr', self.check_nostr_health)
        ]

        for check_name, check_func in checks:
            try:
                result = check_func()
                health_status['checks'][check_name] = result

                if not result.get('healthy', False):
                    health_status['overall_healthy'] = False

            except Exception as e:
                self.logger.error(f"Health check {check_name} failed: {e}")
                health_status['checks'][check_name] = {
                    'healthy': False,
                    'error': str(e),
                    'timestamp': datetime.utcnow().isoformat()
                }
                health_status['overall_healthy'] = False

        # Update overall system health metric
        overall_health = 1 if health_status['overall_healthy'] else 0
        self.prometheus_metrics.service_health.labels(service_name='overall').set(overall_health)

        return health_status

class MonitoringSystem:
    """Main monitoring system coordinator"""

    def __init__(self):
        self.logger = setup_comprehensive_logging()
        self.redis = Redis.from_url(Config.REDIS_URL)
        self.alerting_system = AlertingSystem(self.redis)
        self.health_checker = HealthChecker(self.redis)
        self.prometheus_metrics = PrometheusMetrics()

        # System monitoring thread
        self.monitoring_thread = None
        self.running = False

    def start(self):
        """Start all monitoring systems"""
        self.logger.info("Starting monitoring system...")

        # Start alerting system
        self.alerting_system.start_monitoring()

        # Start system monitoring
        self.start_system_monitoring()

        self.logger.info("Monitoring system started successfully")

    def stop(self):
        """Stop all monitoring systems"""
        self.logger.info("Stopping monitoring system...")

        # Stop alerting system
        self.alerting_system.stop_monitoring()

        # Stop system monitoring
        self.running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)

        self.logger.info("Monitoring system stopped")

    def start_system_monitoring(self):
        """Start continuous system monitoring"""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            return

        self.running = True
        self.monitoring_thread = threading.Thread(target=self._monitor_system)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        self.logger.info("System monitoring started")

    def _monitor_system(self):
        """Monitor system metrics continuously"""
        while self.running:
            try:
                # Collect system metrics
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')

                # Update Prometheus metrics
                self.prometheus_metrics.system_cpu_percent.set(cpu_percent)
                self.prometheus_metrics.system_memory_percent.set(memory.percent)
                self.prometheus_metrics.system_disk_percent.set(disk.percent)

                # Collect business metrics
                self._update_business_metrics()

                # Store in database
                self._store_system_metrics(cpu_percent, memory, disk)

                # Sleep before next collection
                time.sleep(60)  # Collect every minute

            except Exception as e:
                self.logger.error(f"Error in system monitoring: {e}")
                time.sleep(60)  # Wait before retrying

    def _update_business_metrics(self):
        """Update business metrics"""
        try:
            session = get_session()

            # Update active sessions gauge
            active_sessions = session.query(SigningSession).filter(
                SigningSession.status.in_(['initiated', 'challenge_sent', 'awaiting_signature', 'signing'])
            ).count()

            self.prometheus_metrics.active_sessions.labels(session_type='all').set(active_sessions)

            # Update queued jobs gauge
            queued_count = self.redis.llen('rq:queue:default')
            self.prometheus_metrics.queued_jobs.set(queued_count)

            session.close()

        except Exception as e:
            self.logger.error(f"Error updating business metrics: {e}")

    def _store_system_metrics(self, cpu_percent: float, memory, disk):
        """Store system metrics in database"""
        try:
            session = get_session()

            metrics = SystemMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_available_mb=memory.available / (1024 * 1024),
                disk_percent=disk.percent,
                disk_free_gb=disk.free / (1024**3)
            )

            session.add(metrics)
            session.commit()
            session.close()

        except Exception as e:
            self.logger.error(f"Error storing system metrics: {e}")

# Global monitoring system instance
_monitoring_system = None

def get_monitoring_system() -> MonitoringSystem:
    """Get the global monitoring system instance"""
    global _monitoring_system
    if _monitoring_system is None:
        _monitoring_system = MonitoringSystem()
    return _monitoring_system

def initialize_monitoring():
    """Initialize the monitoring system"""
    monitoring_system = get_monitoring_system()
    monitoring_system.start()
    return monitoring_system

def shutdown_monitoring():
    """Shutdown the monitoring system"""
    monitoring_system = get_monitoring_system()
    monitoring_system.stop()