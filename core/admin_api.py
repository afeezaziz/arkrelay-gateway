"""
Administrative API endpoints for ArkRelay Gateway monitoring and management.
"""

from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
import json
import os
import subprocess
import threading
import time
from sqlalchemy import func, desc
import psutil
from functools import wraps

from core.models import (
    JobLog, SystemMetrics, Heartbeat, SigningSession,
    Vtxo, Transaction, Asset, get_session
)
from core.monitoring import get_monitoring_system, PrometheusMetrics
from core.config import Config

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Authentication decorator for admin endpoints
def require_admin_auth(f):
    """Decorator to require admin authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Simple admin key authentication - in production, use proper auth
        admin_key = request.headers.get('X-Admin-Key') or request.args.get('admin_key')
        expected_key = os.getenv('ADMIN_API_KEY')

        if not expected_key:
            return jsonify({'error': 'Admin API not configured'}), 503

        if admin_key != expected_key:
            return jsonify({'error': 'Unauthorized'}), 401

        return f(*args, **kwargs)
    return decorated_function

def utc_now() -> datetime:
    """Return current UTC time as a naive datetime (UTC) without deprecation warnings."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

@admin_bp.route('/health/comprehensive')
@require_admin_auth
def comprehensive_health_check():
    """Comprehensive health check of all services"""
    try:
        monitoring_system = get_monitoring_system()
        health_status = monitoring_system.health_checker.comprehensive_health_check()

        return jsonify({
            'status': health_status,
            'timestamp': utc_now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/metrics/system')
@require_admin_auth
def get_system_metrics():
    """Get detailed system metrics"""
    try:
        hours = request.args.get('hours', 24, type=int)
        session = get_session()

        # Get system metrics for the specified time range
        since = utc_now() - timedelta(hours=hours)
        metrics = session.query(SystemMetrics).filter(
            SystemMetrics.timestamp >= since
        ).order_by(SystemMetrics.timestamp.desc()).all()

        metrics_data = []
        for metric in metrics:
            metrics_data.append({
                'id': metric.id,
                'cpu_percent': metric.cpu_percent,
                'memory_percent': metric.memory_percent,
                'memory_available_mb': metric.memory_available_mb,
                'disk_percent': metric.disk_percent,
                'disk_free_gb': metric.disk_free_gb,
                'timestamp': metric.timestamp.isoformat()
            })

        session.close()

        return jsonify({
            'metrics': metrics_data,
            'time_range_hours': hours,
            'count': len(metrics_data),
            'timestamp': utc_now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/alerts')
@require_admin_auth
def get_alerts():
    """Get active and recent alerts"""
    try:
        monitoring_system = get_monitoring_system()
        active_alerts = monitoring_system.alerting_system.get_active_alerts()

        # Get alert history from database if needed
        history_limit = request.args.get('history_limit', 50, type=int)

        return jsonify({
            'active_alerts': active_alerts,
            'active_count': len(active_alerts),
            'history_limit': history_limit,
            'timestamp': utc_now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/alerts/rules')
@require_admin_auth
def get_alert_rules():
    """Get alert rules configuration"""
    try:
        monitoring_system = get_monitoring_system()
        rules = monitoring_system.alerting_system.alert_rules

        rules_data = []
        for rule in rules:
            rules_data.append({
                'name': rule.name,
                'metric_name': rule.metric_name,
                'threshold': rule.threshold,
                'comparison': rule.comparison,
                'duration_minutes': rule.duration_minutes,
                'severity': rule.severity,
                'message_template': rule.message_template,
                'enabled': rule.enabled
            })

        return jsonify({
            'rules': rules_data,
            'count': len(rules_data),
            'timestamp': utc_now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/alerts/rules/<rule_name>/toggle', methods=['POST'])
@require_admin_auth
def toggle_alert_rule(rule_name):
    """Enable/disable an alert rule"""
    try:
        data = request.get_json() or {}
        enabled = data.get('enabled', True)

        monitoring_system = get_monitoring_system()

        for rule in monitoring_system.alerting_system.alert_rules:
            if rule.name == rule_name:
                rule.enabled = enabled
                return jsonify({
                    'message': f'Alert rule {rule_name} {"enabled" if enabled else "disabled"}',
                    'rule_name': rule_name,
                    'enabled': enabled,
                    'timestamp': utc_now().isoformat()
                })

        return jsonify({'error': f'Alert rule {rule_name} not found'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/jobs/statistics')
@require_admin_auth
def get_job_statistics():
    """Get detailed job statistics"""
    try:
        hours = request.args.get('hours', 24, type=int)
        session = get_session()

        since = utc_now() - timedelta(hours=hours)

        # Get job counts by status
        status_counts = session.query(
            JobLog.status,
            func.count(JobLog.id).label('count')
        ).filter(
            JobLog.created_at >= since
        ).group_by(JobLog.status).all()

        # Get job counts by type
        type_counts = session.query(
            JobLog.job_type,
            func.count(JobLog.id).label('count')
        ).filter(
            JobLog.created_at >= since
        ).group_by(JobLog.job_type).all()

        # Get average duration by job type
        duration_stats = session.query(
            JobLog.job_type,
            func.avg(JobLog.duration_seconds).label('avg_duration'),
            func.min(JobLog.duration_seconds).label('min_duration'),
            func.max(JobLog.duration_seconds).label('max_duration')
        ).filter(
            JobLog.created_at >= since,
            JobLog.status == 'completed',
            JobLog.duration_seconds.isnot(None)
        ).group_by(JobLog.job_type).all()

        # Get failure rate by hour
        failure_rates = []
        for i in range(hours):
            hour_start = utc_now() - timedelta(hours=i+1)
            hour_end = utc_now() - timedelta(hours=i)

            total_jobs = session.query(JobLog).filter(
                JobLog.created_at >= hour_start,
                JobLog.created_at < hour_end
            ).count()

            failed_jobs = session.query(JobLog).filter(
                JobLog.created_at >= hour_start,
                JobLog.created_at < hour_end,
                JobLog.status == 'failed'
            ).count()

            failure_rate = (failed_jobs / total_jobs * 100) if total_jobs > 0 else 0

            failure_rates.append({
                'hour': hour_start.isoformat(),
                'total_jobs': total_jobs,
                'failed_jobs': failed_jobs,
                'failure_rate': round(failure_rate, 2)
            })

        session.close()

        return jsonify({
            'time_range_hours': hours,
            'status_counts': {status: count for status, count in status_counts},
            'type_counts': {job_type: count for job_type, count in type_counts},
            'duration_stats': [
                {
                    'job_type': stat.job_type,
                    'avg_duration': round(stat.avg_duration, 2) if stat.avg_duration else 0,
                    'min_duration': stat.min_duration,
                    'max_duration': stat.max_duration
                }
                for stat in duration_stats
            ],
            'failure_rates': failure_rates,
            'timestamp': utc_now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/services/status')
@require_admin_auth
def get_services_status():
    """Get status of all services"""
    try:
        monitoring_system = get_monitoring_system()
        redis_client = monitoring_system.redis

        # Queue status
        queued_jobs = redis_client.llen('rq:queue:default')
        scheduled_jobs = len(redis_client.zrange('rq:scheduler:scheduled_jobs', 0, -1))
        failed_jobs = len(redis_client.lrange('rq:failed_registry', 0, -1))

        # Worker count
        workers = redis_client.smembers('rq:workers')
        worker_count = len(workers) if workers is not None else 0

        # Services status from recent heartbeats (last 5 minutes)
        session = get_session()
        try:
            recent_heartbeats = session.query(Heartbeat).filter(
                Heartbeat.timestamp >= utc_now() - timedelta(minutes=5)
            ).order_by(Heartbeat.timestamp.desc()).all()
        finally:
            session.close()

        services_status = [
            {
                'service_name': hb.service_name,
                'last_heartbeat': hb.timestamp.isoformat(),
                'alive': hb.is_alive,
                'message': hb.message
            }
            for hb in recent_heartbeats
        ]

        return jsonify({
            'queue_status': {
                'queued_jobs': queued_jobs,
                'scheduled_jobs': scheduled_jobs,
                'failed_jobs': failed_jobs,
                'worker_count': worker_count
            },
            'services': services_status,
            'timestamp': utc_now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/database/stats')
@require_admin_auth
def get_database_stats():
    """Get database statistics"""
    try:
        session = get_session()

        # Get table sizes
        tables_info = []
        tables = [
            ('job_logs', JobLog),
            ('system_metrics', SystemMetrics),
            ('heartbeats', Heartbeat),
            ('signing_sessions', SigningSession),
            ('vtxos', Vtxo),
            ('transactions', Transaction),
            ('assets', Asset)
        ]

        for table_name, model in tables:
            try:
                count = session.query(model).count()
                latest = session.query(model).order_by(desc(model.id)).first()
                latest_time = latest.created_at.isoformat() if hasattr(latest, 'created_at') and latest.created_at else None

                tables_info.append({
                    'name': table_name,
                    'count': count,
                    'latest_record': latest_time
                })
            except Exception:
                continue

        # Get database size (MySQL specific)
        try:
            db_size_result = session.execute(
                "SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) as size_mb "
                "FROM information_schema.tables "
                "WHERE table_schema = DATABASE()"
            ).fetchone()
            db_size_mb = db_size_result[0] if db_size_result else 0
        except Exception:
            db_size_mb = 0

        session.close()

        return jsonify({
            'database_size_mb': db_size_mb,
            'tables': tables_info,
            'timestamp': utc_now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/system/info')
@require_admin_auth
def get_system_info():
    """Get detailed system information"""
    try:
        # Get system info
        cpu_info = {
            'count': psutil.cpu_count(),
            'count_logical': psutil.cpu_count(logical=True),
            'percent': psutil.cpu_percent(interval=1),
            'freq_current': psutil.cpu_freq().current if psutil.cpu_freq() else 0
        }

        memory = psutil.virtual_memory()
        memory_info = {
            'total_gb': round(memory.total / (1024**3), 2),
            'available_gb': round(memory.available / (1024**3), 2),
            'used_gb': round(memory.used / (1024**3), 2),
            'percent': memory.percent
        }

        disk = psutil.disk_usage('/')
        disk_info = {
            'total_gb': round(disk.total / (1024**3), 2),
            'free_gb': round(disk.free / (1024**3), 2),
            'used_gb': round(disk.used / (1024**3), 2),
            'percent': disk.percent
        }

        # Network info
        network = psutil.net_io_counters()
        network_info = {
            'bytes_sent': network.bytes_sent,
            'bytes_recv': network.bytes_recv,
            'packets_sent': network.packets_sent,
            'packets_recv': network.packets_recv
        }

        # Process info
        process = psutil.Process()
        process_info = {
            'pid': process.pid,
            'memory_usage_mb': round(process.memory_info().rss / (1024 * 1024), 2),
            'cpu_percent': process.cpu_percent(),
            'create_time': datetime.fromtimestamp(process.create_time()).isoformat(),
            'threads': process.num_threads()
        }

        return jsonify({
            'cpu': cpu_info,
            'memory': memory_info,
            'disk': disk_info,
            'network': network_info,
            'process': process_info,
            'timestamp': utc_now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/configuration')
@require_admin_auth
def get_configuration():
    """Get current configuration (excluding sensitive data)"""
    try:
        config_data = {
            'app': {
                'flask_env': Config.FLASK_ENV,
                'app_port': Config.APP_PORT,
                'app_host': Config.APP_HOST,
                'service_type': Config.SERVICE_TYPE
            },
            'logging': {
                'log_level': Config.LOG_LEVEL
            },
            'network': {
                'bitcoin_network': Config.BITCOIN_NETWORK
            },
            'monitoring': {
                'enable_metrics': Config.ENABLE_METRICS,
                'metrics_port': Config.METRICS_PORT
            },
            'session': {
                'session_timeout_minutes': Config.SESSION_TIMEOUT_MINUTES,
                'max_concurrent_sessions': Config.MAX_CONCURRENT_SESSIONS
            },
            'vtxo': {
                'vtxo_expiration_hours': Config.VTXO_EXPIRATION_HOURS,
                'vtxo_min_amount_sats': Config.VTXO_MIN_AMOUNT_SATS
            },
            'fees': {
                'fee_sats_per_vbyte': Config.FEE_SATS_PER_VBYTE,
                'fee_percentage': Config.FEE_PERCENTAGE
            },
            'grpc': {
                'grpc_max_message_length': Config.GRPC_MAX_MESSAGE_LENGTH,
                'grpc_timeout_seconds': Config.GRPC_TIMEOUT_SECONDS
            }
        }

        return jsonify({
            'configuration': config_data,
            'timestamp': utc_now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/logs/recent')
@require_admin_auth
def get_recent_logs():
    """Get recent application logs"""
    try:
        limit = request.args.get('limit', 100, type=int)
        level = request.args.get('level')

        session = get_session()

        # Get recent job logs as proxy for application logs
        query = session.query(JobLog).order_by(desc(JobLog.created_at))

        if level:
            query = query.filter(JobLog.status == level)

        logs = query.limit(limit).all()

        logs_data = []
        for log in logs:
            logs_data.append({
                'id': log.id,
                'job_type': log.job_type,
                'job_id': log.job_id,
                'status': log.status,
                'message': log.message,
                'duration_seconds': log.duration_seconds,
                'created_at': log.created_at.isoformat(),
                'updated_at': log.updated_at.isoformat() if log.updated_at else None
            })

        session.close()

        return jsonify({
            'logs': logs_data,
            'limit': limit,
            'level_filter': level,
            'count': len(logs_data),
            'timestamp': utc_now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/maintenance/cleanup', methods=['POST'])
@require_admin_auth
def cleanup_old_data():
    """Clean up old data"""
    try:
        data = request.get_json() or {}
        days = data.get('days', 30)
        dry_run = data.get('dry_run', False)

        session = get_session()
        cutoff_date = utc_now() - timedelta(days=days)

        cleanup_stats = {}

        try:
            # Count records to be cleaned up
            old_metrics = session.query(SystemMetrics).filter(
                SystemMetrics.timestamp < cutoff_date
            ).count()

            old_heartbeats = session.query(Heartbeat).filter(
                Heartbeat.timestamp < cutoff_date
            ).count()

            old_jobs = session.query(JobLog).filter(
                JobLog.created_at < cutoff_date,
                JobLog.status.in_(['completed', 'failed'])
            ).count()

            cleanup_stats = {
                'old_metrics': old_metrics,
                'old_heartbeats': old_heartbeats,
                'old_jobs': old_jobs,
                'total': old_metrics + old_heartbeats + old_jobs,
                'cutoff_date': cutoff_date.isoformat()
            }

            if not dry_run:
                # Perform cleanup
                if old_metrics > 0:
                    session.query(SystemMetrics).filter(
                        SystemMetrics.timestamp < cutoff_date
                    ).delete()

                if old_heartbeats > 0:
                    session.query(Heartbeat).filter(
                        Heartbeat.timestamp < cutoff_date
                    ).delete()

                if old_jobs > 0:
                    session.query(JobLog).filter(
                        JobLog.created_at < cutoff_date,
                        JobLog.status.in_(['completed', 'failed'])
                    ).delete()

                session.commit()

            session.close()

            return jsonify({
                'message': f'Cleanup {"simulated" if dry_run else "completed"}',
                'cleanup_stats': cleanup_stats,
                'dry_run': dry_run,
                'timestamp': utc_now().isoformat()
            })

        except Exception as e:
            session.rollback()
            session.close()
            raise e

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/backup/create', methods=['POST'])
@require_admin_auth
def create_backup():
    """Create a database backup"""
    try:
        data = request.get_json() or {}
        backup_type = data.get('type', 'full')  # 'full' or 'schema'

        # This is a simplified backup implementation
        # In production, you'd use proper database backup tools

        backup_id = f"backup_{utc_now().strftime('%Y%m%d_%H%M%S')}"
        backup_filename = f"/tmp/{backup_id}.sql"

        try:
            # For MySQL/MariaDB
            if 'mysql' in Config.DATABASE_URL.lower():
                # Parse database URL
                import urllib.parse as urlparse
                parsed = urlparse.urlparse(Config.DATABASE_URL)
                db_name = parsed.path.lstrip('/')

                cmd = [
                    'mysqldump',
                    '--user=' + parsed.username,
                    '--password=' + parsed.password,
                    '--host=' + parsed.hostname,
                    '--port=' + str(parsed.port or 3306),
                    '--single-transaction',
                    '--routines',
                    '--triggers' if backup_type == 'full' else '--no-data',
                    db_name
                ]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

                if result.returncode != 0:
                    return jsonify({'error': f'Backup failed: {result.stderr}'}), 500

                # Write backup to file
                with open(backup_filename, 'w') as f:
                    f.write(result.stdout)

                backup_size = len(result.stdout)

            else:
                return jsonify({'error': 'Unsupported database type for backup'}), 400

            return jsonify({
                'message': 'Backup created successfully',
                'backup_id': backup_id,
                'backup_type': backup_type,
                'filename': backup_filename,
                'size_bytes': backup_size,
                'timestamp': utc_now().isoformat()
            })

        except subprocess.TimeoutExpired:
            return jsonify({'error': 'Backup timed out'}), 500
        except FileNotFoundError:
            return jsonify({'error': 'Backup tool not found'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/performance/profile', methods=['POST'])
@require_admin_auth
def performance_profile():
    """Run performance profiling"""
    try:
        data = request.get_json() or {}
        duration = data.get('duration', 60)  # seconds

        # Start monitoring thread
        monitoring_results = {
            'cpu_samples': [],
            'memory_samples': [],
            'disk_samples': [],
            'network_samples': []
        }

        def monitor_performance():
            start_time = time.time()
            while time.time() - start_time < duration:
                try:
                    monitoring_results['cpu_samples'].append(psutil.cpu_percent())
                    monitoring_results['memory_samples'].append(psutil.virtual_memory().percent)
                    monitoring_results['disk_samples'].append(psutil.disk_usage('/').percent)

                    net_io = psutil.net_io_counters()
                    monitoring_results['network_samples'].append({
                        'bytes_sent': net_io.bytes_sent,
                        'bytes_recv': net_io.bytes_recv
                    })

                    time.sleep(1)
                except Exception:
                    break

        # Run monitoring in background
        monitor_thread = threading.Thread(target=monitor_performance)
        monitor_thread.daemon = True
        monitor_thread.start()
        monitor_thread.join(timeout=duration + 10)

        # Calculate statistics
        def calculate_stats(samples):
            if not samples:
                return {}
            return {
                'min': min(samples),
                'max': max(samples),
                'avg': sum(samples) / len(samples),
                'count': len(samples)
            }

        network_stats = {}
        if monitoring_results['network_samples']:
            sent_samples = [s['bytes_sent'] for s in monitoring_results['network_samples']]
            recv_samples = [s['bytes_recv'] for s in monitoring_results['network_samples']]
            network_stats = {
                'bytes_sent': calculate_stats(sent_samples),
                'bytes_recv': calculate_stats(recv_samples)
            }

        return jsonify({
            'duration_seconds': duration,
            'cpu_stats': calculate_stats(monitoring_results['cpu_samples']),
            'memory_stats': calculate_stats(monitoring_results['memory_samples']),
            'disk_stats': calculate_stats(monitoring_results['disk_samples']),
            'network_stats': network_stats,
            'timestamp': utc_now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/restart/service', methods=['POST'])
@require_admin_auth
def restart_service():
    """Restart a specific service (for development/testing)"""
    try:
        data = request.get_json() or {}
        service = data.get('service')

        if service not in ['nostr', 'lightning', 'vtxo']:
            return jsonify({'error': f'Unknown service: {service}'}), 400

        # This would typically use systemd or process management
        # For now, just return success for demonstration
        return jsonify({
            'message': f'Service {service} restart requested',
            'service': service,
            'timestamp': utc_now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/dashboard/summary')
@require_admin_auth
def get_dashboard_summary():
    """Get comprehensive dashboard summary"""
    try:
        monitoring_system = get_monitoring_system()
        session = get_session()

        # System health
        health_status = monitoring_system.health_checker.comprehensive_health_check()

        # Recent activity
        recent_jobs = session.query(JobLog).order_by(desc(JobLog.created_at)).limit(10).all()
        recent_sessions = session.query(SigningSession).order_by(desc(SigningSession.created_at)).limit(10).all()

        # Quick stats
        total_jobs = session.query(JobLog).count()
        active_sessions = session.query(SigningSession).filter(
            SigningSession.status.in_(['initiated', 'challenge_sent', 'awaiting_signature', 'signing'])
        ).count()

        # Alerts
        active_alerts = monitoring_system.alerting_system.get_active_alerts()

        session.close()

        return jsonify({
            'health_status': health_status,
            'recent_activity': {
                'jobs': [
                    {
                        'id': job.id,
                        'job_type': job.job_type,
                        'status': job.status,
                        'created_at': job.created_at.isoformat()
                    }
                    for job in recent_jobs
                ],
                'sessions': [
                    {
                        'session_id': sess.session_id[:8] + '...',
                        'session_type': sess.session_type,
                        'status': sess.status,
                        'created_at': sess.created_at.isoformat()
                    }
                    for sess in recent_sessions
                ]
            },
            'quick_stats': {
                'total_jobs': total_jobs,
                'active_sessions': active_sessions,
                'active_alerts': len(active_alerts)
            },
            'timestamp': utc_now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500