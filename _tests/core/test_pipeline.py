"""
Tests for Valkey pipeline functionality.
"""
import pytest
from app.core.valkey_core.client import client as valkey_client

@pytest.mark.asyncio
async def test_pipeline_basic():
    """Test basic pipeline set/get operations."""
    client = valkey_client
    pipeline = await client.pipeline()
    await pipeline.set("pipeline_key1", "v1")
    await pipeline.set("pipeline_key2", "v2")
    await pipeline.execute()
    val1 = await client.get("pipeline_key1")
    val2 = await client.get("pipeline_key2")
    assert val1 == "v1"
    assert val2 == "v2"

@pytest.mark.asyncio
async def test_pipeline_atomicity():
    """Test that pipeline operations are atomic and all-or-nothing."""
    client = valkey_client
    pipeline = await client.pipeline()
    await pipeline.set("atomic_key1", "a1")
    await pipeline.set("atomic_key2", "a2")
    await pipeline.execute()
    await client.delete("atomic_key1", "atomic_key2")
    pipeline = await client.pipeline()
    await pipeline.set("atomic_key1", "b1")
    await pipeline.set("atomic_key2", "b2")
    await pipeline.execute()
    val1 = await client.get("atomic_key1")
    val2 = await client.get("atomic_key2")
    assert val1 == "b1"
    assert val2 == "b2"
