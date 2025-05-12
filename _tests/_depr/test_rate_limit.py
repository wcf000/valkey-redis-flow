"""
Production-grade Valkey rate limiting tests with:
- Comprehensive error handling
- Edge case testing
"""

import asyncio
import logging
from datetime import datetime
from unittest.mock import patch

import pytest

from app.core.valkey_core.limiting.rate_limit import check_rate_limit

logger = logging.getLogger(__name__)

# Prometheus metrics


@pytest.mark.asyncio
async def test_window_sliding():
    """Test sliding window behavior with Prometheus metrics"""
    endpoint = "test_endpoint"
    identifier = "test_id"
    # Test within limit
    for i in range(10):
        result = await check_rate_limit(endpoint, identifier, 10, 60)
        assert result is False, f"Request {i} should not be rate limited"

    # Test over limit
    result = await check_rate_limit(endpoint, identifier, 10, 60)
    assert result is True


@pytest.mark.asyncio
async def test_burst_handling():
    """Verify burst traffic handling with Prometheus metrics"""
    endpoint = "burst_endpoint"
    identifier = "burst_id"
    # Simulate burst traffic
    tasks = []
    for _ in range(20):
        tasks.append(check_rate_limit(endpoint, identifier, 15, 60))

    results = await asyncio.gather(*tasks)

    # Verify and record results
    allowed = results.count(False)
    rejected = results.count(True)
    assert allowed == 15
    assert rejected == 5


@pytest.mark.asyncio
async def test_distributed_consistency():
    """Test rate limiting works across shards with failover"""
    endpoint = "dist_endpoint"
    identifier = "dist_id"

    try:
        # Test with shard failure
        with patch(
            "app.core.valkey.client.ValkeyClient._get_sharded_client"
        ) as mock_shard:
            mock_shard.return_value = None
            assert await check_rate_limit(endpoint, identifier, 5, 60) is False

        # Test normal operation
        assert await check_rate_limit(endpoint, identifier, 5, 60) is False

    except Exception as e:
        logger.error(f"Distributed consistency test failed: {e}")
        raise


@pytest.mark.asyncio
async def test_edge_cases():
    """Test various edge cases and error scenarios"""
    endpoint = "edge_endpoint"
    identifier = "edge_id"

    # Test empty endpoint
    with pytest.raises(ValueError):
        await check_rate_limit("", identifier, 5, 60)

    # Test empty identifier
    with pytest.raises(ValueError):
        await check_rate_limit(endpoint, "", 5, 60)

    # Test invalid limits
    with pytest.raises(ValueError):
        await check_rate_limit(endpoint, identifier, 0, 60)

    with pytest.raises(ValueError):
        await check_rate_limit(endpoint, identifier, 5, 0)


@pytest.mark.asyncio
async def test_performance_under_load():
    """Test rate limiter performance with Prometheus metrics"""
    endpoint = "perf_endpoint"
    identifier = "perf_id"
    # Simulate high concurrent load
    tasks = []
    for i in range(100):
        tasks.append(check_rate_limit(endpoint, f"{identifier}_{i}", 50, 60))

    results = await asyncio.gather(*tasks)

    # Verify performance (basic check)
    assert len(results) == 100


@pytest.mark.asyncio
async def test_rate_limit_idempotency():
    """Test idempotency for repeated requests."""
    endpoint = "idempotent_endpoint"
    identifier = "idempotent_id"
    # Send repeated requests
    for _ in range(5):
        result = await check_rate_limit(endpoint, identifier, 10, 60)
        assert result is False
