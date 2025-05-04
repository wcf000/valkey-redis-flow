"""
Tests for Valkey distributed lock functionality.
"""
import pytest
from app.core.valkey.lock import ValkeyLock
from app.core.valkey.client import client as valkey_client

@pytest.mark.asyncio
async def test_lock_acquire_release():
    """Test acquiring and releasing a lock."""
    client = await valkey_client.get_client()
    lock = ValkeyLock(client, "lock:test", ttl=3)
    acquired = await lock.acquire()
    assert acquired is True
    released = await lock.release()
    assert released is True

@pytest.mark.asyncio
async def test_lock_context_manager():
    """Test lock context manager usage."""
    client = await valkey_client.get_client()
    async with ValkeyLock(client, "lock:ctx", ttl=2) as lock:
        assert await client.exists(lock.key)
    # After context, lock should be released
    assert not await client.exists("lock:ctx")

@pytest.mark.asyncio
async def test_lock_contention():
    """Test lock contention: only one lock can be acquired at a time."""
    client = await valkey_client.get_client()
    lock1 = ValkeyLock(client, "lock:contend", ttl=3)
    lock2 = ValkeyLock(client, "lock:contend", ttl=3)
    acquired1 = await lock1.acquire()
    acquired2 = await lock2.acquire()
    assert acquired1 is True
    assert acquired2 is False
    await lock1.release()
    await lock2.release()
