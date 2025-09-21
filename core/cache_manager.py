"""
Advanced caching and connection pooling system for ArkRelay Gateway.
Implements Redis-based caching, database connection pooling, and memory optimization.
"""

import time
import threading
import json
import hashlib
from typing import Any, Dict, Optional, List, Callable
from datetime import datetime, timedelta
from functools import wraps
from redis import Redis
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool, NullPool
from sqlalchemy.orm import sessionmaker, scoped_session
import psutil
import gc

from core.config import Config

class CacheManager:
    """Advanced caching system with Redis backend"""

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.local_cache = {}  # Simple in-memory cache for hot data
        self.local_cache_lock = threading.RLock()
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'redis_hits': 0,
            'local_hits': 0,
            'sets': 0,
            'deletes': 0,
            'evictions': 0
        }

    def _generate_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate consistent cache key"""
        key_data = {
            'prefix': prefix,
            'args': args,
            'kwargs': kwargs
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return f"arkrelay:{hashlib.md5(key_str.encode()).hexdigest()}"

    def get(self, key: str, default=None) -> Any:
        """Get value from cache (local first, then Redis)"""
        try:
            # Check local cache first
            with self.local_cache_lock:
                if key in self.local_cache:
                    cache_entry = self.local_cache[key]
                    if cache_entry['expires'] > time.time():
                        self.cache_stats['hits'] += 1
                        self.cache_stats['local_hits'] += 1
                        return cache_entry['value']
                    else:
                        # Expired, remove from local cache
                        del self.local_cache[key]
                        self.cache_stats['evictions'] += 1

            # Check Redis
            cached_data = self.redis.get(key)
            if cached_data is not None:
                try:
                    data = json.loads(cached_data.decode('utf-8'))
                    self.cache_stats['hits'] += 1
                    self.cache_stats['redis_hits'] += 1

                    # Cache in local memory for future access
                    self._set_local_cache(key, data, ttl=60)  # Short TTL for local cache
                    return data
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

            self.cache_stats['misses'] += 1
            return default

        except Exception as e:
            # Cache failure shouldn't break the application
            return default

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set value in cache with TTL"""
        try:
            # Store in Redis
            serialized = json.dumps(value, default=str)
            result = self.redis.setex(key, ttl, serialized)

            # Store in local cache with shorter TTL
            self._set_local_cache(key, value, ttl=min(ttl, 300))

            self.cache_stats['sets'] += 1
            return bool(result)

        except Exception as e:
            return False

    def _set_local_cache(self, key: str, value: Any, ttl: int):
        """Set value in local cache"""
        with self.local_cache_lock:
            # Clean up expired entries if cache is getting large
            if len(self.local_cache) > 1000:
                self._cleanup_local_cache()

            self.local_cache[key] = {
                'value': value,
                'expires': time.time() + ttl
            }

    def _cleanup_local_cache(self):
        """Clean up expired local cache entries"""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.local_cache.items()
            if entry['expires'] <= current_time
        ]

        for key in expired_keys:
            del self.local_cache[key]

        self.cache_stats['evictions'] += len(expired_keys)

    def delete(self, key: str) -> bool:
        """Delete value from cache"""
        try:
            # Delete from both caches
            with self.local_cache_lock:
                if key in self.local_cache:
                    del self.local_cache[key]

            result = self.redis.delete(key)
            self.cache_stats['deletes'] += 1
            return bool(result)

        except Exception:
            return False

    def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching a pattern"""
        try:
            keys = self.redis.keys(pattern)
            if keys:
                deleted = self.redis.delete(*keys)

                # Clear from local cache
                with self.local_cache_lock:
                    keys_str = [k.decode('utf-8') for k in keys]
                    for key in list(self.local_cache.keys()):
                        if any(key_str in key for key_str in keys_str):
                            del self.local_cache[key]

                return deleted
            return 0

        except Exception:
            return 0

    def cache_function(self, ttl: int = 300, key_prefix: str = 'func'):
        """Decorator to cache function results"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Generate cache key
                cache_key = self._generate_cache_key(key_prefix, func.__name__, *args, **kwargs)

                # Try to get from cache
                cached_result = self.get(cache_key)
                if cached_result is not None:
                    return cached_result

                # Execute function and cache result
                result = func(*args, **kwargs)
                self.set(cache_key, result, ttl)
                return result

            return wrapper
        return decorator

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            redis_info = self.redis.info()
            total_keys = len(self.local_cache)

            return {
                'hits': self.cache_stats['hits'],
                'misses': self.cache_stats['misses'],
                'hit_rate': round(
                    self.cache_stats['hits'] / (self.cache_stats['hits'] + self.cache_stats['misses']) * 100,
                    2
                ) if (self.cache_stats['hits'] + self.cache_stats['misses']) > 0 else 0,
                'redis_hits': self.cache_stats['redis_hits'],
                'local_hits': self.cache_stats['local_hits'],
                'sets': self.cache_stats['sets'],
                'deletes': self.cache_stats['deletes'],
                'evictions': self.cache_stats['evictions'],
                'local_cache_size': total_keys,
                'redis_memory_usage': redis_info.get('used_memory_human', 'N/A'),
                'redis_keyspace_hits': redis_info.get('keyspace_hits', 0),
                'redis_keyspace_misses': redis_info.get('keyspace_misses', 0)
            }
        except Exception:
            return self.cache_stats.copy()

