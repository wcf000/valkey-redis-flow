"""
Shared pytest fixtures and configuration for Valkey tests
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.valkey.client import client as valkey_client
from app.core.valkey.config import ValkeyConfig
from app.core.valkey.rate_limit import check_rate_limit
from app.core.valkey.valkey_cache import ValkeyCache


@pytest.fixture
def mock_valkey_client():
    """Mocked Valkey client instance with patched execute_command"""
    with patch('valkey.asyncio.cluster.ValkeyCluster'):
        client = valkey_client
        mock_execute = AsyncMock()
        client._client.execute_command = mock_execute
        yield client, mock_execute

@pytest.fixture
def valkey_cache():
    """Pre-configured ValkeyCache instance"""
    cache = ValkeyCache()
    yield cache
    # Cleanup any test data
    asyncio.run(cache.clear_namespace("test_"))


@pytest.fixture
def rate_limit_checker():
    """Rate limit checker function with default values"""

    async def checker(endpoint, identifier, limit=10, window=60):
        return await check_rate_limit(endpoint, identifier, limit, window)

    return checker


@pytest.fixture(autouse=True)
def reset_valkey_config():
    """Reset ValkeyConfig between tests"""
    original = ValkeyConfig.__dict__.copy()
    yield
    ValkeyConfig.__dict__.clear()
    ValkeyConfig.__dict__.update(original)


@pytest.fixture
def mock_time():
    """Mock time module for time-sensitive tests"""
    with patch("time.time") as mock_time:
        mock_time.return_value = 0
        yield mock_time
