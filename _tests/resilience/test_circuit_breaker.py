"""
Tests for the Valkey client's built-in retry/backoff functionality
"""

import logging
from unittest.mock import patch

import pytest
from ...exceptions.exceptions import TimeoutError

from app.core.valkey_core.client import client as valkey_client

logger = logging.getLogger(__name__)


from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_valkey_retry_and_backoff(monkeypatch):
    """
    Test that Valkey's built-in retry/backoff logic triggers and eventually raises after max attempts.
    """
    async def always_fail(*args, **kwargs):
        raise TimeoutError("Simulated failure")
    mock_cluster_client = AsyncMock()
    mock_cluster_client.get.side_effect = always_fail
    monkeypatch.setattr(valkey_client, "_get_cluster_client", AsyncMock(return_value=mock_cluster_client))
    monkeypatch.setattr(valkey_client, "get_client", AsyncMock(return_value=mock_cluster_client))
    with pytest.raises(TimeoutError):
        await valkey_client.get("test_key", wrap_http_exception=False)



import asyncio
from app.core.valkey_core.limiting.retry import async_retry

@pytest.mark.asyncio
async def test_valkey_retry_success_on_second_attempt():
    """
    Test that retry succeeds on a second attempt after failure.
    """
    attempts = {"count": 0}

    @async_retry(attempts=2, delay=0.01, exceptions=(TimeoutError,))
    async def flaky():
        if attempts["count"] < 1:
            attempts["count"] += 1
            raise TimeoutError("fail once")
        return 42

    result = await flaky()
    assert result == 42
    assert attempts["count"] == 1



@pytest.mark.asyncio
async def test_valkey_timeout_error_classification(monkeypatch):
    """
    Verify client handles different error types properly
    """
    client = valkey_client
    async def raise_timeout(*args, **kwargs):
        raise TimeoutError("Timeout")
    mock_cluster_client = AsyncMock()
    mock_cluster_client.get.side_effect = raise_timeout
    monkeypatch.setattr(valkey_client, "_get_cluster_client", AsyncMock(return_value=mock_cluster_client))
    monkeypatch.setattr(valkey_client, "get_client", AsyncMock(return_value=mock_cluster_client))
    with pytest.raises(TimeoutError):
        await client.get("test_key", wrap_http_exception=False)

