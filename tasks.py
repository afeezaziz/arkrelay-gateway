import time
import json
import uuid
from datetime import datetime
import logging
import psutil
from models import JobLog, SystemMetrics, Heartbeat, get_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def sample_task(message):
    """Sample task that logs to console and writes to database"""
    job_id = str(uuid.uuid4())
    session = get_session()

    try:
        # Log job start to database
        job_log = JobLog(
            job_id=job_id,
            job_type='sample_task',
            status='running',
            message=f'Starting sample task: {message}'
        )
        session.add(job_log)
        session.commit()

        logger.info(f"🚀 Starting sample task: {message} (ID: {job_id})")
        time.sleep(2)

        # Log job completion to database
        result = {"status": "completed", "message": message, "timestamp": datetime.now().isoformat()}
        job_log.status = 'completed'
        job_log.result_data = json.dumps(result)
        job_log.duration_seconds = 2.0
        session.commit()

        logger.info(f"✅ Completed sample task: {message} (ID: {job_id})")
        return result

    except Exception as e:
        logger.error(f"❌ Failed sample task: {e}")
        job_log.status = 'failed'
        job_log.message = str(e)
        session.commit()
        raise
    finally:
        session.close()

def log_system_stats():
    """Task that logs system statistics to database"""
    session = get_session()

    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Log to console
        stats = {
            'timestamp': datetime.now().isoformat(),
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_available_mb': memory.available / (1024 * 1024),
            'disk_percent': disk.percent,
            'disk_free_gb': disk.free / (1024**3)
        }
        logger.info(f"📊 System Stats: {json.dumps(stats, indent=2)}")

        # Save to database
        system_metrics = SystemMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_available_mb=memory.available / (1024 * 1024),
            disk_percent=disk.percent,
            disk_free_gb=disk.free / (1024**3)
        )
        session.add(system_metrics)
        session.commit()

        return stats

    except Exception as e:
        logger.error(f"❌ Failed to log system stats: {e}")
        session.rollback()
        raise
    finally:
        session.close()

def cleanup_old_logs():
    """Task that simulates cleanup operations and logs to database"""
    job_id = str(uuid.uuid4())
    session = get_session()

    try:
        # Log cleanup start
        job_log = JobLog(
            job_id=job_id,
            job_type='cleanup',
            status='running',
            message='Starting cleanup of old logs...'
        )
        session.add(job_log)
        session.commit()

        logger.info("🧹 Starting cleanup of old logs...")
        time.sleep(1)

        # Simulate finding and cleaning old logs
        cleaned_files = 0  # Simulated count

        # Log cleanup completion
        job_log.status = 'completed'
        job_log.message = f'Cleanup completed - removed {cleaned_files} old log files'
        job_log.result_data = json.dumps({
            "status": "completed",
            "cleaned_files": cleaned_files,
            "timestamp": datetime.now().isoformat()
        })
        job_log.duration_seconds = 1.0
        session.commit()

        logger.info(f"✅ Cleanup completed - removed {cleaned_files} old log files")
        return {"status": "completed", "cleaned_files": cleaned_files, "timestamp": datetime.now().isoformat()}

    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        job_log.status = 'failed'
        job_log.message = str(e)
        session.commit()
        raise
    finally:
        session.close()

def send_heartbeat():
    """Task that sends heartbeat to log and database"""
    session = get_session()

    try:
        heartbeat = {
            'type': 'heartbeat',
            'timestamp': datetime.now().isoformat(),
            'status': 'alive'
        }

        # Log to console
        logger.info(f"💓 Heartbeat: {json.dumps(heartbeat)}")

        # Save to database
        db_heartbeat = Heartbeat(
            service_name='scheduler',
            is_alive=True,
            message='Scheduler heartbeat'
        )
        session.add(db_heartbeat)
        session.commit()

        return heartbeat

    except Exception as e:
        logger.error(f"❌ Failed to send heartbeat: {e}")
        session.rollback()
        raise
    finally:
        session.close()

def process_user_data(user_id, action_type, data):
    """Example task processing user data through Redis queue"""
    job_id = str(uuid.uuid4())
    session = get_session()

    try:
        # Log job start
        job_log = JobLog(
            job_id=job_id,
            job_type=f'user_{action_type}',
            status='running',
            message=f'Processing {action_type} for user {user_id}'
        )
        session.add(job_log)
        session.commit()

        logger.info(f"🔄 Processing {action_type} for user {user_id}")
        time.sleep(3)  # Simulate processing time

        # Process the data (example: save to database)
        result = {
            "status": "completed",
            "user_id": user_id,
            "action": action_type,
            "data_processed": len(data),
            "timestamp": datetime.now().isoformat()
        }

        # Log completion
        job_log.status = 'completed'
        job_log.result_data = json.dumps(result)
        job_log.duration_seconds = 3.0
        session.commit()

        logger.info(f"✅ Completed {action_type} for user {user_id}")
        return result

    except Exception as e:
        logger.error(f"❌ Failed to process user data: {e}")
        job_log.status = 'failed'
        job_log.message = str(e)
        session.commit()
        raise
    finally:
        session.close()

