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
from session_manager import get_session_manager
from challenge_manager import get_challenge_manager
from transaction_processor import get_transaction_processor
from signing_orchestrator import get_signing_orchestrator
from asset_manager import get_asset_manager
from lightning_manager import LightningManager, LightningLiftRequest, LightningLandRequest
from lightning_monitor import LightningMonitor
from grpc_clients.lnd_client import LndClient
from grpc_clients import get_grpc_manager, ServiceType
from vtxo_manager import get_vtxo_manager, get_settlement_manager, initialize_vtxo_services, shutdown_vtxo_services

# Import Phase 8 monitoring and operations components
from monitoring import get_monitoring_system, initialize_monitoring, shutdown_monitoring
from admin_api import admin_bp
from cache_manager import initialize_performance_systems, shutdown_performance_systems, get_cache_manager

app = Flask(__name__)

# Register admin blueprint
app.register_blueprint(admin_bp)

# Initialize Lightning services
lightning_manager = None
lightning_monitor = None

# Initialize VTXO services
vtxo_manager = None
settlement_manager = None

# Initialize monitoring and performance systems
monitoring_system = None
cache_manager = None

def initialize_lightning_services():
    """Initialize Lightning services"""
    global lightning_manager, lightning_monitor

    try:
        # Get LND client from gRPC manager
        grpc_manager = get_grpc_manager()
        lnd_client = grpc_manager.get_client(ServiceType.LND)

        if lnd_client:
            lightning_manager = LightningManager(lnd_client)
            lightning_monitor = LightningMonitor(lightning_manager)

            # Start monitoring
            lightning_monitor.start_monitoring()

            print("✅ Lightning services initialized")
            return True
        else:
            print("❌ LND client not available")
            return False
    except Exception as e:
        print(f"❌ Failed to initialize Lightning services: {e}")
        return False

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
    """Basic health check endpoint"""
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

