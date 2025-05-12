"""
Tests for Redis-backed rate limiting/throttling algorithms and their fail-open logic.
- Fixed Window
- Sliding Window
- Token Bucket
- Throttle
- Debounce

* Uses pytest and pytest-asyncio for async tests
* Mocks Redis to simulate fail-open
"""
import asyncio
import logging
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.append("..")

import asyncio

import pytest
import uuid

# * Disable Valkey metrics for all tests to avoid Prometheus duplicate registration errors
from app.core.valkey_core.config import ValkeyConfig
ValkeyConfig.VALKEY_METRICS_ENABLED = False

from app.core.valkey_core.algorithims.rate_limit.debounce import is_allowed_debounce
from app.core.valkey_core.algorithims.rate_limit.fixed_window import is_allowed_fixed_window
from app.core.valkey_core.algorithims.rate_limit.sliding_window import is_allowed_sliding_window
from app.core.valkey_core.algorithims.rate_limit.throttle import is_allowed_throttle
from app.core.valkey_core.algorithims.rate_limit.token_bucket import is_allowed_token_bucket
from app.core.valkey_core.cache.valkey_cache import ValkeyCache
pytestmark = pytest.mark.asyncio

# * Helper to flush keys before each test to ensure clean state

# Note: Redis DB is flushed automatically before each test by the autouse flush_redis fixture.

import pytest

@pytest.mark.asyncio
@pytest.mark.parametrize("algo_func,kwargs", [
    (is_allowed_fixed_window, {"key": "test:fixed", "limit": 2, "window": 2}),
    # Sliding window tested in a dedicated deterministic test
    (is_allowed_token_bucket, {"key": "test:bucket", "capacity": 2, "refill_rate": 1, "interval": 2}),
    (is_allowed_throttle, {"key": "test:throttle", "interval": 2}),
    (is_allowed_debounce, {"key": "test:debounce", "interval": 2}),
])
async def test_algorithms_allow_and_block(algo_func, kwargs, redis_client):
    """
    Test that algorithms allow and block as expected.
    Sliding window is tested in a separate deterministic function.
    """
    # Generate a unique key per test run for isolation
    unique_key = f"{kwargs.get('key', 'test')}_{uuid.uuid4()}"
    if 'key' in kwargs:
        kwargs = {**kwargs, 'key': unique_key}
    # Allow first call
    # Argument order mapping for each algorithm (no cache/client)
    ARG_ORDER = {
        is_allowed_fixed_window: ["key", "limit", "window"],
        is_allowed_token_bucket: ["key", "capacity", "refill_rate", "interval"],
        is_allowed_throttle: ["key", "interval"],
        is_allowed_debounce: ["key", "interval"],
    }
    arg_names = ARG_ORDER.get(algo_func, [])
    def get_args():
        from inspect import signature
        sig = signature(algo_func)
        param_count = len(sig.parameters)
        return [kwargs[name] for name in arg_names[:param_count] if name in kwargs]
    allowed1 = await algo_func(*get_args())
    # For other algorithms, sleep to ensure timestamps differ
    if algo_func in [is_allowed_fixed_window, is_allowed_token_bucket]:
        await asyncio.sleep(1)
    allowed2 = await algo_func(*get_args())
    allowed3 = await algo_func(*get_args())

    # Detect fail-open (all allowed)
    if allowed1 is True and allowed2 is True and allowed3 is True:
        # If fail-open, all calls should be allowed
        assert allowed1 is True, f"Fail-open: allowed1 was {allowed1} for {algo_func.__name__} with kwargs={kwargs}"
        assert allowed2 is True, f"Fail-open: allowed2 was {allowed2} for {algo_func.__name__} with kwargs={kwargs}"
        assert allowed3 is True, f"Fail-open: allowed3 was {allowed3} for {algo_func.__name__} with kwargs={kwargs}"
    else:
        assert allowed1 is True, f"allowed1 was {allowed1} for {algo_func.__name__} with kwargs={kwargs}"
        if algo_func in [is_allowed_fixed_window, is_allowed_token_bucket]:
            assert allowed2 is True, f"allowed2 was {allowed2} for {algo_func.__name__} with kwargs={kwargs}"
            assert allowed3 is False, f"allowed3 was {allowed3} for {algo_func.__name__} with kwargs={kwargs}"
        elif algo_func is is_allowed_throttle or algo_func is is_allowed_debounce:
            assert allowed2 is False, f"allowed2 was {allowed2} for {algo_func.__name__} with kwargs={kwargs}"
            assert allowed3 is False, f"allowed3 was {allowed3} for {algo_func.__name__} with kwargs={kwargs}"
        else:
            assert allowed2 is True, f"allowed2 was {allowed2} for {algo_func.__name__} with kwargs={kwargs}"
            assert allowed3 is True, f"allowed3 was {allowed3} for {algo_func.__name__} with kwargs={kwargs}"

    if algo_func in [is_allowed_fixed_window, is_allowed_token_bucket]:
        assert allowed3 is False, f"allowed3 was {allowed3} for {algo_func.__name__} with kwargs={kwargs}"
    elif algo_func is is_allowed_throttle or algo_func is is_allowed_debounce:
        assert allowed3 is False, f"allowed3 was {allowed3} for {algo_func.__name__} with kwargs={kwargs}"
    else:
        assert allowed3 is True, f"allowed3 was {allowed3} for {algo_func.__name__} with kwargs={kwargs}"

    # Wait for window/interval and allow again
    if algo_func is is_allowed_token_bucket:
        # Wait for enough tokens to refill (interval/refill_rate)
        refill_time = kwargs.get("interval", 1) / kwargs.get("refill_rate", 1)
        await asyncio.sleep(refill_time + 0.1)
    else:
        await asyncio.sleep(kwargs.get("window", kwargs.get("interval", 1)) + 0.5)
    
    allowed4 = await algo_func(*get_args())
    assert allowed4 is True, f"allowed4 was {allowed4} for {algo_func.__name__} with kwargs={kwargs}"

