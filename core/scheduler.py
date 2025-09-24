from redis import Redis
from rq_scheduler import Scheduler
from datetime import datetime, timezone
import time
import logging
import os
from tasks import log_system_stats, send_heartbeat, cleanup_old_logs, cleanup_expired_sessions, cleanup_vtxos

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def utc_now() -> datetime:
    """Return current UTC time as a naive datetime (UTC) without deprecation warnings."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

def setup_scheduler():
    """Setup and configure the scheduler with periodic tasks"""

    # Use REDIS_URL environment variable or fallback to default
    redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    redis_conn = Redis.from_url(redis_url)
    scheduler = Scheduler(connection=redis_conn, queue_name='default')

    # Clear existing scheduled jobs to avoid duplicates
    scheduler.cancel('system-stats')
    scheduler.cancel('heartbeat')
    scheduler.cancel('cleanup')
    scheduler.cancel('session-cleanup')
    scheduler.cancel('vtxo-cleanup')

    logger.info("🗓️  Setting up scheduled jobs...")

    # Schedule system stats every 5 minutes
    scheduler.schedule(
        utc_now(),
        func=log_system_stats,
        interval=300,  # 5 minutes
        timeout=60,
        id='system-stats',
        result_ttl=300  # Store results for 5 minutes
    )
    logger.info("✅ Scheduled system stats every 5 minutes")

    # Schedule heartbeat every 1 minute
    scheduler.schedule(
        utc_now(),
        func=send_heartbeat,
        interval=60,  # 1 minute
        timeout=30,
        id='heartbeat',
        result_ttl=0  # Don't store heartbeat results at all
    )
    logger.info("✅ Scheduled heartbeat every 1 minute")

    # Schedule cleanup every hour
    scheduler.schedule(
        utc_now(),
        func=cleanup_old_logs,
        interval=3600,  # 1 hour
        timeout=120,
        id='cleanup',
        result_ttl=600  # Store results for 10 minutes
    )
    logger.info("✅ Scheduled cleanup every hour")

    # Schedule session cleanup every 5 minutes
    scheduler.schedule(
        utc_now(),
        func=cleanup_expired_sessions,
        interval=300,  # 5 minutes
        timeout=60,
        id='session-cleanup',
        result_ttl=300  # Store results for 5 minutes
    )
    logger.info("✅ Scheduled session cleanup every 5 minutes")

    # Schedule VTXO cleanup every 30 minutes
    scheduler.schedule(
        utc_now(),
        func=cleanup_vtxos,
        interval=1800,  # 30 minutes
        timeout=60,
        id='vtxo-cleanup',
        result_ttl=600  # Store results for 10 minutes
    )
    logger.info("✅ Scheduled VTXO cleanup every 30 minutes")

    # List all scheduled jobs
    jobs = list(scheduler.get_jobs())
    logger.info(f"📋 Total scheduled jobs: {len(jobs)}")
    for job in jobs:
        logger.info(f"   - {job.id}: {job.func_name} (next run: {job.created_at})")

    return scheduler

def run_scheduler():
    """Run the scheduler in a loop"""
    logger.info("🚀 Starting scheduler...")
    scheduler = setup_scheduler()

    try:
        while True:
            # Run any pending jobs
            scheduler.run()

            # Sleep for a bit before checking again
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("🛑 Scheduler stopped by user")
    except Exception as e:
        logger.error(f"❌ Scheduler error: {e}")
        raise

if __name__ == '__main__':
    run_scheduler()