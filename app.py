from flask import Flask, jsonify, request
from redis import Redis
from rq import Queue
from rq_scheduler import Scheduler
from datetime import datetime, timedelta
import os
import json
from models import JobLog, SystemMetrics, Heartbeat, get_session
from grpc_clients import get_grpc_manager, ServiceType

app = Flask(__name__)

# Use REDIS_URL environment variable or fallback to default
redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
redis_conn = Redis.from_url(redis_url)
q = Queue(connection=redis_conn, default_result_ttl=3600)  # 1 hour default for jobs without explicit TTL
scheduler = Scheduler(connection=redis_conn, queue_name='default')

@app.route('/')
def index():
    return jsonify({
        'message': 'Welcome to ArkRelay Gateway',
        'timestamp': datetime.now().isoformat(),
        'status': 'running',
        'services': ['web', 'worker', 'scheduler'],
        'database': 'MariaDB',
        'queue': 'Redis'
    })

@app.route('/health')
def health():
    session = get_session()
    try:
        # Test database connection
        session.execute("SELECT 1")
        db_connected = True
    except:
        db_connected = False
    finally:
        session.close()

    # Check gRPC services
    grpc_manager = get_grpc_manager()
    grpc_health = grpc_manager.health_check_all()

    return jsonify({
        'status': 'healthy',
        'redis_connected': redis_conn.ping(),
        'database_connected': db_connected,
        'grpc_services': {
            'arkd': grpc_health.get(ServiceType.ARKD, False),
            'tapd': grpc_health.get(ServiceType.TAPD, False),
            'lnd': grpc_health.get(ServiceType.LND, False)
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/queue-status')
def queue_status():
    return jsonify({
        'queued_jobs': q.count,
        'scheduled_jobs': len(scheduler.get_jobs()),
        'worker_count': len(redis_conn.smembers('rq:workers')),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/enqueue-demo')
def enqueue_demo():
    job = q.enqueue('tasks.sample_task', args=['Demo job from web'], job_timeout=60, result_ttl=3600)
    return jsonify({
        'message': 'Job enqueued',
        'job_id': job.id,
        'job_status': job.get_status(),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/enqueue-user-process', methods=['POST'])
def enqueue_user_process():
    data = request.get_json() or {}
    user_id = data.get('user_id', 'unknown')
    action_type = data.get('action_type', 'process')
    user_data = data.get('data', {})

    job = q.enqueue(
        'tasks.process_user_data',
        args=[user_id, action_type, user_data],
        job_timeout=120,
        job_id=f"user_{user_id}_{action_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        result_ttl=7200  # Store user job results for 2 hours
    )

    return jsonify({
        'message': 'User processing job enqueued',
        'job_id': job.id,
        'user_id': user_id,
        'action_type': action_type,
        'job_status': job.get_status(),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/jobs')
def get_jobs():
    session = get_session()
    try:
        # Get recent jobs
        recent_jobs = session.query(JobLog).order_by(JobLog.created_at.desc()).limit(10).all()

        jobs_data = []
        for job in recent_jobs:
            jobs_data.append({
                'id': job.id,
                'job_id': job.job_id,
                'job_type': job.job_type,
                'status': job.status,
                'message': job.message,
                'duration_seconds': job.duration_seconds,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'updated_at': job.updated_at.isoformat() if job.updated_at else None
            })

        return jsonify({
            'jobs': jobs_data,
            'total_count': session.query(JobLog).count(),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/jobs/<job_id>')
def get_job(job_id):
    session = get_session()
    try:
        job = session.query(JobLog).filter_by(job_id=job_id).first()
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        return jsonify({
            'id': job.id,
            'job_id': job.job_id,
            'job_type': job.job_type,
            'status': job.status,
            'message': job.message,
            'result_data': json.loads(job.result_data) if job.result_data else None,
            'duration_seconds': job.duration_seconds,
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'updated_at': job.updated_at.isoformat() if job.updated_at else None
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/metrics')
def get_system_metrics():
    session = get_session()
    try:
        # Get recent system metrics
        recent_metrics = session.query(SystemMetrics).order_by(SystemMetrics.timestamp.desc()).limit(24).all()

        metrics_data = []
        for metric in recent_metrics:
            metrics_data.append({
                'id': metric.id,
                'cpu_percent': metric.cpu_percent,
                'memory_percent': metric.memory_percent,
                'memory_available_mb': metric.memory_available_mb,
                'disk_percent': metric.disk_percent,
                'disk_free_gb': metric.disk_free_gb,
                'timestamp': metric.timestamp.isoformat() if metric.timestamp else None
            })

        return jsonify({
            'metrics': metrics_data,
            'total_count': session.query(SystemMetrics).count(),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/heartbeats')
def get_heartbeats():
    session = get_session()
    try:
        # Get recent heartbeats
        recent_heartbeats = session.query(Heartbeat).order_by(Heartbeat.timestamp.desc()).limit(10).all()

        heartbeats_data = []
        for heartbeat in recent_heartbeats:
            heartbeats_data.append({
                'id': heartbeat.id,
                'service_name': heartbeat.service_name,
                'is_alive': heartbeat.is_alive,
                'message': heartbeat.message,
                'timestamp': heartbeat.timestamp.isoformat() if heartbeat.timestamp else None
            })

        return jsonify({
            'heartbeats': heartbeats_data,
            'total_count': session.query(Heartbeat).count(),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/grpc/arkd/info')
def get_arkd_info():
    """Get ARKD service information"""
    try:
        grpc_manager = get_grpc_manager()
        arkd_client = grpc_manager.get_client(ServiceType.ARKD)

        if not arkd_client:
            return jsonify({'error': 'ARKD client not available'}), 503

        network_info = arkd_client.get_network_info()
        return jsonify({
            'service': 'arkd',
            'connected': True,
            'network_info': network_info,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/grpc/tapd/balances')
def get_tapd_balances():
    """Get TAPD asset balances"""
    try:
        grpc_manager = get_grpc_manager()
        tapd_client = grpc_manager.get_client(ServiceType.TAPD)

        if not tapd_client:
            return jsonify({'error': 'TAPD client not available'}), 503

        balances = tapd_client.get_asset_balances()
        return jsonify({
            'service': 'tapd',
            'connected': True,
            'balances': balances,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/grpc/lnd/balances')
def get_lnd_balances():
    """Get LND balances"""
    try:
        grpc_manager = get_grpc_manager()
        lnd_client = grpc_manager.get_client(ServiceType.LND)

        if not lnd_client:
            return jsonify({'error': 'LND client not available'}), 503

        balances = lnd_client.get_total_balance()
        return jsonify({
            'service': 'lnd',
            'connected': True,
            'balances': balances,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/grpc/reconnect/<service>')
def reconnect_grpc_service(service):
    """Reconnect to a specific gRPC service"""
    try:
        grpc_manager = get_grpc_manager()

        if service == 'arkd':
            grpc_manager.reconnect(ServiceType.ARKD)
        elif service == 'tapd':
            grpc_manager.reconnect(ServiceType.TAPD)
        elif service == 'lnd':
            grpc_manager.reconnect(ServiceType.LND)
        else:
            return jsonify({'error': 'Invalid service name'}), 400

        return jsonify({
            'message': f'Reconnected to {service}',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stats')
def get_stats():
    session = get_session()
    try:
        # Get database statistics
        total_jobs = session.query(JobLog).count()
        completed_jobs = session.query(JobLog).filter_by(status='completed').count()
        failed_jobs = session.query(JobLog).filter_by(status='failed').count()
        running_jobs = session.query(JobLog).filter_by(status='running').count()

        # Get average duration for completed jobs
        avg_duration = session.query(JobLog.duration_seconds).filter(
            JobLog.status == 'completed',
            JobLog.duration_seconds.isnot(None)
        ).all()
        avg_duration = sum(d[0] for d in avg_duration if d[0]) / len(avg_duration) if avg_duration else 0

        # Get latest metrics
        latest_metrics = session.query(SystemMetrics).order_by(SystemMetrics.timestamp.desc()).first()

        # Get gRPC service health
        grpc_manager = get_grpc_manager()
        grpc_health = grpc_manager.health_check_all()

        return jsonify({
            'jobs': {
                'total': total_jobs,
                'completed': completed_jobs,
                'failed': failed_jobs,
                'running': running_jobs,
                'success_rate': round((completed_jobs / total_jobs * 100) if total_jobs > 0 else 0, 2),
                'average_duration_seconds': round(avg_duration, 2)
            },
            'latest_metrics': {
                'cpu_percent': latest_metrics.cpu_percent if latest_metrics else None,
                'memory_percent': latest_metrics.memory_percent if latest_metrics else None,
                'memory_available_mb': latest_metrics.memory_available_mb if latest_metrics else None,
                'disk_percent': latest_metrics.disk_percent if latest_metrics else None,
                'disk_free_gb': latest_metrics.disk_free_gb if latest_metrics else None,
                'timestamp': latest_metrics.timestamp.isoformat() if latest_metrics and latest_metrics.timestamp else None
            },
            'queue_status': {
                'queued_jobs': q.count,
                'scheduled_jobs': len(scheduler.get_jobs()),
                'worker_count': len(redis_conn.smembers('rq:workers'))
            },
            'grpc_services': {
                'arkd': grpc_health.get(ServiceType.ARKD, False),
                'tapd': grpc_health.get(ServiceType.TAPD, False),
                'lnd': grpc_health.get(ServiceType.LND, False)
            },
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)