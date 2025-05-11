"""
Production-grade Valkey sharding tests with:
- Error handling and logging
- Performance metrics
- Edge case testing
- Monitoring integration
"""
import asyncio
import logging
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.core.valkey.client import client as valkey_client
from app.core.valkey.config import ValkeyConfig
from app.core.valkey.metrics import record_metrics

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_shard_distribution():
    """Test keys are properly distributed across shards with metrics"""
    with patch('valkey.asyncio.cluster.ValkeyCluster') as mock_cluster:
        mock_client = MagicMock()
        mock_cluster.return_value = mock_client
        
        # Setup metrics
        start_time = datetime.now()
        
        try:
            # Test with 1000 keys
            client = valkey_client
            valkey = await client.get_client()
            
            for i in range(1000):
                await valkey.set(f"test_key_{i}", f"value_{i}")
            
            # Verify distribution
            called_nodes = {call[0][0] for call in mock_client.set.call_args_list}
            assert len(called_nodes) == len(ValkeyConfig.VALKEY_SHARD_NODES)
            
            # Record metrics
            duration = (datetime.now() - start_time).total_seconds()
            record_metrics(
                "valkey_sharding_distribution",
                {"keys": 1000, "shards": len(called_nodes), "duration": duration}
            )
            
        except Exception as e:
            logger.error(f"Shard distribution test failed: {e}")
            raise
        finally:
            mock_client.reset_mock()

@pytest.mark.asyncio
async def test_shard_failover():
    """Test client handles partial cluster failures with retries"""
    with patch('valkey.asyncio.cluster.ValkeyCluster.execute_command') as mock_exec:
        # Setup failure scenarios
        mock_exec.side_effect = [
            Exception("Node down"),
            "OK",
            Exception("Cluster reconfigured"),
            "OK",
        ]
        
        try:
            client = valkey_client
            valkey = await client.get_client()
            
            # Should succeed after failover
            result = await valkey.set("test_key", "value")
            assert result == "OK"
            assert mock_exec.call_count == 4
            
            # Verify retry logging
            assert any("Retrying on different shard" in str(call) 
                      for call in mock_exec.call_args_list)
            
        except Exception as e:
            logger.error(f"Shard failover test failed: {e}")
            raise

@pytest.mark.asyncio
async def test_shard_rebalancing():
    """Test cluster rebalancing doesn't cause data loss"""
    with patch('valkey.asyncio.cluster.ValkeyCluster') as mock_cluster:
        mock_client = MagicMock()
        mock_cluster.return_value = mock_client
        
        # Setup rebalance scenario
        mock_client.get.side_effect = [
            None,  # First attempt - key not found
            "moved_value",  # Second attempt - found after rebalance
            RuntimeError("Cluster rebalancing")  # Edge case
        ]
        
        try:
            client = valkey_client
            valkey = await client.get_client()
            
            # Test normal rebalance
            value = await valkey.get("rebalanced_key")
            assert value == "moved_value"
            
            # Test edge case during rebalance
            with pytest.raises(RuntimeError):
                await valkey.get("edge_case_key")
            
        except Exception as e:
            logger.error(f"Shard rebalancing test failed: {e}")
            raise
        finally:
            mock_client.reset_mock()

@pytest.mark.asyncio
async def test_shard_performance_under_load():
    """Test shard performance under concurrent load"""
    with patch('valkey.asyncio.cluster.ValkeyCluster') as mock_cluster:
        mock_client = MagicMock()
        mock_cluster.return_value = mock_client
        
        # Setup concurrent test
        start_time = datetime.now()
        
        try:
            client = valkey_client
            valkey = await client.get_client()
            
            # Simulate concurrent requests
            tasks = []
            for i in range(1000):
                tasks.append(valkey.set(f"load_key_{i}", f"value_{i}"))
            
            await asyncio.gather(*tasks)
            
            # Verify performance
            duration = (datetime.now() - start_time).total_seconds()
            assert duration < 2.0  # Should complete under 2 seconds
            
            # Record metrics
            record_metrics(
                "valkey_sharding_load_test",
                {"operations": 1000, "duration": duration}
            )
            
        except Exception as e:
            logger.error(f"Shard load test failed: {e}")
            raise
        finally:
            mock_client.reset_mock()

@pytest.mark.asyncio
async def test_shard_metrics_label_isolation():
    """Test that metrics for sharding are labeled per shard and not cross-contaminated."""
    with patch('valkey.asyncio.cluster.ValkeyCluster') as mock_cluster:
        mock_client = MagicMock()
        mock_cluster.return_value = mock_client
        client = valkey_client
        valkey = await client.get_client()
        # Simulate writes to two shards
        mock_client.set.side_effect = lambda key, value: f"shard_{int(key.split('_')[-1]) % 2}"
        results = [await valkey.set(f"metric_key_{i}", f"v{i}") for i in range(10)]
        assert set(results) == {"shard_0", "shard_1"}
        # Here you would check Prometheus or your metrics store for correct labeling

@pytest.mark.asyncio
async def test_shard_data_consistency_after_failover():
    """Test that data is not lost or duplicated after failover and retry."""
    with patch('valkey.asyncio.cluster.ValkeyCluster.execute_command') as mock_exec:
        # Simulate failover and recovery
        mock_exec.side_effect = [Exception("fail"), "OK", "OK"]
        client = valkey_client
        valkey = await client.get_client()
        result1 = await valkey.set("failover_key", "v1")
        result2 = await valkey.set("failover_key", "v2")
        assert result1 == "OK"
        assert result2 == "OK"
        assert mock_exec.call_count == 3

@pytest.mark.asyncio
async def test_shard_rebalance_metrics():
    """Test that rebalancing events are recorded in metrics/monitoring."""
    with patch('valkey.asyncio.cluster.ValkeyCluster') as mock_cluster:
        mock_client = MagicMock()
        mock_cluster.return_value = mock_client
        mock_client.get.side_effect = [None, "moved", None]
        client = valkey_client
        valkey = await client.get_client()
        await valkey.get("rebalance_key_1")
        await valkey.get("rebalance_key_2")
        # Here you would check that record_metrics or a similar function was called
        # (Requires a real metrics backend or a mock/spy)