class DatabaseConnectionPool:
    """Advanced database connection pooling"""

    def __init__(self):
        self.engine = None
        self.session_factory = None
        self.scoped_session = None
        self.pool_stats = {
            'total_connections': 0,
            'active_connections': 0,
            'idle_connections': 0,
            'overflow_connections': 0,
            'checkouts': 0,
            'invalidations': 0
        }

        self._initialize_pool()

    def _initialize_pool(self):
        """Initialize database connection pool"""
        try:
            # Parse database URL for pool configuration
            import urllib.parse as urlparse
            parsed = urlparse.urlparse(Config.DATABASE_URL)

            pool_config = {
                'pool_size': 10,
                'max_overflow': 20,
                'pool_timeout': 30,
                'pool_recycle': 3600,  # 1 hour
                'pool_pre_ping': True,
                'connect_args': {
                    'connect_timeout': 10,
                    'read_timeout': 30,
                    'write_timeout': 30
                }
            }

            # Adjust pool size based on environment
            if Config.FLASK_ENV == 'production':
                pool_config['pool_size'] = 20
                pool_config['max_overflow'] = 40
            elif Config.FLASK_ENV == 'testing':
                # Use NullPool for testing
                pool_config['poolclass'] = NullPool

            # Create engine with pool configuration
            self.engine = create_engine(
                Config.DATABASE_URL,
                **pool_config
            )

            # Create session factory
            self.session_factory = sessionmaker(bind=self.engine)
            self.scoped_session = scoped_session(self.session_factory)

            # Set up event listeners for statistics
            self._setup_pool_listeners()

        except Exception as e:
            raise RuntimeError(f"Failed to initialize database pool: {e}")

    def _setup_pool_listeners(self):
        """Setup event listeners for pool statistics"""
        from sqlalchemy import event

        @event.listens_for(self.engine, 'connect')
        def on_connect(dbapi_connection, connection_record):
            self.pool_stats['total_connections'] += 1

        @event.listens_for(self.engine, 'close')
        def on_close(dbapi_connection, connection_record):
            self.pool_stats['total_connections'] -= 1

        @event.listens_for(self.engine, 'checkin')
        def on_checkin(dbapi_connection, connection_record):
            self.pool_stats['active_connections'] -= 1
            self.pool_stats['idle_connections'] += 1

        @event.listens_for(self.engine, 'checkout')
        def on_checkout(dbapi_connection, connection_record, connection_proxy):
            self.pool_stats['active_connections'] += 1
            self.pool_stats['idle_connections'] -= 1
            self.pool_stats['checkouts'] += 1

    def get_session(self):
        """Get a database session from the pool"""
        if not self.scoped_session:
            self._initialize_pool()

        return self.scoped_session()

    def remove_session(self):
        """Remove the current thread-local session"""
        if self.scoped_session:
            self.scoped_session.remove()

    def get_pool_status(self) -> Dict[str, Any]:
        """Get connection pool status"""
        try:
            pool = self.engine.pool

            return {
                'pool_size': pool.size(),
                'checked_in': pool.checkedin(),
                'checked_out': pool.checkedout(),
                'overflow': pool.overflow(),
                'invalidated': pool.invalidated(),
                'total_connections': self.pool_stats['total_connections'],
                'active_connections': self.pool_stats['active_connections'],
                'idle_connections': self.pool_stats['idle_connections'],
                'checkouts': self.pool_stats['checkouts'],
                'invalidations': self.pool_stats['invalidations']
            }
        except Exception:
            return {}

    def close_all_connections(self):
        """Close all connections in the pool"""
        try:
            if self.engine:
                self.engine.dispose()
                self.engine = None
                self.session_factory = None
                self.scoped_session = None
                self.pool_stats = {k: 0 for k in self.pool_stats}
        except Exception:
            pass

