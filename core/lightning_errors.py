"""
Lightning Error Handling and Recovery

This module provides specialized error handling and recovery mechanisms
for Lightning Network operations.
"""

import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class LightningErrorType(Enum):
    """Types of Lightning errors"""
    NETWORK_ERROR = "network_error"
    INVOICE_EXPIRED = "invoice_expired"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    CHANNEL_ERROR = "channel_error"
    PAYMENT_FAILED = "payment_failed"
    TIMEOUT_ERROR = "timeout_error"
    VALIDATION_ERROR = "validation_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class LightningError:
    """Lightning error information"""
    error_type: LightningErrorType
    message: str
    payment_hash: Optional[str] = None
    timestamp: datetime = None
    retry_count: int = 0
    max_retries: int = 3
    recoverable: bool = True

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class LightningErrorHandler:
    """Handles Lightning operation errors and recovery"""

    def __init__(self):
        self.error_history: List[LightningError] = []
        self.error_counts: Dict[LightningErrorType, int] = {}
        self.circuit_breaker_threshold = 5  # Consecutive errors before circuit breaker trips
        self.circuit_breaker_timeout = 300  # 5 minutes
        self.last_error_time = {}
        self.circuit_breaker_active = False
        self.circuit_breaker_until = None

    def handle_error(self, error: Exception, context: Dict[str, Any] = None) -> LightningError:
        """Handle a Lightning error"""
        lightning_error = self._classify_error(error, context)
        self._record_error(lightning_error)
        self._check_circuit_breaker(lightning_error)

        logger.error(f"Lightning error: {lightning_error.error_type.value} - {lightning_error.message}")

        return lightning_error

    def _classify_error(self, error: Exception, context: Dict[str, Any] = None) -> LightningError:
        """Classify the error type"""
        context = context or {}

        # Extract payment hash if available
        payment_hash = context.get('payment_hash')

        # Classify based on error message and type
        error_msg = str(error).lower()

        if "timeout" in error_msg:
            return LightningError(
                error_type=LightningErrorType.TIMEOUT_ERROR,
                message=str(error),
                payment_hash=payment_hash,
                recoverable=True,
                max_retries=3
            )
        elif "network" in error_msg or "connection" in error_msg:
            return LightningError(
                error_type=LightningErrorType.NETWORK_ERROR,
                message=str(error),
                payment_hash=payment_hash,
                recoverable=True,
                max_retries=5
            )
        elif "expired" in error_msg:
            return LightningError(
                error_type=LightningErrorType.INVOICE_EXPIRED,
                message=str(error),
                payment_hash=payment_hash,
                recoverable=False
            )
        elif "insufficient" in error_msg or "balance" in error_msg:
            return LightningError(
                error_type=LightningErrorType.INSUFFICIENT_BALANCE,
                message=str(error),
                payment_hash=payment_hash,
                recoverable=False
            )
        elif "channel" in error_msg:
            return LightningError(
                error_type=LightningErrorType.CHANNEL_ERROR,
                message=str(error),
                payment_hash=payment_hash,
                recoverable=True,
                max_retries=3
            )
        elif "payment" in error_msg and "failed" in error_msg:
            return LightningError(
                error_type=LightningErrorType.PAYMENT_FAILED,
                message=str(error),
                payment_hash=payment_hash,
                recoverable=True,
                max_retries=3
            )
        elif "timeout" in error_msg:
            return LightningError(
                error_type=LightningErrorType.TIMEOUT_ERROR,
                message=str(error),
                payment_hash=payment_hash,
                recoverable=True,
                max_retries=3
            )
        elif "validation" in error_msg or "invalid" in error_msg:
            return LightningError(
                error_type=LightningErrorType.VALIDATION_ERROR,
                message=str(error),
                payment_hash=payment_hash,
                recoverable=False
            )
        elif "rate limit" in error_msg:
            return LightningError(
                error_type=LightningErrorType.RATE_LIMIT_ERROR,
                message=str(error),
                payment_hash=payment_hash,
                recoverable=True,
                max_retries=1
            )
        else:
            return LightningError(
                error_type=LightningErrorType.UNKNOWN_ERROR,
                message=str(error),
                payment_hash=payment_hash,
                recoverable=False
            )

    def _record_error(self, error: LightningError):
        """Record error for statistics and circuit breaker"""
        self.error_history.append(error)

        # Update error counts
        if error.error_type not in self.error_counts:
            self.error_counts[error.error_type] = 0
        self.error_counts[error.error_type] += 1

        # Keep only recent errors (last hour)
        cutoff_time = datetime.now() - timedelta(hours=1)
        self.error_history = [e for e in self.error_history if e.timestamp > cutoff_time]

    def _check_circuit_breaker(self, error: LightningError):
        """Check if circuit breaker should be activated"""
        now = datetime.now()

        # Reset circuit breaker if timeout has passed
        if self.circuit_breaker_active and self.circuit_breaker_until and now > self.circuit_breaker_until:
            self.circuit_breaker_active = False
            self.circuit_breaker_until = None
            logger.info("Circuit breaker reset")

        # Check for consecutive errors of the same type
        recent_errors = [e for e in self.error_history
                        if e.error_type == error.error_type and
                        e.timestamp > now - timedelta(minutes=5)]

        if len(recent_errors) >= self.circuit_breaker_threshold:
            self.circuit_breaker_active = True
            self.circuit_breaker_until = now + timedelta(seconds=self.circuit_breaker_timeout)
            logger.warning(f"Circuit breaker activated for {error.error_type.value} until {self.circuit_breaker_until}")

    def should_retry(self, error: LightningError) -> bool:
        """Determine if operation should be retried"""
        if not error.recoverable:
            return False

        if error.retry_count >= error.max_retries:
            return False

        if self.circuit_breaker_active:
            return False

        return True

    def get_retry_delay(self, error: LightningError) -> float:
        """Get retry delay with exponential backoff"""
        base_delay = 1.0  # 1 second
        max_delay = 60.0  # 60 seconds

        delay = min(base_delay * (2 ** error.retry_count), max_delay)

        # Add jitter to avoid thundering herd
        import random
        jitter = random.uniform(0.1, 0.5)
        delay *= jitter

        return delay

    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics"""
        now = datetime.now()

        # Count errors by type in last hour
        recent_errors = [e for e in self.error_history if e.timestamp > now - timedelta(hours=1)]

        stats = {
            "total_errors_last_hour": len(recent_errors),
            "circuit_breaker_active": self.circuit_breaker_active,
            "circuit_breaker_until": self.circuit_breaker_until.isoformat() if self.circuit_breaker_until else None,
            "error_counts_by_type": {}
        }

        for error_type in LightningErrorType:
            count = len([e for e in recent_errors if e.error_type == error_type])
            if count > 0:
                stats["error_counts_by_type"][error_type.value] = count

        return stats

    def recover_from_error(self, error: LightningError, operation_func, *args, **kwargs) -> Any:
        """Attempt to recover from an error"""
        if not self.should_retry(error):
            raise Exception(f"Cannot recover from error: {error.message}")

        # Wait before retry
        delay = self.get_retry_delay(error)
        logger.info(f"Retrying operation in {delay:.2f}s (attempt {error.retry_count + 1}/{error.max_retries})")
        time.sleep(delay)

        # Increment retry count
        error.retry_count += 1

        try:
            result = operation_func(*args, **kwargs)
            logger.info(f"Operation recovered successfully after {error.retry_count} retries")
            return result
        except Exception as e:
            new_error = self.handle_error(e, {"payment_hash": error.payment_hash})
            new_error.retry_count = error.retry_count  # Preserve retry count
            return self.recover_from_error(new_error, operation_func, *args, **kwargs)


class LightningPaymentRecovery:
    """Specialized recovery for payment operations"""

    def __init__(self, error_handler: LightningErrorHandler):
        self.error_handler = error_handler

    def recover_payment(self, payment_hash: str, payment_func, *args, **kwargs) -> Any:
        """Recover from payment failures"""
        max_attempts = 3
        attempts = 0

        while attempts < max_attempts:
            try:
                attempts += 1
                logger.info(f"Payment attempt {attempts}/{max_attempts} for {payment_hash}")
                return payment_func(*args, **kwargs)

            except Exception as e:
                error = self.error_handler.handle_error(e, {"payment_hash": payment_hash})

                if not self.error_handler.should_retry(error):
                    raise Exception(f"Payment failed permanently: {error.message}")

                if attempts >= max_attempts:
                    raise Exception(f"Payment failed after {max_attempts} attempts: {error.message}")

                # Wait before retry
                delay = self.error_handler.get_retry_delay(error)
                logger.info(f"Retrying payment in {delay:.2f}s...")
                time.sleep(delay)

    def check_payment_status(self, payment_hash: str, check_func) -> Dict[str, Any]:
        """Check payment status with recovery"""
        try:
            return check_func(payment_hash)
        except Exception as e:
            error = self.error_handler.handle_error(e, {"payment_hash": payment_hash})

            # For status checks, we can return error status
            return {
                "payment_hash": payment_hash,
                "status": "error",
                "error": error.message,
                "error_type": error.error_type.value,
                "timestamp": datetime.now().isoformat()
            }


class LightningInvoiceRecovery:
    """Specialized recovery for invoice operations"""

    def __init__(self, error_handler: LightningErrorHandler):
        self.error_handler = error_handler

    def recover_invoice_creation(self, invoice_data: Dict[str, Any], create_func) -> Any:
        """Recover from invoice creation failures"""
        max_attempts = 3
        attempts = 0

        while attempts < max_attempts:
            try:
                attempts += 1
                logger.info(f"Invoice creation attempt {attempts}/{max_attempts}")
                return create_func(**invoice_data)

            except Exception as e:
                error = self.error_handler.handle_error(e)

                if not self.error_handler.should_retry(error):
                    raise Exception(f"Cannot create invoice: {error.message}")

                if attempts >= max_attempts:
                    raise Exception(f"Invoice creation failed after {max_attempts} attempts: {error.message}")

                # Wait before retry
                delay = self.error_handler.get_retry_delay(error)
                logger.info(f"Retrying invoice creation in {delay:.2f}s...")
                time.sleep(delay)

    def check_invoice_expiry(self, payment_hash: str, expiry_time: datetime) -> bool:
        """Check if invoice has expired"""
        return datetime.now() > expiry_time

    def handle_expired_invoice(self, payment_hash: str) -> Dict[str, Any]:
        """Handle expired invoice"""
        logger.warning(f"Invoice {payment_hash} has expired")

        error = LightningError(
            error_type=LightningErrorType.INVOICE_EXPIRED,
            message=f"Invoice {payment_hash} has expired",
            payment_hash=payment_hash,
            recoverable=False
        )

        self.error_handler._record_error(error)

        return {
            "payment_hash": payment_hash,
            "status": "expired",
            "error": "Invoice has expired",
            "timestamp": datetime.now().isoformat()
        }


# Global error handler instance
lightning_error_handler = LightningErrorHandler()
lightning_payment_recovery = LightningPaymentRecovery(lightning_error_handler)
lightning_invoice_recovery = LightningInvoiceRecovery(lightning_error_handler)