@app.route('/health/comprehensive')
def comprehensive_health():
    """Comprehensive health check using monitoring system"""
    try:
        if monitoring_system:
            health_status = monitoring_system.health_checker.comprehensive_health_check()
            return jsonify(health_status)
        else:
            return jsonify({'error': 'Monitoring system not initialized'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
    """Get basic system metrics from database"""
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

@app.route('/monitoring/stats')
def get_monitoring_stats():
    """Get comprehensive monitoring statistics"""
    try:
        if not monitoring_system:
            return jsonify({'error': 'Monitoring system not initialized'}), 503

        stats = monitoring_system.get_performance_stats()
        return jsonify({
            'monitoring_stats': stats,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/monitoring/alerts')
def get_monitoring_alerts():
    """Get active monitoring alerts"""
    try:
        if not monitoring_system:
            return jsonify({'error': 'Monitoring system not initialized'}), 503

        alerts = monitoring_system.alerting_system.get_active_alerts()
        return jsonify({
            'alerts': alerts,
            'active_count': len(alerts),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/monitoring/cache/stats')
def get_cache_stats():
    """Get cache performance statistics"""
    try:
        if not cache_manager:
            return jsonify({'error': 'Cache manager not initialized'}), 503

        stats = cache_manager.get_stats()
        return jsonify({
            'cache_stats': stats,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

# Session Management Endpoints

@app.route('/sessions/create', methods=['POST'])
def create_session():
    """Create a new signing session"""
    try:
        data = request.get_json()
        user_pubkey = data.get('user_pubkey')
        session_type = data.get('session_type')
        intent_data = data.get('intent_data', {})

        if not user_pubkey or not session_type:
            return jsonify({'error': 'user_pubkey and session_type are required'}), 400

        # Validate session type
        valid_types = ['p2p_transfer', 'lightning_lift', 'lightning_land']
        if session_type not in valid_types:
            return jsonify({'error': f'Invalid session_type. Must be one of: {valid_types}'}), 400

        session_manager = get_session_manager()
        session = session_manager.create_session(user_pubkey, session_type, intent_data)

        return jsonify({
            'message': 'Session created successfully',
            'session_id': session.session_id,
            'user_pubkey': session.user_pubkey,
            'session_type': session.session_type,
            'status': session.status,
            'expires_at': session.expires_at.isoformat(),
            'created_at': session.created_at.isoformat(),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sessions/<session_id>')
def get_session_info(session_id):
    """Get session information"""
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session(session_id)

        if not session:
            return jsonify({'error': 'Session not found'}), 404

        response = {
            'session_id': session.session_id,
            'user_pubkey': session.user_pubkey,
            'session_type': session.session_type,
            'status': session.status,
            'intent_data': session.intent_data,
            'context': session.context,
            'expires_at': session.expires_at.isoformat(),
            'created_at': session.created_at.isoformat(),
            'updated_at': session.updated_at.isoformat(),
            'timestamp': datetime.now().isoformat()
        }

        if session.result_data:
            response['result_data'] = session.result_data

        if session.signed_tx:
            response['signed_tx'] = session.signed_tx

        if session.error_message:
            response['error_message'] = session.error_message

        return jsonify(response)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sessions/<session_id>/challenge', methods=['POST'])
def create_challenge():
    """Create a signing challenge for a session"""
    try:
        session_manager = get_session_manager()
        challenge_manager = get_challenge_manager()

        session = session_manager.get_session(session_id)
        if not session:
            return jsonify({'error': 'Session not found'}), 404

        if session.status != 'initiated':
            return jsonify({'error': f'Session is in {session.status} state, cannot create challenge'}), 400

        # Create challenge with context data
        context_data = {
            'session_id': session_id,
            'session_type': session.session_type,
            'intent_data': session.intent_data
        }

        challenge = challenge_manager.create_and_store_challenge(session_id, context_data)

        if not challenge:
            return jsonify({'error': 'Failed to create challenge'}), 500

        return jsonify({
            'message': 'Challenge created successfully',
            'challenge_id': challenge.challenge_id,
            'session_id': session.session_id,
            'context': challenge.context,
            'expires_at': challenge.expires_at.isoformat(),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sessions/<session_id>/respond', methods=['POST'])
def respond_to_challenge():
    """Respond to a challenge with signature"""
    try:
        data = request.get_json()
        signature_hex = data.get('signature')
        user_pubkey = data.get('user_pubkey')

        if not signature_hex or not user_pubkey:
            return jsonify({'error': 'signature and user_pubkey are required'}), 400

        # Convert hex signature to bytes
        try:
            signature = bytes.fromhex(signature_hex)
        except ValueError:
            return jsonify({'error': 'Invalid signature format, must be hex string'}), 400

        session_manager = get_session_manager()
        challenge_manager = get_challenge_manager()

        # Validate challenge response
        if not challenge_manager.validate_challenge_response(session_id, signature, user_pubkey):
            return jsonify({'error': 'Invalid challenge response'}), 400

        # Update session status
        if not session_manager.update_session_status(session_id, 'awaiting_signature', 'Challenge response validated'):
            return jsonify({'error': 'Failed to update session status'}), 500

        return jsonify({
            'message': 'Challenge response validated successfully',
            'session_id': session_id,
            'status': 'awaiting_signature',
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sessions/<session_id>/complete', methods=['POST'])
def complete_session():
    """Complete a session with result data"""
    try:
        data = request.get_json()
        result_data = data.get('result_data', {})
        signed_tx = data.get('signed_tx')

        session_manager = get_session_manager()

        if not session_manager.complete_session(session_id, result_data, signed_tx):
            return jsonify({'error': 'Failed to complete session'}), 500

        return jsonify({
            'message': 'Session completed successfully',
            'session_id': session_id,
            'result_data': result_data,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sessions/<session_id>/fail', methods=['POST'])
def fail_session():
    """Mark a session as failed"""
    try:
        data = request.get_json()
        error_message = data.get('error_message', 'Session failed')

        session_manager = get_session_manager()

        if not session_manager.fail_session(session_id, error_message):
            return jsonify({'error': 'Failed to fail session'}), 500

        return jsonify({
            'message': 'Session marked as failed',
            'session_id': session_id,
            'error_message': error_message,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sessions')
def get_sessions():
    """Get sessions, optionally filtered by user pubkey"""
    try:
        user_pubkey = request.args.get('user_pubkey')
        status_filter = request.args.get('status')

        session_manager = get_session_manager()

        if user_pubkey:
            sessions = session_manager.get_active_sessions(user_pubkey)
        else:
            # Get all sessions from database
            db_session = get_session()
            try:
                query = db_session.query(SigningSession)

                if status_filter:
                    query = query.filter(SigningSession.status == status_filter)

                sessions = query.order_by(SigningSession.created_at.desc()).limit(50).all()
            finally:
                db_session.close()

        sessions_data = []
        for sess in sessions:
            session_data = {
                'session_id': sess.session_id,
                'user_pubkey': sess.user_pubkey[:8] + '...',  # Truncate for privacy
                'session_type': sess.session_type,
                'status': sess.status,
                'context': sess.context,
                'created_at': sess.created_at.isoformat() if sess.created_at else None,
                'expires_at': sess.expires_at.isoformat() if sess.expires_at else None,
                'updated_at': sess.updated_at.isoformat() if sess.updated_at else None
            }

            if sess.result_data:
                session_data['has_result'] = True

            if sess.error_message:
                session_data['has_error'] = True

            sessions_data.append(session_data)

        return jsonify({
            'sessions': sessions_data,
            'total_count': len(sessions_data),
            'filters': {
                'user_pubkey': user_pubkey[:8] + '...' if user_pubkey else None,
                'status': status_filter
            },
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sessions/cleanup', methods=['POST'])
def cleanup_expired_sessions():
    """Clean up expired sessions and challenges"""
    try:
        session_manager = get_session_manager()
        challenge_manager = get_challenge_manager()

        # Clean up expired sessions
        expired_sessions = session_manager.cleanup_expired_sessions()

        # Clean up expired challenges
        expired_challenges = challenge_manager.cleanup_expired_challenges()

        return jsonify({
            'message': 'Cleanup completed',
            'expired_sessions_cleaned': expired_sessions,
            'expired_challenges_cleaned': expired_challenges,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/challenges/<challenge_id>')
def get_challenge_info(challenge_id):
    """Get challenge information"""
    try:
        challenge_manager = get_challenge_manager()
        challenge_info = challenge_manager.get_challenge_info(challenge_id)

        if not challenge_info:
            return jsonify({'error': 'Challenge not found'}), 404

        return jsonify({
            'challenge': challenge_info,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sessions/stats')
def get_session_stats():
    """Get session statistics"""
    try:
        db_session = get_session()
        try:
            # Get session counts by status
            from sqlalchemy import func
            status_counts = db_session.query(
                SigningSession.status,
                func.count(SigningSession.id)
            ).group_by(SigningSession.status).all()

            # Get session counts by type
            type_counts = db_session.query(
                SigningSession.session_type,
                func.count(SigningSession.id)
            ).group_by(SigningSession.session_type).all()

            # Get recent sessions
            recent_sessions = db_session.query(SigningSession).order_by(
                SigningSession.created_at.desc()
            ).limit(10).all()

            stats = {
                'status_counts': {status: count for status, count in status_counts},
                'type_counts': {session_type: count for session_type, count in type_counts},
                'total_sessions': sum(count for _, count in status_counts),
                'recent_sessions': [
                    {
                        'session_id': sess.session_id[:8] + '...',
                        'status': sess.status,
                        'session_type': sess.session_type,
                        'created_at': sess.created_at.isoformat()
                    }
                    for sess in recent_sessions
                ]
            }

            return jsonify({
                'stats': stats,
                'timestamp': datetime.now().isoformat()
            })

        finally:
            db_session.close()

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

# Phase 5: Core Business Logic Endpoints

@app.route('/transactions/p2p-transfer', methods=['POST'])
def process_p2p_transfer():
    """Process a P2P transfer transaction"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')

        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400

        transaction_processor = get_transaction_processor()
        result = transaction_processor.process_p2p_transfer(session_id)

        return jsonify({
            'message': 'P2P transfer processed successfully',
            'transaction': result,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/transactions/<txid>/status')
def get_transaction_status(txid):
    """Get the status of a transaction"""
    try:
        transaction_processor = get_transaction_processor()
        status = transaction_processor.get_transaction_status(txid)

        if 'error' in status:
            return jsonify(status), 404

        return jsonify(status)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/transactions/<txid>/broadcast', methods=['POST'])
def broadcast_transaction(txid):
    """Broadcast a transaction to the network"""
    try:
        transaction_processor = get_transaction_processor()
        result = transaction_processor.broadcast_transaction(txid)

        return jsonify({
            'success': result,
            'txid': txid,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/transactions/user/<user_pubkey>')
def get_user_transactions(user_pubkey):
    """Get transactions for a specific user"""
    try:
        limit = request.args.get('limit', 50, type=int)
        transaction_processor = get_transaction_processor()
        transactions = transaction_processor.get_user_transactions(user_pubkey, limit)

        return jsonify({
            'transactions': transactions,
            'user_pubkey': user_pubkey[:8] + '...',
            'total_count': len(transactions),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/signing/ceremony/start', methods=['POST'])
def start_signing_ceremony():
    """Start a signing ceremony for a session"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')

        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400

        orchestrator = get_signing_orchestrator()
        result = orchestrator.start_signing_ceremony(session_id)

        return jsonify({
            'message': 'Signing ceremony started',
            'ceremony': result,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/signing/ceremony/<session_id>/status')
def get_signing_ceremony_status(session_id):
    """Get the status of a signing ceremony"""
    try:
        orchestrator = get_signing_orchestrator()
        status = orchestrator.get_ceremony_status(session_id)

        return jsonify(status)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/signing/ceremony/<session_id>/step/<int:step>', methods=['POST'])
def execute_signing_step(session_id, step):
    """Execute a specific signing ceremony step"""
    try:
        data = request.get_json() or {}
        signature_data = data.get('signature_data')

        orchestrator = get_signing_orchestrator()
        from signing_orchestrator import SigningStep
        step_enum = SigningStep(step)

        result = orchestrator.execute_signing_step(session_id, step_enum, signature_data)

        return jsonify({
            'step': step,
            'result': result,
            'timestamp': datetime.now().isoformat()
        })

    except ValueError as e:
        return jsonify({'error': f'Invalid step: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/signing/ceremony/<session_id>/cancel', methods=['POST'])
def cancel_signing_ceremony(session_id):
    """Cancel a signing ceremony"""
    try:
        data = request.get_json() or {}
        reason = data.get('reason', 'User cancelled')

        orchestrator = get_signing_orchestrator()
        result = orchestrator.cancel_ceremony(session_id, reason)

        return jsonify({
            'success': result,
            'session_id': session_id,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/assets', methods=['POST'])
def create_asset():
    """Create a new asset"""
    try:
        data = request.get_json()
        required_fields = ['asset_id', 'name', 'ticker']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400

        asset_manager = get_asset_manager()
        result = asset_manager.create_asset(
            asset_id=data['asset_id'],
            name=data['name'],
            ticker=data['ticker'],
            asset_type=data.get('asset_type', 'normal'),
            decimal_places=data.get('decimal_places', 8),
            total_supply=data.get('total_supply', 0),
            metadata=data.get('metadata')
        )

        return jsonify({
            'message': 'Asset created successfully',
            'asset': result,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/assets/<asset_id>')
def get_asset_info(asset_id):
    """Get information about an asset"""
    try:
        asset_manager = get_asset_manager()
        info = asset_manager.get_asset_info(asset_id)

        if 'error' in info:
            return jsonify(info), 404

        return jsonify(info)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/assets')
def list_assets():
    """List all assets"""
    try:
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        asset_manager = get_asset_manager()
        assets = asset_manager.list_assets(active_only)

        return jsonify({
            'assets': assets,
            'total_count': len(assets),
            'active_only': active_only,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/assets/<asset_id>/mint', methods=['POST'])
def mint_assets():
    """Mint new assets to a user"""
    try:
        data = request.get_json()
        required_fields = ['user_pubkey', 'amount']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400

        asset_manager = get_asset_manager()
        result = asset_manager.mint_assets(
            user_pubkey=data['user_pubkey'],
            asset_id=asset_id,
            amount=data['amount'],
            reserve_amount=data.get('reserve_amount', 0)
        )

        return jsonify({
            'message': 'Assets minted successfully',
            'result': result,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/assets/transfer', methods=['POST'])
def transfer_assets():
    """Transfer assets between users"""
    try:
        data = request.get_json()
        required_fields = ['sender_pubkey', 'recipient_pubkey', 'asset_id', 'amount']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400

        asset_manager = get_asset_manager()
        result = asset_manager.transfer_assets(
            sender_pubkey=data['sender_pubkey'],
            recipient_pubkey=data['recipient_pubkey'],
            asset_id=data['asset_id'],
            amount=data['amount']
        )

        return jsonify({
            'message': 'Assets transferred successfully',
            'result': result,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/balances/<user_pubkey>')
def get_user_balances(user_pubkey):
    """Get all balances for a user"""
    try:
        asset_manager = get_asset_manager()
        balances = asset_manager.get_user_balances(user_pubkey)

        return jsonify({
            'balances': balances,
            'user_pubkey': user_pubkey[:8] + '...',
            'total_assets': len(balances),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/balances/<user_pubkey>/<asset_id>')
def get_user_balance(user_pubkey, asset_id):
    """Get user's balance for a specific asset"""
    try:
        asset_manager = get_asset_manager()
        balance = asset_manager.get_user_balance(user_pubkey, asset_id)

        return jsonify(balance)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vtxos/<user_pubkey>')
def manage_vtxos(user_pubkey):
    """Manage VTXOs for a user"""
    try:
        asset_id = request.args.get('asset_id')
        action = request.args.get('action', 'list')

        asset_manager = get_asset_manager()
        result = asset_manager.manage_vtxos(
            user_pubkey=user_pubkey,
            asset_id=asset_id,
            action=action
        )

        return jsonify({
            'vtxo_management': result,
            'user_pubkey': user_pubkey[:8] + '...',
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/assets/stats')
def get_asset_stats():
    """Get overall asset statistics"""
    try:
        asset_manager = get_asset_manager()
        stats = asset_manager.get_asset_stats()

        return jsonify({
            'stats': stats,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/assets/cleanup-vtxos', methods=['POST'])
def cleanup_expired_vtxos():
    """Clean up expired VTXOs"""
    try:
        asset_manager = get_asset_manager()
        result = asset_manager.cleanup_expired_vtxos()

        return jsonify({
            'message': 'VTXO cleanup completed',
            'result': result,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/assets/<asset_id>/reserve')
def get_reserve_requirements(asset_id):
    """Get reserve requirements for an asset"""
    try:
        asset_manager = get_asset_manager()
        reserve = asset_manager.get_reserve_requirements(asset_id)

        return jsonify({
            'reserve_requirements': reserve,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Lightning API Endpoints

@app.route('/lightning/lift', methods=['POST'])
def create_lightning_lift():
    """Create a Lightning lift (on-ramp) operation"""
    try:
        if not lightning_manager:
            return jsonify({'error': 'Lightning services not available'}), 503

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Validate required fields
        required_fields = ['user_pubkey', 'asset_id', 'amount_sats']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Create lift request
        lift_request = LightningLiftRequest(
            user_pubkey=data['user_pubkey'],
            asset_id=data['asset_id'],
            amount_sats=int(data['amount_sats']),
            memo=data.get('memo', '')
        )

        # Process the lift
        result = lightning_manager.create_lightning_lift(lift_request)

        if result.success:
            return jsonify({
                'success': True,
                'operation_id': result.operation_id,
                'payment_hash': result.payment_hash,
                'bolt11_invoice': result.bolt11_invoice,
                'details': result.details,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': result.error,
                'timestamp': datetime.now().isoformat()
            }), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/lightning/land', methods=['POST'])
def process_lightning_land():
    """Process a Lightning land (off-ramp) operation"""
    try:
        if not lightning_manager:
            return jsonify({'error': 'Lightning services not available'}), 503

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Validate required fields
        required_fields = ['user_pubkey', 'asset_id', 'amount_sats', 'lightning_invoice']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Create land request
        land_request = LightningLandRequest(
            user_pubkey=data['user_pubkey'],
            asset_id=data['asset_id'],
            amount_sats=int(data['amount_sats']),
            lightning_invoice=data['lightning_invoice']
        )

        # Process the land
        result = lightning_manager.process_lightning_land(land_request)

        if result.success:
            return jsonify({
                'success': True,
                'operation_id': result.operation_id,
                'payment_hash': result.payment_hash,
                'bolt11_invoice': result.bolt11_invoice,
                'details': result.details,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': result.error,
                'timestamp': datetime.now().isoformat()
            }), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/lightning/invoices/<payment_hash>')
def get_invoice_status(payment_hash):
    """Get the status of a Lightning invoice"""
    try:
        if not lightning_manager:
            return jsonify({'error': 'Lightning services not available'}), 503

        status = lightning_manager.check_invoice_status(payment_hash)

        if 'error' in status:
            return jsonify({'error': status['error']}), 404

        return jsonify({
            'invoice_status': status,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/lightning/pay/<payment_hash>', methods=['POST'])
def pay_lightning_invoice(payment_hash):
    """Pay a Lightning invoice (for land operations)"""
    try:
        if not lightning_manager:
            return jsonify({'error': 'Lightning services not available'}), 503

        result = lightning_manager.pay_lightning_invoice(payment_hash)

        if result.success:
            return jsonify({
                'success': True,
                'operation_id': result.operation_id,
                'payment_hash': result.payment_hash,
                'details': result.details,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': result.error,
                'timestamp': datetime.now().isoformat()
            }), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/lightning/balances')
def get_lightning_balances():
    """Get Lightning balance information"""
    try:
        if not lightning_manager:
            return jsonify({'error': 'Lightning services not available'}), 503

        balances = lightning_manager.get_lightning_balances()

        if 'error' in balances:
            return jsonify({'error': balances['error']}), 500

        return jsonify({
            'lightning_balances': balances,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/lightning/channels')
def list_lightning_channels():
    """List Lightning channels"""
    try:
        if not lightning_manager:
            return jsonify({'error': 'Lightning services not available'}), 503

        lnd_client = lightning_manager.lnd_client
        channels = lnd_client.list_channels()

        return jsonify({
            'channels': [
                {
                    'channel_id': channel.channel_id,
                    'remote_pubkey': channel.remote_pubkey,
                    'capacity': channel.capacity,
                    'local_balance': channel.local_balance,
                    'remote_balance': channel.remote_balance,
                    'private': channel.private,
                    'active': channel.active,
                    'funding_txid': channel.funding_txid
                }
                for channel in channels
            ],
            'count': len(channels),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/lightning/fees/estimate/<int:amount_sats>')
def estimate_lightning_fees(amount_sats):
    """Estimate Lightning fees for a given amount"""
    try:
        if not lightning_manager:
            return jsonify({'error': 'Lightning services not available'}), 503

        fees = lightning_manager.estimate_lightning_fees(amount_sats)

        if 'error' in fees:
            return jsonify({'error': fees['error']}), 500

        return jsonify({
            'fee_estimate': fees,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/lightning/activity/<user_pubkey>')
def get_user_lightning_activity(user_pubkey):
    """Get user's Lightning activity history"""
    try:
        if not lightning_manager:
            return jsonify({'error': 'Lightning services not available'}), 503

        limit = request.args.get('limit', 50, type=int)
        activity = lightning_manager.get_user_lightning_activity(user_pubkey, limit)

        return jsonify({
            'user_activity': activity,
            'user_pubkey': user_pubkey,
            'count': len(activity),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/lightning/statistics')
def get_lightning_statistics():
    """Get Lightning operation statistics"""
    try:
        if not lightning_monitor:
            return jsonify({'error': 'Lightning monitor not available'}), 503

        hours = request.args.get('hours', 24, type=int)
        stats = lightning_monitor.get_lightning_statistics(hours)

        if 'error' in stats:
            return jsonify({'error': stats['error']}), 500

        return jsonify({
            'lightning_statistics': stats,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/lightning/monitor/health')
def get_lightning_monitor_health():
    """Get Lightning monitor health status"""
    try:
        if not lightning_monitor:
            return jsonify({'error': 'Lightning monitor not available'}), 503

        health = lightning_monitor.health_check()

        return jsonify({
            'monitor_health': health,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/lightning/invoices')
def list_lightning_invoices():
    """List Lightning invoices with filtering"""
    try:
        if not lightning_manager:
            return jsonify({'error': 'Lightning services not available'}), 503

        lnd_client = lightning_manager.lnd_client
        pending_only = request.args.get('pending_only', 'false').lower() == 'true'
        invoices = lnd_client.list_invoices(pending_only)

        return jsonify({
            'invoices': [
                {
                    'payment_hash': invoice.payment_hash,
                    'payment_request': invoice.payment_request,
                    'value': invoice.value,
                    'settled': invoice.settled,
                    'creation_date': invoice.creation_date.isoformat(),
                    'expiry': invoice.expiry,
                    'memo': invoice.memo
                }
                for invoice in invoices
            ],
            'count': len(invoices),
            'pending_only': pending_only,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/lightning/payments')
def list_lightning_payments():
    """List Lightning payments"""
    try:
        if not lightning_manager:
            return jsonify({'error': 'Lightning services not available'}), 503

        lnd_client = lightning_manager.lnd_client
        payments = lnd_client.list_payments()

        return jsonify({
            'payments': [
                {
                    'payment_hash': payment.payment_hash,
                    'value': payment.value,
                    'fee': payment.fee,
                    'payment_preimage': payment.payment_preimage,
                    'payment_request': payment.payment_request,
                    'status': payment.status,
                    'creation_time': payment.creation_time.isoformat(),
                    'completion_time': payment.completion_time.isoformat() if payment.completion_time else None
                }
                for payment in payments
            ],
            'count': len(payments),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# VTXO Management Endpoints

@app.route('/vtxos/inventory/<asset_id>')
def get_vtxo_inventory(asset_id):
    """Get VTXO inventory status for an asset"""
    try:
        vtxo_manager = get_vtxo_manager()
        inventory_status = vtxo_manager.inventory_monitor.get_asset_inventory_status(get_session(), asset_id)

        return jsonify({
            'inventory_status': inventory_status,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session = get_session()
        session.close()

@app.route('/vtxos/batch/create', methods=['POST'])
def create_vtxo_batch():
    """Create a batch of new VTXOs"""
    try:
        data = request.get_json()
        required_fields = ['asset_id', 'count']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400

        vtxo_manager = get_vtxo_manager()
        success = vtxo_manager.create_vtxo_batch(
            asset_id=data['asset_id'],
            count=data['count'],
            amount_sats=data.get('amount_sats')
        )

        if success:
            return jsonify({
                'message': 'VTXO batch created successfully',
                'asset_id': data['asset_id'],
                'count': data['count'],
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': 'Failed to create VTXO batch'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vtxos/assign', methods=['POST'])
def assign_vtxo_to_user():
    """Assign a VTXO to a user"""
    try:
        data = request.get_json()
        required_fields = ['user_pubkey', 'asset_id', 'amount_needed']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400

        vtxo_manager = get_vtxo_manager()
        vtxo = vtxo_manager.assign_vtxo_to_user(
            user_pubkey=data['user_pubkey'],
            asset_id=data['asset_id'],
            amount_needed=data['amount_needed']
        )

        if vtxo:
            return jsonify({
                'message': 'VTXO assigned successfully',
                'vtxo_id': vtxo.vtxo_id,
                'user_pubkey': vtxo.user_pubkey[:8] + '...',
                'asset_id': vtxo.asset_id,
                'amount_sats': vtxo.amount_sats,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': 'No available VTXO for assignment'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vtxos/user/<user_pubkey>')
def get_user_vtxos(user_pubkey):
    """Get VTXOs assigned to a user"""
    try:
        asset_id = request.args.get('asset_id')
        vtxo_manager = get_vtxo_manager()
        vtxos = vtxo_manager.get_user_vtxos(user_pubkey, asset_id)

        vtxos_data = []
        for vtxo in vtxos:
            vtxos_data.append({
                'vtxo_id': vtxo.vtxo_id,
                'asset_id': vtxo.asset_id,
                'amount_sats': vtxo.amount_sats,
                'status': vtxo.status,
                'created_at': vtxo.created_at.isoformat(),
                'expires_at': vtxo.expires_at.isoformat()
            })

        return jsonify({
            'vtxos': vtxos_data,
            'user_pubkey': user_pubkey[:8] + '...',
            'total_count': len(vtxos_data),
            'asset_filter': asset_id,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vtxos/mark-spent', methods=['POST'])
def mark_vtxo_spent():
    """Mark a VTXO as spent"""
    try:
        data = request.get_json()
        required_fields = ['vtxo_id', 'spending_txid']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400

        vtxo_manager = get_vtxo_manager()
        vtxo_manager.mark_vtxo_spent(data['vtxo_id'], data['spending_txid'])

        return jsonify({
            'message': 'VTXO marked as spent successfully',
            'vtxo_id': data['vtxo_id'],
            'spending_txid': data['spending_txid'],
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vtxos/cleanup', methods=['POST'])
def cleanup_expired_vtxos():
    """Clean up expired VTXOs"""
    try:
        vtxo_manager = get_vtxo_manager()
        cleaned_count = vtxo_manager.cleanup_expired_vtxos()

        return jsonify({
            'message': 'VTXO cleanup completed',
            'cleaned_count': cleaned_count,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vtxos/settlement/process', methods=['POST'])
def process_vtxo_settlement():
    """Manually trigger VTXO settlement processing"""
    try:
        settlement_manager = get_settlement_manager()
        settlement_manager.process_hourly_settlement()

        return jsonify({
            'message': 'VTXO settlement processing triggered',
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vtxos/settlement/status')
def get_settlement_status():
    """Get VTXO settlement status"""
    try:
        session = get_session()
        try:
            # Get settlement statistics
            total_vtxos = session.query(Vtxo).count()
            available_vtxos = session.query(Vtxo).filter(Vtxo.status == 'available').count()
            assigned_vtxos = session.query(Vtxo).filter(Vtxo.status == 'assigned').count()
            spent_vtxos = session.query(Vtxo).filter(Vtxo.status == 'spent').count()
            settled_vtxos = session.query(Vtxo).filter(Vtxo.status == 'settled').count()

            # Get recent settlements
            recent_settlements = session.query(Transaction).filter(
                Transaction.tx_type == 'settlement_tx'
            ).order_by(Transaction.created_at.desc()).limit(10).all()

            settlements_data = []
            for tx in recent_settlements:
                settlements_data.append({
                    'txid': tx.txid,
                    'status': tx.status,
                    'amount_sats': tx.amount_sats,
                    'fee_sats': tx.fee_sats,
                    'created_at': tx.created_at.isoformat()
                })

            return jsonify({
                'settlement_status': {
                    'total_vtxos': total_vtxos,
                    'available_vtxos': available_vtxos,
                    'assigned_vtxos': assigned_vtxos,
                    'spent_vtxos': spent_vtxos,
                    'settled_vtxos': settled_vtxos,
                    'pending_settlement': spent_vtxos - settled_vtxos
                },
                'recent_settlements': settlements_data,
                'timestamp': datetime.now().isoformat()
            })

        finally:
            session.close()

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vtxos/monitor/start', methods=['POST'])
def start_vtxo_monitoring():
    """Start VTXO monitoring services"""
    try:
        global vtxo_manager, settlement_manager

        if vtxo_manager and vtxo_manager.inventory_monitor.running:
            return jsonify({'message': 'VTXO monitoring already running'})

        vtxo_manager = get_vtxo_manager()
        settlement_manager = get_settlement_manager()

        vtxo_manager.start_services()
        settlement_manager.start_settlement_service()

        return jsonify({
            'message': 'VTXO monitoring services started',
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vtxos/monitor/stop', methods=['POST'])
def stop_vtxo_monitoring():
    """Stop VTXO monitoring services"""
    try:
        global vtxo_manager, settlement_manager

        if vtxo_manager:
            vtxo_manager.stop_services()

        if settlement_manager:
            settlement_manager.stop_settlement_service()

        return jsonify({
            'message': 'VTXO monitoring services stopped',
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vtxos/monitor/status')
def get_vtxo_monitoring_status():
    """Get VTXO monitoring status"""
    try:
        global vtxo_manager, settlement_manager

        inventory_running = vtxo_manager.inventory_monitor.running if vtxo_manager else False
        settlement_running = settlement_manager.running if settlement_manager else False

        return jsonify({
            'monitoring_status': {
                'inventory_monitoring': inventory_running,
                'settlement_service': settlement_running,
                'overall_status': 'running' if (inventory_running and settlement_running) else 'stopped'
            },
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/vtxos/stats')
def get_vtxo_stats():
    """Get comprehensive VTXO statistics"""
    try:
        session = get_session()
        try:
            # Get VTXO counts by asset
            from sqlalchemy import func
            asset_stats = session.query(
                Asset.asset_id,
                Asset.ticker,
                func.count(Vtxo.id).label('total_vtxos'),
                func.sum(func.case([(Vtxo.status == 'available', 1)], else_=0)).label('available_vtxos'),
                func.sum(func.case([(Vtxo.status == 'assigned', 1)], else_=0)).label('assigned_vtxos'),
                func.sum(func.case([(Vtxo.status == 'spent', 1)], else_=0)).label('spent_vtxos'),
                func.sum(func.case([(Vtxo.status == 'settled', 1)], else_=0)).label('settled_vtxos')
            ).join(Vtxo, Asset.asset_id == Vtxo.asset_id, isouter=True).group_by(Asset.asset_id, Asset.ticker).all()

            stats_data = []
            for stat in asset_stats:
                stats_data.append({
                    'asset_id': stat.asset_id,
                    'ticker': stat.ticker,
                    'total_vtxos': stat.total_vtxos or 0,
                    'available_vtxos': stat.available_vtxos or 0,
                    'assigned_vtxos': stat.assigned_vtxos or 0,
                    'spent_vtxos': stat.spent_vtxos or 0,
                    'settled_vtxos': stat.settled_vtxos or 0,
                    'utilization_rate': round((stat.assigned_vtxos / stat.total_vtxos * 100) if stat.total_vtxos > 0 else 0, 2)
                })

            # Get overall statistics
            total_vtxos = session.query(Vtxo).count()
            total_value = session.query(func.sum(Vtxo.amount_sats)).scalar() or 0

            return jsonify({
                'vtxo_statistics': {
                    'overall': {
                        'total_vtxos': total_vtxos,
                        'total_value_sats': total_value,
                        'average_vtxo_value': round(total_value / total_vtxos, 2) if total_vtxos > 0 else 0
                    },
                    'by_asset': stats_data
                },
                'timestamp': datetime.now().isoformat()
            })

        finally:
            session.close()

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def initialize_services():
    """Initialize all services when the app starts"""
    global nostr_client, redis_manager, event_handler, vtxo_manager, settlement_manager, monitoring_system, cache_manager

    # Initialize monitoring system first
    try:
        if os.getenv('MONITORING_AUTO_START', 'true').lower() == 'true':
            monitoring_system = initialize_monitoring()
            cache_manager = get_cache_manager()
            print("✅ Monitoring system initialized")
    except Exception as e:
        print(f"❌ Failed to initialize monitoring system: {e}")

    # Initialize performance optimization systems
    try:
        if os.getenv('PERFORMANCE_OPTIMIZATION', 'true').lower() == 'true':
            perf_initialized = initialize_performance_systems()
            if perf_initialized:
                print("✅ Performance optimization systems initialized")
    except Exception as e:
        print(f"❌ Failed to initialize performance systems: {e}")

    # Auto-start Lightning service if configured
    if os.getenv('LIGHTNING_AUTO_START', 'true').lower() == 'true':
        try:
            lightning_initialized = initialize_lightning_services()
            if lightning_initialized:
                print("✅ Lightning service auto-started")
            else:
                print("❌ Lightning service failed to start")
        except Exception as e:
            print(f"❌ Failed to auto-start Lightning service: {e}")

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

    # Auto-start VTXO services if configured
    if os.getenv('VTXO_AUTO_START', 'true').lower() == 'true':
        try:
            vtxo_initialized = initialize_vtxo_services()
            if vtxo_initialized:
                vtxo_manager = get_vtxo_manager()
                settlement_manager = get_settlement_manager()
                print("✅ VTXO services auto-started")
            else:
                print("❌ VTXO services failed to start")
        except Exception as e:
            print(f"❌ Failed to auto-start VTXO services: {e}")

if __name__ == '__main__':
    # Initialize services on startup
    initialize_services()
    app.run(debug=True, host='0.0.0.0', port=8000)