class MemoryOptimizer:
    """Memory optimization utilities"""

    def __init__(self):
        self.optimization_stats = {
            'gc_collections': 0,
            'memory_freed_mb': 0,
            'optimizations_run': 0
        }

    def optimize_memory(self, force: bool = False) -> Dict[str, Any]:
        """Optimize memory usage"""
        try:
            # Get memory usage before optimization
            process = psutil.Process()
            memory_before = process.memory_info().rss / (1024 * 1024)  # MB

            # Force garbage collection
            if force:
                collected = gc.collect(2)  # Generation 2 collection
                self.optimization_stats['gc_collections'] += 1

            # Clear local caches if memory is high
            memory_after = process.memory_info().rss / (1024 * 1024)  # MB
            memory_freed = memory_before - memory_after

            if memory_freed > 0:
                self.optimization_stats['memory_freed_mb'] += memory_freed

            self.optimization_stats['optimizations_run'] += 1

            return {
                'memory_before_mb': round(memory_before, 2),
                'memory_after_mb': round(memory_after, 2),
                'memory_freed_mb': round(memory_freed, 2),
                'gc_objects_collected': collected if force else 0,
                'optimization_stats': self.optimization_stats.copy()
            }

        except Exception as e:
            return {'error': str(e)}

    def get_memory_info(self) -> Dict[str, Any]:
        """Get detailed memory information"""
        try:
            process = psutil.Process()

            return {
                'rss_mb': round(process.memory_info().rss / (1024 * 1024), 2),
                'vms_mb': round(process.memory_info().vms / (1024 * 1024), 2),
                'percent': process.memory_percent(),
                'threads': process.num_threads(),
                'open_files': process.num_fds(),
                'gc_stats': {
                    'generation_0': gc.get_count()[0],
                    'generation_1': gc.get_count()[1],
                    'generation_2': gc.get_count()[2],
                    'threshold': gc.get_threshold(),
                    'enabled': gc.isenabled()
                }
            }
        except Exception:
            return {}

