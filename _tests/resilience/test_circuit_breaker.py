"""
Tests for the Valkey client's built-in retry/backoff functionality
"""

import logging
from unittest.mock import patch

import pytest
from valkey_core.exceptions import TimeoutError

from app.core.valkey_core.client import client as valkey_client

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_valkey_retry_and_backoff(monkeypatch):
    """
    Test that Valkey's built-in retry/backoff logic triggers and eventually raises after max attempts.
    """
    # Patch the underlying get_client().get to always fail
    async def always_fail(*args, **kwargs):
        raise TimeoutError("Simulated failure")
    monkeypatch.setattr(valkey_client, "get_client", lambda: valkey_client._get_cluster_client())
    monkeypatch.setattr(valkey_client._get_cluster_client().__class__, "get", always_fail)

    # Should raise after max retries
    with pytest.raises(TimeoutError):
        await valkey_client.get("test_key")


@pytest.mark.asyncio
async def test_valkey_retry_success_on_second_attempt(monkeypatch):
    """
    Test that built-in retry/backoff succeeds if a retry eventually passes.
    """
    attempts = {"count": 0}
    async def flaky_get(*args, **kwargs):
        if attempts["count"] < 1:
            attempts["count"] += 1
            raise TimeoutError("fail once")
        return b"42"
    monkeypatch.setattr(valkey_client, "get_client", lambda: valkey_client._get_cluster_client())
    monkeypatch.setattr(valkey_client._get_cluster_client().__class__, "get", flaky_get)
    result = await valkey_client.get("test_key")
    assert result == 42 or result == b"42"


@pytest.mark.asyncio
async def test_valkey_timeout_error_classification():
    """
    Verify client handles different error types properly
    """
    client = valkey_client

    test_cases = [
        (TimeoutError("Timeout"), "connection"),
    ]

    for error, error_type in test_cases:
        with patch("valkey.asyncio.cluster.ValkeyCluster.execute_command") as mock_exec:
            mock_exec.side_effect = error
            with pytest.raises(type(error)):
                await client.get("test_key")