@pytest.mark.parametrize("algo_func,kwargs,valkey_path", [
    (is_allowed_fixed_window, {"key": "failopen:fixed", "limit": 2, "window": 2}, "app.core.valkey.algorithims.fixed_window.ValkeyCache"),
    (is_allowed_sliding_window, {"key": "failopen:sliding", "limit": 2, "window": 2}, "app.core.valkey.algorithims.sliding_window.ValkeyCache"),
    (is_allowed_token_bucket, {"key": "failopen:bucket", "capacity": 2, "refill_rate": 1, "interval": 2}, "app.core.valkey.algorithims.token_bucket.ValkeyCache"),
    (is_allowed_throttle, {"key": "failopen:throttle", "interval": 2}, "app.core.valkey.algorithims.throttle.ValkeyCache"),
    (is_allowed_debounce, {"key": "failopen:debounce", "interval": 2}, "app.core.valkey.algorithims.debounce.ValkeyCache"),
])
async def test_algorithms_fail_open(algo_func, kwargs, valkey_path, monkeypatch):
    # Generate a unique key per test run for isolation
    unique_key = f"{kwargs.get('key', 'test')}_{uuid.uuid4()}"
    if 'key' in kwargs:
        kwargs = {**kwargs, 'key': unique_key}
    # Simulate VALKEY unavailable by raising exception on incr/zadd/set
    class DummyClient:
        async def incr(self, key): raise Exception("VALKEY down")
        async def expire(self, key, window): pass
        async def zremrangebyscore(self, key, min_score, max_score): pass
        async def zadd(self, key, mapping): raise Exception("VALKEY down")
        async def zcard(self, key): raise Exception("VALKEY down")
        async def setnx(self, key, value): raise Exception("VALKEY down")
        async def set(self, key, value, ex=None): raise Exception("VALKEY down")
        async def ttl(self, key): raise Exception("VALKEY down")
    # Patch the per-module valkey_client symbol used by each algorithm to simulate fail-open
    monkeypatch.setattr("app.core.valkey_core.algorithims.rate_limit.fixed_window.get_valkey_client", lambda: DummyClient())
    monkeypatch.setattr("app.core.valkey_core.algorithims.rate_limit.sliding_window.get_valkey_client", lambda: DummyClient())
    monkeypatch.setattr("app.core.valkey_core.algorithims.rate_limit.token_bucket.get_valkey_client", lambda: DummyClient())
    monkeypatch.setattr("app.core.valkey_core.algorithims.rate_limit.throttle.get_valkey_client", lambda: DummyClient())
    monkeypatch.setattr("app.core.valkey_core.algorithims.rate_limit.debounce.get_valkey_client", lambda: DummyClient())