class PerformanceOptimizer:
    """Comprehensive performance optimization"""

    def __init__(self, redis_client: Redis):
        self.cache_manager = CacheManager(redis_client)
        self.db_pool = DatabaseConnectionPool()
        self.memory_optimizer = MemoryOptimizer()
        self.optimization_thread = None
        self.running = False

    def start_optimization(self):
        """Start background optimization thread"""
        if self.optimization_thread and self.optimization_thread.is_alive():
            return

        self.running = True
        self.optimization_thread = threading.Thread(target=self._optimization_loop)
        self.optimization_thread.daemon = True
        self.optimization_thread.start()

    def stop_optimization(self):
        """Stop background optimization"""
        self.running = False
        if self.optimization_thread:
            self.optimization_thread.join(timeout=5)

    def _optimization_loop(self):
        """Background optimization loop"""
        while self.running:
            try:
                # Optimize memory every 5 minutes
                self.memory_optimizer.optimize_memory()

                # Clean up expired cache entries every 10 minutes
                self.cache_manager._cleanup_local_cache()

                # Sleep before next optimization
                time.sleep(300)  # 5 minutes

            except Exception as e:
                # Don't let optimization errors break the application
                time.sleep(60)  # Wait before retrying

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics"""
        return {
            'cache_stats': self.cache_manager.get_stats(),
            'db_pool_status': self.db_pool.get_pool_status(),
            'memory_info': self.memory_optimizer.get_memory_info(),
            'optimization_stats': self.memory_optimizer.optimization_stats.copy()
        }

    def cached_query(self, ttl: int = 300, query_type: str = 'default'):
        """Decorator to cache database query results"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Generate cache key based on function and arguments
                cache_key = self.cache_manager._generate_cache_key(
                    f"query_{query_type}",
                    func.__name__,
                    *args,
                    **kwargs
                )

                # Try to get from cache
                cached_result = self.cache_manager.get(cache_key)
                if cached_result is not None:
                    return cached_result

                # Execute query and cache result
                result = func(*args, **kwargs)
                self.cache_manager.set(cache_key, result, ttl)
                return result

            return wrapper
        return decorator

# Global instances
_cache_manager = None
_db_pool = None
_performance_optimizer = None

def get_cache_manager() -> CacheManager:
    """Get the global cache manager instance"""
    global _cache_manager
    if _cache_manager is None:
        redis_client = Redis.from_url(Config.REDIS_URL)
        _cache_manager = CacheManager(redis_client)
    return _cache_manager

def get_db_pool() -> DatabaseConnectionPool:
    """Get the global database connection pool instance"""
    global _db_pool
    if _db_pool is None:
        _db_pool = DatabaseConnectionPool()
    return _db_pool

def get_performance_optimizer() -> PerformanceOptimizer:
    """Get the global performance optimizer instance"""
    global _performance_optimizer
    if _performance_optimizer is None:
        redis_client = Redis.from_url(Config.REDIS_URL)
        _performance_optimizer = PerformanceOptimizer(redis_client)
    return _performance_optimizer

def initialize_performance_systems():
    """Initialize all performance optimization systems"""
    try:
        # Initialize components
        cache_manager = get_cache_manager()
        db_pool = get_db_pool()
        performance_optimizer = get_performance_optimizer()

        # Start background optimization
        performance_optimizer.start_optimization()

        return True
    except Exception as e:
        # Log error but don't fail startup
        print(f"Failed to initialize performance systems: {e}")
        return False

def shutdown_performance_systems():
    """Shutdown performance optimization systems"""
    try:
        performance_optimizer = get_performance_optimizer()
        performance_optimizer.stop_optimization()

        db_pool = get_db_pool()
        db_pool.close_all_connections()

    except Exception as e:
        print(f"Error shutting down performance systems: {e}")

# Utility function to create cached database queries
def create_cached_query_function(query_func, ttl: int = 300, cache_key_prefix: str = 'query'):
    """Create a cached version of a query function"""
    cache_manager = get_cache_manager()

    @wraps(query_func)
    def cached_query(*args, **kwargs):
        cache_key = cache_manager._generate_cache_key(cache_key_prefix, *args, **kwargs)

        # Try cache first
        result = cache_manager.get(cache_key)
        if result is not None:
            return result

        # Execute query and cache result
        result = query_func(*args, **kwargs)
        cache_manager.set(cache_key, result, ttl)
        return result

    return cached_query