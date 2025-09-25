"""
Retry helpers for transient operations (HTTP calls, polling, etc.).

- with_retry(fn, ...): execute a callable with exponential backoff + jitter
- retry(exceptions=..., ...): decorator form to auto-retry a function

Design goals:
- Keep API minimal and dependency-free
- Let callers provide on_retry hooks for logging
"""
from __future__ import annotations

import random
import time
from typing import Any, Callable, Optional, Tuple, Type, TypeVar

from .errors import RetryExceededError

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    max_attempts: int = 5,
    backoff_base: float = 0.2,
    backoff_factor: float = 2.0,
    jitter: float = 0.1,
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
) -> T:
    """
    Execute fn() with retries on specified exceptions using exponential backoff + jitter.

    on_retry receives (attempt_index, exception, sleep_seconds) before sleeping.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except exceptions as e:  # type: ignore[misc]
            attempt += 1
            if attempt >= max_attempts:
                raise RetryExceededError(f"retry attempts exceeded ({max_attempts})") from e
            sleep_s = backoff_base * (backoff_factor ** (attempt - 1))
            sleep_s += random.uniform(0, jitter)
            if on_retry is not None:
                try:
                    on_retry(attempt, e, sleep_s)
                except Exception:
                    pass
            time.sleep(sleep_s)


def retry(
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    max_attempts: int = 5,
    backoff_base: float = 0.2,
    backoff_factor: float = 2.0,
    jitter: float = 0.1,
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
):
    """Decorator to retry synchronous functions on failure."""

    def _decorator(fn: Callable[..., T]) -> Callable[..., T]:
        def _wrapped(*args: Any, **kwargs: Any) -> T:
            return with_retry(
                lambda: fn(*args, **kwargs),
                exceptions=exceptions,
                max_attempts=max_attempts,
                backoff_base=backoff_base,
                backoff_factor=backoff_factor,
                jitter=jitter,
                on_retry=on_retry,
            )

        return _wrapped

    return _decorator
