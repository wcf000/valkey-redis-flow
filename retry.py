"""
Retry and backoff utilities for Valkey client operations.
Follows best practices for async, exponential backoff, and idempotency.
"""
import asyncio
import functools
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

def async_retry(
    attempts: int = 3,
    delay: float = 0.1,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    logger: logging.Logger | None = None,
) -> Callable[[Callable[..., Coroutine[Any, Any, Any]]], Callable[..., Coroutine[Any, Any, Any]]]:
    """
    Decorator for async functions to retry with exponential backoff.
    """
    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            _attempts, _delay = attempts, delay
            last_exc = None
            for attempt in range(1, _attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if logger:
                        logger.warning(f"Attempt {attempt} failed: {exc}. Retrying in {_delay} seconds...")
                    await asyncio.sleep(_delay)
                    _delay *= backoff
            raise last_exc
        return wrapper
    return decorator
