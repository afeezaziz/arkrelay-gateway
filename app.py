from flask import Flask, jsonify, request
from redis import Redis
from rq import Queue
from rq_scheduler import Scheduler
from datetime import datetime, timedelta
import os
import json
from models import JobLog, SystemMetrics, Heartbeat, get_session
from grpc_clients import get_grpc_manager, ServiceType
from nostr_clients.nostr_client import get_nostr_client, initialize_nostr_client, shutdown_nostr_client
from nostr_clients.nostr_handlers import get_event_handler, initialize_event_handler
from nostr_clients.nostr_redis import get_redis_manager, initialize_redis_manager, shutdown_redis_manager
from nostr_clients.nostr_workers import get_action_intent_worker, get_signing_response_worker

app = Flask(__name__)

# Use REDIS_URL environment variable or fallback to default
redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
redis_conn = Redis.from_url(redis_url)
q = Queue(connection=redis_conn, default_result_ttl=3600)  # 1 hour default for jobs without explicit TTL
scheduler = Scheduler(connection=redis_conn, queue_name='default')

# Initialize Nostr components
nostr_client = None
redis_manager = None
event_handler = None

@app.route('/')
def index():
    return jsonify({
        'message': 'Welcome to ArkRelay Gateway',
        'timestamp': datetime.now().isoformat(),
        'status': 'running',
        'services': ['web', 'worker', 'scheduler', 'nostr'],
        'database': 'MariaDB',
        'queue': 'Redis',
        'version': '1.0.0'
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

    # Check Nostr service
    nostr_stats = {}
    if nostr_client:
        nostr_stats = nostr_client.get_stats()

    return jsonify({
        'status': 'healthy',
        'redis_connected': redis_conn.ping(),
        'database_connected': db_connected,
        'grpc_services': {
            'arkd': grpc_health.get(ServiceType.ARKD, False),
            'tapd': grpc_health.get(ServiceType.TAPD, False),
            'lnd': grpc_health.get(ServiceType.LND, False)
        },
        'nostr_service': {
            'connected': nostr_stats.get('running', False),
            'connected_relays': nostr_stats.get('connected_relays', 0),
            'events_received': nostr_stats.get('events_received', 0),
            'events_published': nostr_stats.get('events_published', 0)
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

# Nostr Integration Endpoints

@app.route('/nostr/start', methods=['POST'])
def start_nostr_service():
    """Start the Nostr service"""
    global nostr_client, redis_manager, event_handler

    try:
        if nostr_client and nostr_client._running:
            return jsonify({'message': 'Nostr service already running'})

        # Initialize Nostr components
        nostr_client = initialize_nostr_client()
        redis_manager = initialize_redis_manager()
        event_handler = initialize_event_handler()

        # Set up Redis pub/sub handlers
        action_worker = get_action_intent_worker()
        signing_worker = get_signing_response_worker()

        redis_manager.subscribe_to_channel('action_intent', action_worker.process_action_intent)
        redis_manager.subscribe_to_channel('signing_response', signing_worker.process_signing_response)

        return jsonify({
            'message': 'Nostr service started successfully',
            'gateway_pubkey': nostr_client.public_key.to_hex(),
            'connected_relays': len(nostr_client.relays),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/nostr/stop', methods=['POST'])
def stop_nostr_service():
    """Stop the Nostr service"""
    global nostr_client, redis_manager, event_handler

    try:
        if not nostr_client:
            return jsonify({'message': 'Nostr service not running'})

        # Shutdown components
        shutdown_redis_manager()
        shutdown_nostr_client()

        # Clear references
        nostr_client = None
        redis_manager = None
        event_handler = None

        return jsonify({
            'message': 'Nostr service stopped successfully',
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/nostr/status')
def nostr_status():
    """Get Nostr service status"""
    global nostr_client, redis_manager

    try:
        if not nostr_client:
            return jsonify({
                'running': False,
                'message': 'Nostr service not started'
            })

        nostr_stats = nostr_client.get_stats()
        redis_stats = redis_manager.get_stats() if redis_manager else {}

        return jsonify({
            'running': True,
            'gateway_pubkey': nostr_client.public_key.to_hex(),
            'nostr_stats': nostr_stats,
            'redis_stats': redis_stats,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/nostr/send-dm', methods=['POST'])
def send_nostr_dm():
    """Send an encrypted direct message"""
    if not nostr_client:
        return jsonify({'error': 'Nostr service not running'}), 400

    try:
        data = request.get_json()
        recipient_pubkey = data.get('recipient_pubkey')
        message = data.get('message')

        if not recipient_pubkey or not message:
            return jsonify({'error': 'recipient_pubkey and message are required'}), 400

        event_id = nostr_client.send_encrypted_dm(recipient_pubkey, message)

        if event_id:
            return jsonify({
                'message': 'Direct message sent successfully',
                'event_id': event_id,
                'recipient': recipient_pubkey,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': 'Failed to send direct message'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/nostr/publish-test', methods=['POST'])
def publish_test_event():
    """Publish a test event"""
    if not nostr_client:
        return jsonify({'error': 'Nostr service not running'}), 400

    try:
        data = request.get_json() or {}
        message = data.get('message', 'Test message from ArkRelay Gateway')
        kind = data.get('kind', 1)

        event_id = nostr_client.publish_event(
            kind=kind,
            content=message,
            tags=[['t', 'arkrelay-test']]
        )

        if event_id:
            return jsonify({
                'message': 'Test event published successfully',
                'event_id': event_id,
                'kind': kind,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': 'Failed to publish test event'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/nostr/relays')
def get_nostr_relays():
    """Get configured Nostr relays"""
    if not nostr_client:
        return jsonify({'error': 'Nostr service not running'}), 400

    try:
        relay_status = []
        for relay_url in nostr_client.relays:
            relay_obj = nostr_client.relay_manager.relays.get(relay_url)
            relay_status.append({
                'url': relay_url,
                'connected': relay_obj.is_connected if relay_obj else False
            })

        return jsonify({
            'relays': relay_status,
            'total_relays': len(relay_status),
            'connected_relays': sum(1 for r in relay_status if r['connected']),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/nostr/test-encryption', methods=['POST'])
def test_encryption():
    """Test encryption/decryption functionality"""
    if not nostr_client:
        return jsonify({'error': 'Nostr service not running'}), 400

    try:
        data = request.get_json()
        recipient_pubkey = data.get('recipient_pubkey', nostr_client.public_key.to_hex())
        message = data.get('message', 'This is a test encrypted message')

        # Test encryption
        start_time = datetime.now()
        encrypted = nostr_client.encrypt_dm(recipient_pubkey, message)
        encryption_time = (datetime.now() - start_time).total_seconds()

        if not encrypted:
            return jsonify({'error': 'Encryption failed'}), 500

        # Test decryption
        start_time = datetime.now()
        decrypted = nostr_client.decrypt_dm(recipient_pubkey, encrypted)
        decryption_time = (datetime.now() - start_time).total_seconds()

        success = decrypted == message

        return jsonify({
            'success': success,
            'original_message': message,
            'encrypted_length': len(encrypted),
            'encryption_time_ms': round(encryption_time * 1000, 2),
            'decryption_time_ms': round(decryption_time * 1000, 2),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/nostr/sessions')
def get_nostr_sessions():
    """Get active Nostr signing sessions"""
    session = get_session()
    try:
        # Get active sessions
        active_sessions = session.query(SigningSession).filter(
            SigningSession.status.in_(['initiated', 'challenge_sent', 'awaiting_signature', 'signing'])
        ).order_by(SigningSession.created_at.desc()).all()

        sessions_data = []
        for sess in active_sessions:
            sessions_data.append({
                'session_id': sess.session_id,
                'user_pubkey': sess.user_pubkey[:8] + '...',  # Truncate for privacy
                'session_type': sess.session_type,
                'status': sess.status,
                'context': sess.context,
                'created_at': sess.created_at.isoformat() if sess.created_at else None,
                'expires_at': sess.expires_at.isoformat() if sess.expires_at else None
            })

        return jsonify({
            'sessions': sessions_data,
            'total_count': len(sessions_data),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

def initialize_services():
    """Initialize all services when the app starts"""
    global nostr_client, redis_manager, event_handler

    # Auto-start Nostr service if configured
    if os.getenv('NOSTR_AUTO_START', 'false').lower() == 'true':
        try:
            nostr_client = initialize_nostr_client()
            redis_manager = initialize_redis_manager()
            event_handler = initialize_event_handler()

            # Set up Redis pub/sub handlers
            action_worker = get_action_intent_worker()
            signing_worker = get_signing_response_worker()

            redis_manager.subscribe_to_channel('action_intent', action_worker.process_action_intent)
            redis_manager.subscribe_to_channel('signing_response', signing_worker.process_signing_response)

            print("✅ Nostr service auto-started")
        except Exception as e:
            print(f"❌ Failed to auto-start Nostr service: {e}")

if __name__ == '__main__':
    # Initialize services on startup
    initialize_services()
    app.run(debug=True, host='0.0.0.0', port=8000)