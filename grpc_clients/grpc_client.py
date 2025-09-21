"""
Unified gRPC Client Layer for Ark Relay Gateway

This module provides a unified interface for communicating with arkd, tapd, and lnd daemons
through gRPC with connection pooling, retry logic, and circuit breakers.
"""

import os
import time
import logging
import threading
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Union, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
import grpc
from grpc import StatusCode

from core.config import Config

logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """Service types for gRPC clients"""
    ARKD = "arkd"
    TAPD = "tapd"
    LND = "lnd"


@dataclass
class ConnectionConfig:
    """Configuration for gRPC connection"""
    host: str
    port: int
    tls_cert: Optional[str] = None
    macaroon: Optional[str] = None
    timeout_seconds: int = 30
    max_message_length: int = 4 * 1024 * 1024  # 4MB


class CircuitBreakerState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"         # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service is back


class CircuitBreaker:
    """Circuit breaker for gRPC service protection"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
        self._lock = threading.Lock()

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = CircuitBreakerState.HALF_OPEN
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                else:
                    raise ConnectionError(f"Circuit breaker is OPEN - service unavailable")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        """Handle successful call"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.CLOSED
            logger.info("Circuit breaker reset to CLOSED")
        self.failure_count = 0

    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if (self.state == CircuitBreakerState.CLOSED and
            self.failure_count >= self.failure_threshold):
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")


class GrpcClientBase(ABC):
    """Base class for all gRPC clients"""

    def __init__(self, service_type: ServiceType, config: ConnectionConfig):
        self.service_type = service_type
        self.config = config
        self.channel = None
        self.stub = None
        self.circuit_breaker = CircuitBreaker()
        self._lock = threading.Lock()

        # Initialize connection
        self._connect()

    def _connect(self):
        """Establish gRPC connection"""
        try:
            if self.channel:
                self.channel.close()

            # Create channel options
            options = [
                ('grpc.max_send_message_length', self.config.max_message_length),
                ('grpc.max_receive_message_length', self.config.max_message_length),
                ('grpc.keepalive_time_ms', 30000),
                ('grpc.keepalive_timeout_ms', 5000),
                ('grpc.keepalive_permit_without_calls', 1),
            ]

            # Create channel
            if self.config.tls_cert:
                # TLS connection
                with open(self.config.tls_cert, 'rb') as f:
                    cert = f.read()
                credentials = grpc.ssl_channel_credentials(cert)
                self.channel = grpc.secure_channel(
                    f"{self.config.host}:{self.config.port}",
                    credentials,
                    options=options
                )
            else:
                # Insecure connection (development only)
                self.channel = grpc.insecure_channel(
                    f"{self.config.host}:{self.config.port}",
                    options=options
                )

            # Create stub
            self.stub = self._create_stub()

            logger.info(f"Connected to {self.service_type.value} at {self.config.host}:{self.config.port}")

        except Exception as e:
            logger.error(f"Failed to connect to {self.service_type.value}: {e}")
            raise

    @abstractmethod
    def _create_stub(self):
        """Create gRPC stub for specific service"""
        pass

    def _execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute gRPC call with retry logic and circuit breaker"""
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                return self.circuit_breaker.call(func, *args, **kwargs)

            except grpc.RpcError as e:
                if e.code() in [StatusCode.DEADLINE_EXCEEDED, StatusCode.UNAVAILABLE]:
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Retry {attempt + 1}/{max_retries} for {self.service_type.value} after {delay}s")
                    time.sleep(delay)
                else:
                    raise

            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Retry {attempt + 1}/{max_retries} for {self.service_type.value} after {delay}s")
                time.sleep(delay)

    def health_check(self) -> bool:
        """Check if service is healthy"""
        try:
            return self._execute_with_retry(self._health_check_impl)
        except Exception as e:
            logger.error(f"Health check failed for {self.service_type.value}: {e}")
            return False

    @abstractmethod
    def _health_check_impl(self) -> bool:
        """Implementation-specific health check"""
        pass

    def close(self):
        """Close gRPC connection"""
        if self.channel:
            self.channel.close()
            logger.info(f"Closed connection to {self.service_type.value}")


class GrpcClientManager:
    """Manager for all gRPC clients with connection pooling"""

    def __init__(self):
        self.clients: Dict[ServiceType, GrpcClientBase] = {}
        self._lock = threading.Lock()
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize all gRPC clients"""
        try:
            config = Config()

            # ARKD client
            arkd_config = ConnectionConfig(
                host=config.ARKD_HOST,
                port=config.ARKD_PORT,
                tls_cert=config.ARKD_TLS_CERT,
                macaroon=config.ARKD_MACAROON,
                timeout_seconds=config.GRPC_TIMEOUT_SECONDS,
                max_message_length=config.GRPC_MAX_MESSAGE_LENGTH
            )
            self.clients[ServiceType.ARKD] = ArkdClient(arkd_config)

            # TAPD client
            tapd_config = ConnectionConfig(
                host=config.TAPD_HOST,
                port=config.TAPD_PORT,
                tls_cert=config.TAPD_TLS_CERT,
                macaroon=config.TAPD_MACAROON,
                timeout_seconds=config.GRPC_TIMEOUT_SECONDS,
                max_message_length=config.GRPC_MAX_MESSAGE_LENGTH
            )
            self.clients[ServiceType.TAPD] = TapdClient(tapd_config)

            # LND client
            lnd_config = ConnectionConfig(
                host=config.LND_HOST,
                port=config.LND_PORT,
                tls_cert=config.LND_TLS_CERT,
                macaroon=config.LND_MACAROON,
                timeout_seconds=config.GRPC_TIMEOUT_SECONDS,
                max_message_length=config.GRPC_MAX_MESSAGE_LENGTH
            )
            self.clients[ServiceType.LND] = LndClient(lnd_config)

            logger.info("Initialized all gRPC clients")

        except Exception as e:
            logger.error(f"Failed to initialize gRPC clients: {e}")
            raise

    def get_client(self, service_type: ServiceType) -> GrpcClientBase:
        """Get gRPC client for specific service"""
        with self._lock:
            return self.clients.get(service_type)

    def health_check_all(self) -> Dict[ServiceType, bool]:
        """Check health of all services"""
        results = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                service_type: executor.submit(client.health_check)
                for service_type, client in self.clients.items()
            }

            for service_type, future in futures.items():
                try:
                    results[service_type] = future.result(timeout=10)
                except Exception as e:
                    logger.error(f"Health check failed for {service_type.value}: {e}")
                    results[service_type] = False

        return results

    def reconnect(self, service_type: ServiceType):
        """Reconnect to specific service"""
        with self._lock:
            if service_type in self.clients:
                try:
                    self.clients[service_type]._connect()
                    logger.info(f"Reconnected to {service_type.value}")
                except Exception as e:
                    logger.error(f"Failed to reconnect to {service_type.value}: {e}")
                    raise

    def close_all(self):
        """Close all gRPC connections"""
        with self._lock:
            for client in self.clients.values():
                try:
                    client.close()
                except Exception as e:
                    logger.error(f"Error closing client: {e}")
            logger.info("Closed all gRPC connections")


# Global instance (lazy initialization)
_grpc_manager = None


def get_grpc_manager() -> GrpcClientManager:
    """Get global gRPC manager instance"""
    global _grpc_manager
    if _grpc_manager is None:
        _grpc_manager = GrpcClientManager()
    return _grpc_manager


# Import specific client implementations
from .arkd_client import ArkdClient
from .tapd_client import TapdClient
from .lnd_client import LndClient