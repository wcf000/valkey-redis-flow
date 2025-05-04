"""
VALKEY Cache Utilities

Core VALKEY functionality including:
- Connection management
- Basic caching operations
- Cache statistics
"""

import hashlib
import json
import logging
from collections.abc import Callable
from typing import Any

from opentelemetry import trace

from app.core.grafana.metrics import (
    record_valkey_cache_delete,
    record_valkey_cache_error,
    record_valkey_cache_hit,
    record_valkey_cache_miss,
    record_valkey_cache_set,
)
from app.core.prometheus.metrics import (
    VALKEY_CACHE_DELETES,
    VALKEY_CACHE_ERRORS,
    VALKEY_CACHE_HITS,
    VALKEY_CACHE_MISSES,
    VALKEY_CACHE_SETS,
)
from app.core.telemetry.client import TelemetryClient
from app.core.valkey.client import client as valkey_client

telemetry = TelemetryClient(service_name="valkey_cache")

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)


async def get_cached_result(key: str, default: Any = None) -> Any:
    """
    Get a result from the VALKEY cache.
    Args:
        key: The cache key to retrieve
        default: Value to return if key is not found or error occurs
    Returns:
        Cached value, or default if not found
    """
    # Trace cache get
    with telemetry.span_cache_operation("get", {"key": key}):
        try:
            value = await valkey_client.get(key)
            if value is None:
                VALKEY_CACHE_MISSES.inc()
                record_valkey_cache_miss()
                return default
            VALKEY_CACHE_HITS.inc()
            record_valkey_cache_hit()
            return value
        except Exception as e:
            # Record cache error
            VALKEY_CACHE_ERRORS.inc()
            record_valkey_cache_error()
            logger.warning(f"Error retrieving from VALKEY cache: {str(e)}")
            return default


async def invalidate_cache_key(key: str) -> bool:
    """
    Invalidate a specific cache key in VALKEY.
    Args:
        key: The cache key to invalidate
    Returns:
        True if the key was found and deleted, False otherwise
    """
    # Trace cache delete
    with telemetry.span_cache_operation("delete", {"key": key}):
        try:
            result = bool(await valkey_client.delete(key))
            if result:
                VALKEY_CACHE_DELETES.inc()
                record_valkey_cache_delete()
            else:
                VALKEY_CACHE_MISSES.inc()
                record_valkey_cache_miss()
            return result
        except Exception as e:
            # Record cache error
            VALKEY_CACHE_ERRORS.inc()
            record_valkey_cache_error()
            logger.warning(f"Error invalidating VALKEY cache: {str(e)}")
            return False


async def get_or_set_cache(
    key: str, func: Callable[[], Any], expire_seconds: int | None = None
) -> Any:
    """
    Get a value from VALKEY, or compute and store it if not found.
    Args:
        key: The cache key to retrieve or store
        func: Function to call if the key is not in the cache
        expire_seconds: Optional cache expiration in seconds
    Returns:
        The cached or computed value
    """
    # Trace get or set cache
    with telemetry.span_cache_operation("get_or_set", {"key": key}):
        try:
            value = await valkey_client.get(key)
            if value is not None:
                VALKEY_CACHE_HITS.inc()
                record_valkey_cache_hit()
                return value
            VALKEY_CACHE_MISSES.inc()
            record_valkey_cache_miss()
            result = func()
            await valkey_client.set(key, result, expire_seconds)
            VALKEY_CACHE_SETS.inc()
            record_valkey_cache_set()
            return result
        except Exception as e:
            # Record cache error
            VALKEY_CACHE_ERRORS.inc()
            record_valkey_cache_error()
            logger.error(f"Error computing or caching result in VALKEY: {str(e)}")
            raise


def cache_result(expire_seconds: int | None = None, key_prefix: str = ""):
    """
    Decorator that caches the result of a function based on its arguments using VALKEY.
    Args:
        expire_seconds: Optional cache expiration in seconds
        key_prefix: Optional prefix for the cache key
    Returns:
        Decorated function that uses VALKEY caching
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(*args, **kwargs):
            key_args = json.dumps(args, sort_keys=True, default=str)
            key_kwargs = json.dumps(kwargs, sort_keys=True, default=str)
            raw_key = f"{key_prefix}:{func.__name__}:{key_args}:{key_kwargs}"
            key = hashlib.md5(raw_key.encode()).hexdigest()
            value = await get_cached_result(key)
            if value is not None:
                return value
            result = await func(*args, **kwargs)
            await valkey_client.set(key, result, expire_seconds)
            return result

        return wrapper

    return decorator
