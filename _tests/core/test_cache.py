"""
Redis cache consistency tests
"""
import asyncio
import pytest

from app.core.valkey_core.cache.valkey_cache import ValkeyCache



@pytest.mark.asyncio
async def test_cache_invalidation(valkey_client):
    """Test cache invalidation works"""
    cache = ValkeyCache(valkey_client)
    await cache.set("test_key", "value", ttl=10)
    await cache.delete("test_key")
    assert await cache.get("test_key") is None  

@pytest.mark.asyncio
async def test_ttl_behavior(valkey_client):
    """Verify TTL expiration works"""
    cache = ValkeyCache(valkey_client)
    await cache.set("ttl_key", "value", ttl=1)
    assert await cache.get("ttl_key") == "value"
    await asyncio.sleep(1.1)
    assert await cache.get("ttl_key") is None

@pytest.mark.asyncio
async def test_race_conditions(valkey_client):
    """Test cache stampede protection"""
    cache = ValkeyCache(valkey_client)
    # * Use a real async function for value_fn
    async def value_fn():
        return "value"
    results = await asyncio.gather(
        *[cache.get_or_set("race_key", value_fn) for _ in range(10)]
    )
    assert all(r == "value" for r in results)
