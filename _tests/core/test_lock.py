"""
Tests for Valkey distributed lock functionality.
"""
import pytest

import pytest
import pytest_asyncio
from app.core.valkey_core.client import ValkeyClient
from valkey.exceptions import TimeoutError as ValkeyTimeoutError

@pytest_asyncio.fixture
async def valkey_client():
    # Disable metrics to avoid Prometheus duplicated timeseries errors in tests
    from app.core.valkey_core.config import ValkeyConfig
    old_metrics_enabled = ValkeyConfig.VALKEY_METRICS_ENABLED
    ValkeyConfig.VALKEY_METRICS_ENABLED = False
    client = ValkeyClient()
    await client.get_client()  # Ensures connection is established
    try:
        yield client
    finally:
        await client.shutdown()
        ValkeyConfig.VALKEY_METRICS_ENABLED = old_metrics_enabled


@pytest.mark.asyncio
async def test_valkey_lock_acquire_release(valkey_client):
    """Test acquiring and releasing a lock using ValkeyClient.lock."""
    async with valkey_client.lock("lock:test:acquire", timeout=2) as lock:
        # Lock should be held here
        assert lock is not None
    # After context, lock should be released (no error)

@pytest.mark.asyncio
async def test_valkey_lock_contention(valkey_client):
    """Test only one coroutine can acquire the same lock at a time."""
    acquired = False
    async with valkey_client.lock("lock:test:contend", timeout=2):
        with pytest.raises(ValkeyTimeoutError):
            async with valkey_client.lock("lock:test:contend", blocking_timeout=0.5):
                # Should not acquire
                assert False, "Should not acquire lock when already held"
        acquired = True
    assert acquired

@pytest.mark.asyncio
async def test_valkey_lock_nonblocking(valkey_client):
    """Test non-blocking lock acquisition returns immediately if lock is held."""
    async with valkey_client.lock("lock:test:nonblock", timeout=2):
        with pytest.raises(ValkeyTimeoutError):
            async with valkey_client.lock("lock:test:nonblock", blocking=False):
                assert False, "Should not acquire lock when already held"

@pytest.mark.asyncio
async def test_valkey_lock_released_after_context(valkey_client):
    """Test that lock is released after context exit."""
    key = "lock:test:release"
    async with valkey_client.lock(key, timeout=2):
        pass
    # After context, lock should be released (try to reacquire)
    async with valkey_client.lock(key, timeout=2):
        assert True
