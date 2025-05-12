"""
* Fixed Window Rate Limiter using VALKEY
* DRY, SOLID, CI/CD, and type safety best practices
"""
import logging

from app.core.valkey_core.client import client as valkey_client

# ! This implementation assumes VALKEY is healthy and available.
# todo: Add fail-open logic and Prometheus metrics if needed

async def is_allowed_fixed_window(
    key: str, limit: int, window: int
) -> bool:
    """
    * Fixed Window Rate Limiter (DI version)    
    Args:
        key (str): Injected RedisCache instance
        key (str): Unique identifier for the rate limit (user ID, IP, etc.)
        limit (int): Max allowed requests per window
        window (int): Window size in seconds
    Returns:
        bool: True if allowed, False if rate limited
    """
    try:
        count = await valkey_client.incr(key)
        if count == 1:
            await valkey_client.expire(key, window)
        return count <= limit
    except Exception as e:
        # ! Fail-open: If VALKEY is unavailable, allow the event and log a warning
        import logging
        logging.warning(f"[fixed_window] Redis unavailable, allowing event (fail-open): {e}")
        return True
