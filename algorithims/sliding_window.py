"""
* Sliding Window Rate Limiter using VALKEY
* DRY, SOLID, CI/CD, and type safety best practices
"""
import logging
import time
from app.core.valkey_core.client import client as valkey_client

# ! Uses VALKEY sorted sets for timestamped requests

async def is_allowed_sliding_window(
    key: str, limit: int, window: int
) -> bool:  
    """
    * Sliding Window Rate Limiter (DI version)
    Args:
        key (str): Unique identifier for the rate limit (user ID, IP, etc.)
        limit (int): Max allowed requests per window
        window (int): Window size in seconds
    Returns:
        bool: True if allowed, False if rate limited
    """
    import time
    try:
        now = int(time.time())
        min_score = now - window
        p = valkey_client.pipeline()
        p.zremrangebyscore(key, 0, min_score)
        p.zadd(key, {str(now): now})
        p.zcard(key)
        p.expire(key, window)
        _, _, count, _ = await p.execute()
        return count <= limit
    except Exception as e:
        import logging
        logging.warning(f"[sliding_window] VALKEY unavailable, allowing event (fail-open): {e}")
        return True