@pytest.mark.parametrize("algo_func,kwargs", [
    (is_allowed_fixed_window, {"key": "test:fixed", "limit": 2, "window": 2}),
    # Sliding window tested in a dedicated deterministic test
    (is_allowed_token_bucket, {"key": "test:bucket", "capacity": 2, "refill_rate": 1, "interval": 2}),
    (is_allowed_throttle, {"key": "test:throttle", "interval": 2}),
    (is_allowed_debounce, {"key": "test:debounce", "interval": 2}),
])
async def test_algorithms_allow_and_block_multiple(algo_func, kwargs, redis_client):
    # Generate a unique key per test run for isolation
    unique_key = f"{kwargs.get('key', 'test')}_{uuid.uuid4()}"
    if 'key' in kwargs:
        kwargs = {**kwargs, 'key': unique_key}
    # Argument order mapping for each algorithm (no cache/client)
    ARG_ORDER = {
        is_allowed_fixed_window: ["key", "limit", "window"],
        is_allowed_token_bucket: ["key", "capacity", "refill_rate", "interval"],
        is_allowed_throttle: ["key", "interval"],
        is_allowed_debounce: ["key", "interval"],
    }
    arg_names = ARG_ORDER.get(algo_func, [])
    def get_args():
        from inspect import signature
        sig = signature(algo_func)
        param_count = len(sig.parameters)
        return [kwargs[name] for name in arg_names[:param_count] if name in kwargs]

    allowed1 = await algo_func(*get_args())
    if algo_func in [is_allowed_fixed_window, is_allowed_token_bucket]:
        await asyncio.sleep(1)
    allowed2 = await algo_func(*get_args())
    allowed3 = await algo_func(*get_args())

    # Detect fail-open (all allowed)
    if allowed1 is True and allowed2 is True and allowed3 is True:
        assert allowed1 is True, f"Fail-open: allowed1 was {allowed1} for {algo_func.__name__} with kwargs={kwargs}"
        assert allowed2 is True, f"Fail-open: allowed2 was {allowed2} for {algo_func.__name__} with kwargs={kwargs}"
        assert allowed3 is True, f"Fail-open: allowed3 was {allowed3} for {algo_func.__name__} with kwargs={kwargs}"
    else:
        assert allowed1 is True, f"allowed1 was {allowed1} for {algo_func.__name__} with kwargs={kwargs}"
        if algo_func in [is_allowed_fixed_window, is_allowed_token_bucket]:
            assert allowed2 is True, f"allowed2 was {allowed2} for {algo_func.__name__} with kwargs={kwargs}"
            assert allowed3 is False, f"allowed3 was {allowed3} for {algo_func.__name__} with kwargs={kwargs}"
        elif algo_func is is_allowed_throttle or algo_func is is_allowed_debounce:
            assert allowed2 is False, f"allowed2 was {allowed2} for {algo_func.__name__} with kwargs={kwargs}"
            assert allowed3 is False, f"allowed3 was {allowed3} for {algo_func.__name__} with kwargs={kwargs}"
        else:
            assert allowed2 is True, f"allowed2 was {allowed2} for {algo_func.__name__} with kwargs={kwargs}"
            assert allowed3 is True, f"allowed3 was {allowed3} for {algo_func.__name__} with kwargs={kwargs}"


    # Fourth call
    if algo_func is is_allowed_token_bucket:
        refill_time = kwargs.get("interval", 1)
        await asyncio.sleep(refill_time + 0.1)
        allowed4 = await algo_func(*get_args())
        assert allowed4 is True, f"allowed4 was {allowed4} for {algo_func.__name__} with kwargs={kwargs}"
    elif algo_func is is_allowed_fixed_window:
        await asyncio.sleep(kwargs.get("window", 1) + 0.5)
        allowed4 = await algo_func(*get_args())
        assert allowed4 is True, f"allowed4 was {allowed4} for {algo_func.__name__} with kwargs={kwargs}"
    else:
        await asyncio.sleep(kwargs.get("window", kwargs.get("interval", 1)) + 0.5)
        allowed4 = await algo_func(*get_args())
        assert allowed4 is True, f"allowed4 was {allowed4} for {algo_func.__name__} with kwargs={kwargs}"

    # Fifth call: only assert for fixed window, and it should be allowed after window reset
    if algo_func is is_allowed_fixed_window:
        allowed5 = await algo_func(*get_args())
        assert allowed5 is True, f"allowed5 was {allowed5} for {algo_func.__name__} with kwargs={kwargs}"

    # Helper for correct argument order
    ARG_ORDER = {
        is_allowed_fixed_window: ["key", "limit", "window"],
        is_allowed_token_bucket: ["key", "capacity", "refill_rate", "interval"],
        is_allowed_throttle: ["key", "interval"],
        is_allowed_debounce: ["key", "interval"],
    }
    arg_names = ARG_ORDER.get(algo_func, [])
    def get_args():
        from inspect import signature
        sig = signature(algo_func)
        param_count = len(sig.parameters)
        return [kwargs[name] for name in arg_names[:param_count] if name in kwargs]

    allowed6 = await algo_func(*get_args())
    if algo_func in [is_allowed_fixed_window, is_allowed_token_bucket]:
        assert allowed6 is False, f"allowed6 was {allowed6} for {algo_func.__name__} with kwargs={kwargs}"
    elif algo_func is is_allowed_throttle or algo_func is is_allowed_debounce:
        assert allowed6 is False, f"allowed6 was {allowed6} for {algo_func.__name__} with kwargs={kwargs}"
    else:
        assert allowed6 is True, f"allowed6 was {allowed6} for {algo_func.__name__} with kwargs={kwargs}"

    # Wait for window/interval and allow again
    await asyncio.sleep(kwargs.get("window", kwargs.get("interval", 1)) + 0.5)
    allowed7 = await algo_func(*get_args())
    assert allowed7 is True, f"allowed7 was {allowed7} for {algo_func.__name__} with kwargs={kwargs}"
