from redis import Redis
from rq_scheduler import Scheduler
from datetime import datetime
import time
import logging
from tasks import log_system_stats, send_heartbeat, cleanup_old_logs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_scheduler():
    """Setup and configure the scheduler with periodic tasks"""

    redis_conn = Redis(host='redis', port=6379, db=0)
    scheduler = Scheduler(connection=redis_conn, queue_name='default')

    # Clear existing scheduled jobs to avoid duplicates
    scheduler.cancel('system-stats')
    scheduler.cancel('heartbeat')
    scheduler.cancel('cleanup')

    logger.info("🗓️  Setting up scheduled jobs...")

    # Schedule system stats every 5 minutes
    scheduler.schedule(
        datetime.utcnow(),
        func=log_system_stats,
        interval=300,  # 5 minutes
        timeout=60,
        id='system-stats'
    )
    logger.info("✅ Scheduled system stats every 5 minutes")

    # Schedule heartbeat every 1 minute
    scheduler.schedule(
        datetime.utcnow(),
        func=send_heartbeat,
        interval=60,  # 1 minute
        timeout=30,
        id='heartbeat'
    )
    logger.info("✅ Scheduled heartbeat every 1 minute")

    # Schedule cleanup every hour
    scheduler.schedule(
        datetime.utcnow(),
        func=cleanup_old_logs,
        interval=3600,  # 1 hour
        timeout=120,
        id='cleanup'
    )
    logger.info("✅ Scheduled cleanup every hour")

    # List all scheduled jobs
    jobs = scheduler.get_jobs()
    logger.info(f"📋 Total scheduled jobs: {len(jobs)}")
    for job in jobs:
        logger.info(f"   - {job.id}: {job.func_name} (next run: {job.next_run_time})")

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