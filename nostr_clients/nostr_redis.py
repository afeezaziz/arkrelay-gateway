import json
import logging
import threading
import time
from datetime import datetime
from typing import Dict, Any, Callable, Optional

from redis import Redis
from rq import Queue
from core.config import Config

logger = logging.getLogger(__name__)

class NostrRedisManager:
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_conn = Redis.from_url(redis_url or Config.REDIS_URL)
        self.queue = Queue(connection=self.redis_conn, default_result_ttl=3600)

        # Pub/Sub channels
        self.channels = {
            'action_intent': [],
            'signing_response': [],
            'session_status': [],
            'gateway_events': []
        }

        # Subscriptions
        self.pubsub = self.redis_conn.pubsub()
        self._running = False
        self._worker_thread = None

        # Statistics
        self.stats = {
            'messages_processed': 0,
            'messages_published': 0,
            'jobs_enqueued': 0,
            'errors': 0
        }

        logger.info("Initialized Nostr Redis manager")

    def subscribe_to_channel(self, channel: str, handler: Callable[[Dict[str, Any]], None]):
        """Subscribe to a Redis channel"""
        if channel in self.channels:
            self.channels[channel].append(handler)
            logger.info(f"Added handler for channel: {channel}")
        else:
            logger.warning(f"Unknown channel: {channel}")

    def publish_to_channel(self, channel: str, data: Dict[str, Any]):
        """Publish data to a Redis channel"""
        try:
            message = json.dumps(data)
            self.redis_conn.publish(channel, message)
            self.stats['messages_published'] += 1

            logger.debug(f"Published to {channel}: {message[:100]}...")

        except Exception as e:
            logger.error(f"Error publishing to {channel}: {e}")
            self.stats['errors'] += 1

    def start_listening(self):
        """Start listening to Redis pub/sub messages"""
        if self._running:
            logger.warning("Redis pub/sub listener is already running")
            return

        # Subscribe to all channels
        for channel in self.channels.keys():
            self.pubsub.subscribe(channel)

        self._running = True
        self._worker_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._worker_thread.start()
        logger.info("Started Redis pub/sub listener")

    def stop_listening(self):
        """Stop listening to Redis pub/sub messages"""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)

        self.pubsub.unsubscribe()
        logger.info("Stopped Redis pub/sub listener")

    def _listen_loop(self):
        """Main listening loop for Redis pub/sub"""
        logger.info("Starting Redis pub/sub listening loop")

        while self._running:
            try:
                message = self.pubsub.get_message(timeout=1.0)
                if message and message['type'] == 'message':
                    self._process_message(message)

            except Exception as e:
                logger.error(f"Error in Redis pub/sub loop: {e}")
                self.stats['errors'] += 1
                time.sleep(1)  # Wait before retrying

    def _process_message(self, message: Dict[str, Any]):
        """Process a received Redis message"""
        try:
            channel = message['channel'].decode('utf-8')
            data = json.loads(message['data'].decode('utf-8'))

            self.stats['messages_processed'] += 1

            logger.debug(f"Received message from {channel}: {data}")

            # Route to appropriate handlers
            if channel in self.channels:
                for handler in self.channels[channel]:
                    try:
                        handler(data)
                    except Exception as e:
                        logger.error(f"Error in handler for {channel}: {e}")
                        self.stats['errors'] += 1

        except Exception as e:
            logger.error(f"Error processing Redis message: {e}")
            self.stats['errors'] += 1

    def enqueue_job(self, job_func: str, args: list = None, kwargs: dict = None,
                   job_timeout: int = 300, job_id: str = None) -> Optional[str]:
        """Enqueue a background job"""
        try:
            job = self.queue.enqueue(
                job_func,
                args=args or [],
                kwargs=kwargs or {},
                timeout=job_timeout,
                job_id=job_id
            )

            self.stats['jobs_enqueued'] += 1
            logger.info(f"Enqueued job {job.id}: {job_func}")

            return job.id

        except Exception as e:
            logger.error(f"Error enqueuing job {job_func}: {e}")
            self.stats['errors'] += 1
            return None

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a background job"""
        try:
            job = self.queue.fetch_job(job_id)
            if not job:
                return None

            return {
                'id': job.id,
                'status': job.get_status(),
                'result': job.result,
                'exc_info': job.exc_info,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'enqueued_at': job.enqueued_at.isoformat() if job.enqueued_at else None,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'ended_at': job.ended_at.isoformat() if job.ended_at else None
            }

        except Exception as e:
            logger.error(f"Error getting job status for {job_id}: {e}")
            return None

    def store_session_data(self, session_id: str, data: Dict[str, Any], ttl: int = 3600):
        """Store session data in Redis with TTL"""
        try:
            key = f"session:{session_id}"
            self.redis_conn.setex(key, ttl, json.dumps(data))
            logger.debug(f"Stored session data for {session_id}")
        except Exception as e:
            logger.error(f"Error storing session data for {session_id}: {e}")

    def get_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data from Redis"""
        try:
            key = f"session:{session_id}"
            data = self.redis_conn.get(key)
            if data:
                return json.loads(data.decode('utf-8'))
            return None
        except Exception as e:
            logger.error(f"Error retrieving session data for {session_id}: {e}")
            return None

    def delete_session_data(self, session_id: str):
        """Delete session data from Redis"""
        try:
            key = f"session:{session_id}"
            self.redis_conn.delete(key)
            logger.debug(f"Deleted session data for {session_id}")
        except Exception as e:
            logger.error(f"Error deleting session data for {session_id}: {e}")

    def cache_asset_balances(self, user_pubkey: str, balances: Dict[str, int], ttl: int = 300):
        """Cache user asset balances in Redis"""
        try:
            key = f"balances:{user_pubkey}"
            self.redis_conn.setex(key, ttl, json.dumps(balances))
            logger.debug(f"Cached balances for {user_pubkey[:8]}...")
        except Exception as e:
            logger.error(f"Error caching balances for {user_pubkey}: {e}")

    def get_cached_balances(self, user_pubkey: str) -> Optional[Dict[str, int]]:
        """Get cached user asset balances from Redis"""
        try:
            key = f"balances:{user_pubkey}"
            data = self.redis_conn.get(key)
            if data:
                return json.loads(data.decode('utf-8'))
            return None
        except Exception as e:
            logger.error(f"Error getting cached balances for {user_pubkey}: {e}")
            return None

    def rate_limit_check(self, key: str, limit: int, window: int) -> bool:
        """Check if a key has exceeded rate limit"""
        try:
            current = self.redis_conn.incr(key)
            if current == 1:
                self.redis_conn.expire(key, window)
            return current <= limit
        except Exception as e:
            logger.error(f"Error checking rate limit for {key}: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get Redis manager statistics"""
        return {
            **self.stats,
            'running': self._running,
            'queue_size': self.queue.count,
            'channel_count': len(self.channels),
            'handler_count': {k: len(v) for k, v in self.channels.items()}
        }

# Global Redis manager instance
_redis_manager = None

def get_redis_manager() -> NostrRedisManager:
    """Get the global Redis manager instance"""
    global _redis_manager
    if _redis_manager is None:
        _redis_manager = NostrRedisManager()
    return _redis_manager

def initialize_redis_manager():
    """Initialize the global Redis manager"""
    manager = get_redis_manager()
    manager.start_listening()
    logger.info("Nostr Redis manager initialized")
    return manager

def shutdown_redis_manager():
    """Shutdown the global Redis manager"""
    global _redis_manager
    if _redis_manager:
        _redis_manager.stop_listening()
        _redis_manager = None
        logger.info("Nostr Redis manager shutdown")