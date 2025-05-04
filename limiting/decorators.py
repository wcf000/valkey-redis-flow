"""
valkey/limiting/decorators.py

Reusable decorators for advanced rate limiting using Redis/Valkey.
Import these decorators in your worker/task modules for consistent rate limiting.
"""

import functools
import logging
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, status

from .rate_limit import (
    RATE_LIMIT_GAUGE,
    RATE_LIMIT_REQUESTS,
    check_rate_limit,
)

logger = logging.getLogger("app.core.valkey.limiting.decorators")


def _resolve_key(req: Any, key_type: str, endpoint: str) -> str:
    """
    Helper to resolve the rate limiting key based on type.
    """
    if key_type == "user":
        return getattr(req, "user_id", None) or endpoint
    elif key_type == "ip":
        return getattr(req, "client_ip", None) or endpoint
    elif key_type == "custom":
        return getattr(req, "rate_limit_key", None) or endpoint
    return endpoint  # default: service-level


def rate_limit_decorator(
    limit: int = 100,
    window: int = 60,
    endpoint: str = "worker",
    key_type: str = "service",  # "service", "user", "ip", "custom"
    raise_http: bool = True,
    http_status: int = status.HTTP_429_TOO_MANY_REQUESTS,
    http_detail: str | None = None,
):
    """
    General-purpose async rate limiting decorator.
    Args:
        limit: Max requests per window.
        window: Time window in seconds.
        endpoint: Logical endpoint name.
        key_type: "service", "user", "ip", or "custom".
        raise_http: If True, raises HTTPException on limit (for FastAPI).
        http_status: HTTP status code for exception.
        http_detail: Custom error message.
    """
    def decorator(func: Callable[..., Any]):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            req = kwargs.get("request")
            key = _resolve_key(req, key_type, endpoint)
            RATE_LIMIT_GAUGE.labels(endpoint=endpoint).inc()
            try:
                rate_key = f"{key_type}_rate:{key}"
                if await check_rate_limit(rate_key, limit=limit, window=window):
                    logger.warning(
                        "Rate limit exceeded",
                        extra={"key": key, "endpoint": endpoint, "limit": limit, "type": key_type},
                    )
                    RATE_LIMIT_REQUESTS.labels(endpoint=endpoint, status="limited").inc()
                    if raise_http:
                        raise HTTPException(
                            status_code=http_status,
                            detail=http_detail or f"Rate limit exceeded for {key} on {endpoint}",
                        )
                    raise Exception(f"Rate limit exceeded for {key} on {endpoint}")
                RATE_LIMIT_REQUESTS.labels(endpoint=endpoint, status="ok").inc()
                return await func(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Error in rate_limit_decorator: {e}")
                raise
        return wrapper
    return decorator

# Example aliases for common use cases:
user_rate_limit = functools.partial(rate_limit_decorator, key_type="user")
ip_rate_limit = functools.partial(rate_limit_decorator, key_type="ip")
service_rate_limit = functools.partial(rate_limit_decorator, key_type="service")
custom_rate_limit = functools.partial(rate_limit_decorator, key_type="custom")
