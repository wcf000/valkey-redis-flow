"""
Shared pytest fixtures and configuration for Valkey tests
"""

import asyncio

# If you have a ValkeyCache or similar, import here
# from app.core.valkey.cache.valkey_cache import ValkeyCache
# No need for Valkey server startup logic here; assume test environment provides Valkey.
from unittest.mock import patch

import pytest

# --- Real async Valkey client fixture for integration tests ---
# If using pytest-asyncio, import it here if needed
import pytest_asyncio
from valkey.asyncio import Valkey
from valkey.exceptions import TimeoutError, ValkeyError

from app.core.valkey.cache.valkey_cache import ValkeyCache
from app.core.valkey.client import client as valkey_client
from app.core.valkey.config import ValkeyConfig
from app.core.valkey.limiting.rate_limit import check_rate_limit


@pytest_asyncio.fixture(autouse=True)
async def flush_valkey():
    """
    ! Flush Valkey before each test for isolation
    """
    await valkey_client.flushdb()


@pytest.fixture
def valkey_cache():
    """# Pre-configured ValkeyCache instance (if available)
"""
    cache = ValkeyCache()
    yield cache
    # Cleanup any test data
    asyncio.run(cache.clear_namespace("test_"))


@pytest.fixture
def rate_limit_checker():
    """# Rate limit checker function with default values (Valkey)
"""

    async def checker(endpoint, identifier, limit=10, window=60):
        return await check_rate_limit(endpoint, identifier, limit, window)

    return checker


@pytest.fixture(autouse=True)
def reset_valkey_config():
    """# Reset ValkeyConfig between tests
"""
    original_attrs = {k: v for k, v in vars(ValkeyConfig).items() if not k.startswith('__')}
    yield
    # Restore only the attributes that were present originally
    for k in list(vars(ValkeyConfig).keys()):
        if not k.startswith('__'):
            if k in original_attrs:
                setattr(ValkeyConfig, k, original_attrs[k])
            else:
                delattr(ValkeyConfig, k)


@pytest.fixture
def mock_time():
    """# Mock time module for time-sensitive tests
"""
    with patch("time.time") as mock_time:
        mock_time.return_value = 0
        yield mock_time
