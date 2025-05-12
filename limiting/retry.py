"""
Async retry decorator for resilient Valkey operations.
Follows best practices: type safety, exponential backoff, custom exceptions, and DRY/SOLID principles.
"""
from typing import Callable, Awaitable, TypeVar, ParamSpec
import asyncio
import functools

T = TypeVar("T")
P = ParamSpec("P")

# * Async retry decorator factory
def async_retry(
    attempts: int = 3,
    delay: float = 0.1,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    backoff: float = 1.0,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        attempts (int): Number of attempts before giving up.
        delay (float): Initial delay between attempts (seconds).
        exceptions (tuple): Exception types to retry on.
        backoff (float): Backoff multiplier (e.g., 2.0 doubles delay each retry).
    """
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exc: Exception | None = None
            cur_delay = delay
            for attempt in range(1, attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == attempts:
                        # ! Max attempts reached, re-raise
                        raise
                    # * Exponential backoff
                    await asyncio.sleep(cur_delay)
                    cur_delay *= backoff
        return wrapper
    return decorator

# todo: Add a RetryConfig (Pydantic) if config-driven retries are needed
# todo: Add metrics/logging hooks for observability if required
