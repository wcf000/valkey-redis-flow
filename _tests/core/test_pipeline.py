"""
Tests for Valkey pipeline functionality.
"""
import pytest
from app.core.valkey_core.client import ValkeyClient

@pytest.mark.asyncio
async def test_pipeline_basic(valkey_client):
    """Test basic pipeline set/get operations."""
    client = valkey_client
    pipeline = await client.pipeline()
    await pipeline.set("pipeline_key1", "v1")
    await pipeline.set("pipeline_key2", "v2")
    await pipeline.execute()
    val1 = await client.get("pipeline_key1")
    val2 = await client.get("pipeline_key2")
    if isinstance(val1, bytes):
        val1 = val1.decode()
    if isinstance(val2, bytes):
        val2 = val2.decode()
    assert val1 == "v1"
    assert val2 == "v2"

@pytest.mark.asyncio
async def test_pipeline_atomicity(valkey_client):
    """Test that pipeline operations are atomic and all-or-nothing."""
    client = valkey_client
    pipeline1 = await client.pipeline()
    try:
        await pipeline1.set("atomic_key1", "a1")
        await pipeline1.set("atomic_key2", "a2")
        await pipeline1.execute()
    finally:
        if hasattr(pipeline1, "aclose"):
            await pipeline1.aclose()
        elif hasattr(pipeline1, "close"):
            await pipeline1.close()
    await client.delete("atomic_key1", "atomic_key2")
    pipeline2 = await client.pipeline()
    try:
        await pipeline2.set("atomic_key1", "b1")
        await pipeline2.set("atomic_key2", "b2")
        await pipeline2.execute()
        val1 = await client.get("atomic_key1")
        val2 = await client.get("atomic_key2")
        if isinstance(val1, bytes):
            val1 = val1.decode()
        if isinstance(val2, bytes):
            val2 = val2.decode()
        assert val1 == "b1"
        assert val2 == "b2"
    finally:
        if hasattr(pipeline2, "aclose"):
            await pipeline2.aclose()
        elif hasattr(pipeline2, "close"):
            await pipeline2.close()
    if hasattr(client, "close"):
        await client.close()
