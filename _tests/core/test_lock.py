"""
Tests for Valkey distributed lock functionality.
"""
import pytest

from app.core.valkey.client import client as valkey_client


@pytest.mark.asyncio
async def test_valkey_lock_acquire_release():
    """Test acquiring and releasing a lock using ValkeyClient.lock."""
    async with valkey_client.lock("lock:test:acquire", timeout=2) as lock:
        # Lock should be held here
        assert lock is not None
    # After context, lock should be released (no error)

@pytest.mark.asyncio
async def test_valkey_lock_contention():
    """Test only one coroutine can acquire the same lock at a time."""
    acquired = False
    async with valkey_client.lock("lock:test:contend", timeout=2):
        # Try to acquire the same lock in another coroutine (should block/fail)
        async def try_acquire():
            try:
                async with valkey_client.lock("lock:test:contend", blocking_timeout=0.5):
                    return True
            except TimeoutError:
                return False
        result = await try_acquire()
        assert result is False
        acquired = True
    assert acquired

@pytest.mark.asyncio
async def test_valkey_lock_nonblocking():
    """Test non-blocking lock acquisition returns immediately if lock is held."""
    async with valkey_client.lock("lock:test:nonblock", timeout=2):
        try:
            async with valkey_client.lock("lock:test:nonblock", blocking=False):
                raise AssertionError("Should not acquire lock when already held")
        except TimeoutError:
            pass

@pytest.mark.asyncio
async def test_valkey_lock_released_after_context():
    """Test that lock is released after context exit."""
    key = "lock:test:release"
    async with valkey_client.lock(key, timeout=2):
        pass
    # After context, lock should be released (try to reacquire)
    async with valkey_client.lock(key, timeout=2):
        assert True
