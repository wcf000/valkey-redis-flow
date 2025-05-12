"""
* Fixed Window Rate Limiter using VALKEY
* DRY, SOLID, CI/CD, and type safety best practices
"""
import logging

from app.core.valkey_core.client import get_valkey_client

# ! This implementation assumes VALKEY is healthy and available.
# todo: Add fail-open logic and Prometheus metrics if needed

async def is_allowed_fixed_window(
    key: str, limit: int, window: int
) -> bool:
    try:
        valkey_client = get_valkey_client()
        redis = await valkey_client.aconn()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window)
        return count <= limit
    except Exception as e:
        import logging
        logging.warning(f"[fixed_window] VALKEY unavailable, allowing event (fail-open): {e}")
        return True

    """
    * Fixed Window Rate Limiter (DI version)
    Args:
        key (str): Unique identifier for the rate limit (user ID, IP, etc.)
        limit (int): Max allowed requests per window
        window (int): Window size in seconds
    Returns:
        bool: True if allowed, False if rate limited
    """