def cleanup_expired_sessions():
    """Clean up expired signing sessions and challenges"""
    job_id = str(uuid.uuid4())
    session = get_session()

    try:
        # Log job start
        job_log = JobLog(
            job_id=job_id,
            job_type='session_cleanup',
            status='running',
            message='Starting session cleanup'
        )
        session.add(job_log)
        session.commit()

        start_time = time.time()

        # Import the managers
        from session_manager import get_session_manager
        from challenge_manager import get_challenge_manager

        session_manager = get_session_manager()
        challenge_manager = get_challenge_manager()

        # Clean up expired sessions
        expired_sessions = session_manager.cleanup_expired_sessions()

        # Clean up expired challenges
        expired_challenges = challenge_manager.cleanup_expired_challenges()

        duration = time.time() - start_time

        # Log completion
        result = {
            "status": "completed",
            "expired_sessions_cleaned": expired_sessions,
            "expired_challenges_cleaned": expired_challenges,
            "total_cleaned": expired_sessions + expired_challenges,
            "duration_seconds": duration,
            "timestamp": datetime.now().isoformat()
        }

        job_log.status = 'completed'
        job_log.result_data = json.dumps(result)
        job_log.duration_seconds = duration
        session.commit()

        logger.info(f"✅ Session cleanup completed: {expired_sessions} sessions, {expired_challenges} challenges cleaned")
        return result

    except Exception as e:
        logger.error(f"❌ Failed to cleanup sessions: {e}")
        job_log.status = 'failed'
        job_log.message = str(e)
        session.commit()
        raise
    finally:
        session.close()

def enqueue_vtxo_replenishment(asset_id: str, count: int):
    """Enqueue a VTXO replenishment job"""
    from redis import Redis
    from rq import Queue
    import os

    redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    redis_conn = Redis.from_url(redis_url)
    q = Queue(connection=redis_conn)

    job = q.enqueue(
        'tasks.process_vtxo_replenishment',
        args=[asset_id, count],
        job_timeout=300,  # 5 minutes timeout
        job_id=f"vtxo_replenishment_{asset_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        result_ttl=3600  # Store results for 1 hour
    )

    logger.info(f"🔄 Enqueued VTXO replenishment job for asset {asset_id}: {count} VTXOs (Job ID: {job.id})")
    return job

def process_vtxo_replenishment(asset_id: str, count: int):
    """Process VTXO replenishment by creating new VTXOs"""
    job_id = f"vtxo_replenishment_{asset_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    session = get_session()

    try:
        # Log job start
        job_log = JobLog(
            job_id=job_id,
            job_type='vtxo_replenishment',
            status='running',
            message=f'Starting VTXO replenishment for asset {asset_id}: {count} VTXOs'
        )
        session.add(job_log)
        session.commit()

        start_time = time.time()

        # Get VTXO manager and create batch
        from vtxo_manager import get_vtxo_manager
        vtxo_manager = get_vtxo_manager()

        success = vtxo_manager.create_vtxo_batch(asset_id, count)

        duration = time.time() - start_time

        if success:
            result = {
                "status": "completed",
                "asset_id": asset_id,
                "vtxos_created": count,
                "duration_seconds": duration,
                "timestamp": datetime.now().isoformat()
            }

            job_log.status = 'completed'
            job_log.result_data = json.dumps(result)
            job_log.duration_seconds = duration
            session.commit()

            logger.info(f"✅ VTXO replenishment completed for asset {asset_id}: {count} VTXOs created")
            return result
        else:
            raise Exception("Failed to create VTXO batch")

    except Exception as e:
        logger.error(f"❌ Failed to process VTXO replenishment: {e}")
        job_log.status = 'failed'
        job_log.message = str(e)
        session.commit()
        raise
    finally:
        session.close()

def cleanup_vtxos():
    """Clean up expired VTXOs"""
    job_id = f"vtxo_cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    session = get_session()

    try:
        # Log job start
        job_log = JobLog(
            job_id=job_id,
            job_type='vtxo_cleanup',
            status='running',
            message='Starting VTXO cleanup'
        )
        session.add(job_log)
        session.commit()

        start_time = time.time()

        # Get VTXO manager and cleanup expired VTXOs
        from vtxo_manager import get_vtxo_manager
        vtxo_manager = get_vtxo_manager()

        cleaned_count = vtxo_manager.cleanup_expired_vtxos()

        duration = time.time() - start_time

        # Log completion
        result = {
            "status": "completed",
            "cleaned_vtxos": cleaned_count,
            "duration_seconds": duration,
            "timestamp": datetime.now().isoformat()
        }

        job_log.status = 'completed'
        job_log.result_data = json.dumps(result)
        job_log.duration_seconds = duration
        session.commit()

        logger.info(f"✅ VTXO cleanup completed: {cleaned_count} expired VTXOs cleaned")
        return result

    except Exception as e:
        logger.error(f"❌ Failed to cleanup VTXOs: {e}")
        job_log.status = 'failed'
        job_log.message = str(e)
        session.commit()
        raise
    finally:
        session.close()