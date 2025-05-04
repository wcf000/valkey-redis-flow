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
from typing import Any, Callable

from opentelemetry import trace

from app.core.valkey.client import client as valkey_client

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
    try:
        value = await valkey_client.get(key)
        if value is None:
            return default
        return value
    except Exception as e:
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
    try:
        return bool(await valkey_client.delete(key))
    except Exception as e:
        logger.warning(f"Error invalidating VALKEY cache: {str(e)}")
        return False

async def get_or_set_cache(key: str, func: Callable[[], Any], expire_seconds: int | None = None) -> Any:
    """
    Get a value from VALKEY, or compute and store it if not found.
    Args:
        key: The cache key to retrieve or store
        func: Function to call if the key is not in the cache
        expire_seconds: Optional cache expiration in seconds
    Returns:
        The cached or computed value
    """
    try:
        value = await valkey_client.get(key)
        if value is not None:
            return value
        result = func()
        await valkey_client.set(key, result, expire_seconds)
        return result
    except Exception as e:
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
