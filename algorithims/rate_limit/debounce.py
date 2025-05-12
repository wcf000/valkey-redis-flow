"""
* Debounce utility using Redis
* DRY, SOLID, CI/CD, and type safety best practices
"""
import logging
import time
from app.core.valkey_core.client import get_valkey_client

# ! Debounce: only allow event after interval of inactivity
# todo: Add fail-open logic and Prometheus metrics if needed


async def is_allowed_debounce(key: str, interval: int) -> bool:
    """
    * Debounce: only allow event after interval of inactivity
    Args:
        key (str): Unique identifier for the debounce (user ID, IP, etc.)
        interval (int): Inactivity interval in seconds
    Returns:
        bool: True if allowed, False if debounced
    """
    import time
    try:
        valkey_client = get_valkey_client()
        redis = await valkey_client.aconn()
        now = int(time.time())
        ttl = await redis.ttl(key)
        if ttl > 0:
            return False
        await redis.set(key, now, ex=interval)
        return True
    except Exception as e:
        # ! Fail-open: If VALKEY is unavailable, allow the event and log a warning
        logging.warning(f"[debounce] VALKEY unavailable, allowing event (fail-open): {e}")
        return True

# todo: Add Prometheus metrics for debounce events
