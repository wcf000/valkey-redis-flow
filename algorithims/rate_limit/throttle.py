"""
* Throttle utility using VALKEY
* DRY, SOLID, CI/CD, and type safety best practices
"""
import logging
import time
from app.core.valkey_core.client import get_valkey_client

# ! Throttle: allow one event per interval
# todo: Add fail-open logic and Prometheus metrics if needed

async def is_allowed_throttle(
    key: str, interval: int
) -> bool:
    try:
        import time
        valkey_client = get_valkey_client()
        redis = await valkey_client.aconn()
        now = int(time.time())
        result = await redis.setnx(key, now)
        if result:
            await redis.expire(key, interval)
            return True
        return False
    except Exception as e:
        import logging
        logging.warning(f"[throttle] VALKEY unavailable, allowing event (fail-open): {e}")
        return True

    """
    * Throttle: allow only one event per interval
    Args:
        key (str): Unique identifier for the throttle (user ID, IP, etc.)
        interval (int): Interval in seconds
    Returns:
        bool: True if allowed, False if throttled
    """
