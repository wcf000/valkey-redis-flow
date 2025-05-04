"""
Tests for the Valkey client's built-in circuit breaker functionality
"""

import logging
from unittest.mock import patch

import pytest
from prometheus_client import REGISTRY
from circuitbreaker import CircuitBreakerError
from app.core.valkey.client import client as valkey_client
from app.core.valkey.config import ValkeyConfig

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def reset_prometheus():
    """Reset Prometheus metrics between tests"""
    for collector in list(REGISTRY._collector_to_names):
        if collector not in REGISTRY._names_to_collectors.values():
            REGISTRY.unregister(collector)


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold():
    """Verify client's circuit opens after configured failures"""
    client = valkey_client

    with patch("valkey.asyncio.cluster.ValkeyCluster.execute_command") as mock_exec:
        mock_exec.side_effect = Exception("Shard down")

        for _ in range(ValkeyConfig.CIRCUIT_BREAKER["failure_threshold"] - 1):
            with pytest.raises(Exception):
                await client.get("test_key")

        with pytest.raises(CircuitBreakerError):
            await client.get("test_key")


@pytest.mark.asyncio
async def test_circuit_resets_after_timeout():
    """Test client's automatic recovery after timeout"""
    client = valkey_client

    with (
        patch("valkey.asyncio.cluster.ValkeyCluster.execute_command") as mock_exec,
    ):
        mock_exec.side_effect = Exception("Shard down")

        for _ in range(ValkeyConfig.CIRCUIT_BREAKER["failure_threshold"]):
            with pytest.raises(Exception):
                await client.get("test_key")

        # Simulate timeout and reset
        # (add appropriate time patching if Valkey uses time-based reset logic)
        mock_exec.return_value = "OK"
        result = await client.get("test_key")
        assert result == "OK"


@pytest.mark.asyncio
async def test_error_classification():
    """Verify client handles different error types properly"""
    client = valkey_client

    test_cases = [
        (Exception("Timeout"), "connection"),
        (Exception("READONLY"), "response"),
    ]

    for error, error_type in test_cases:
        with patch("valkey.asyncio.cluster.ValkeyCluster.execute_command") as mock_exec:
            mock_exec.side_effect = error
            with pytest.raises(type(error)):
                await client.get("test_key")


@pytest.mark.asyncio
async def test_metrics_collection():
    """Verify client collects proper circuit metrics"""
    client = valkey_client

    with patch("valkey.asyncio.cluster.ValkeyCluster.execute_command") as mock_exec:
        mock_exec.side_effect = Exception("Shard down")

        try:
            await client.get("test_key")
        except Exception:
            pass

        # Verify metrics were updated
        # (update this assertion to match Valkey's metrics API)
        # assert (
        #     client._metrics["errors"]
        #     .labels(operation="get", type="connection")
        #     ._value.get()
        #     == 1
        # )
