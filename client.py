"""
Valkey client initialization and configuration.

Follows best practices for:
- Connection pooling
- Timeout handling
- Error recovery
- Sharding support
- OpenTelemetry tracing for all key operations
- Structured Valkey exception handling
"""

import asyncio
import json
import logging
from typing import Any

from circuitbreaker import circuit
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from prometheus_client import Gauge, Histogram
from valkey.asyncio import Valkey, ValkeyCluster
from valkey.exceptions import TimeoutError, ValkeyError

from app.core.valkey.exceptions.exceptions import handle_valkey_exceptions
from app.core.valkey.config import ValkeyConfig

VALKEY_CLUSTER = ValkeyConfig.VALKEY_CLUSTER
VALKEY_DB = ValkeyConfig.VALKEY_DB
VALKEY_FAILURE_THRESHOLD = ValkeyConfig.VALKEY_FAILURE_THRESHOLD
VALKEY_HOST = ValkeyConfig.VALKEY_HOST
VALKEY_MAX_CONNECTIONS = ValkeyConfig.VALKEY_MAX_CONNECTIONS
VALKEY_PASSWORD = ValkeyConfig.VALKEY_PASSWORD
VALKEY_PORT = ValkeyConfig.VALKEY_PORT
VALKEY_RECOVERY_TIMEOUT = ValkeyConfig.VALKEY_RECOVERY_TIMEOUT
VALKEY_SOCKET_CONNECT_TIMEOUT = ValkeyConfig.VALKEY_SOCKET_CONNECT_TIMEOUT
VALKEY_SOCKET_TIMEOUT = ValkeyConfig.VALKEY_SOCKET_TIMEOUT

logger = logging.getLogger(__name__)

# Default timeout constants (in seconds)
DEFAULT_CONNECTION_TIMEOUT = 5.0
DEFAULT_SOCKET_TIMEOUT = 10.0
DEFAULT_COMMAND_TIMEOUT = 5.0

# Prometheus metrics
SHARD_SIZE_GAUGE = Gauge(
    "valkey_shard_size_bytes", "Size of Valkey shards in bytes", ["shard"]
)
SHARD_OPS_GAUGE = Gauge(
    "valkey_shard_ops_per_sec", "Operations per second per shard", ["shard"]
)
REQUEST_DURATION = Histogram(
    "valkey_request_duration_seconds", "Valkey request duration", ["operation", "shard"]
)

tracer = trace.get_tracer(__name__)


class ValkeyClient:
    """
    Valkey client wrapper with connection management and utilities.

    Handles:
    - Connection pooling
    - Automatic reconnections
    - Timeout handling
    - Sharding support
    - OpenTelemetry tracing for all key operations
    - Structured Valkey exception handling
    """

    def __init__(self):
        """Initialize with automatic cluster detection"""
        self._client = None
        self._cluster_mode = VALKEY_CLUSTER
        self._metrics_task = None

    async def get_client(self) -> Valkey | ValkeyCluster:
        """
        Returns configured client based on settings
        - Auto-reconnects if needed
        - Supports both cluster and sharded modes
        """
        if self._cluster_mode:
            return await self._get_cluster_client()
        return await self._get_sharded_client()

    async def _get_cluster_client(self) -> ValkeyCluster:
        """Get a cluster Valkey client based on configuration"""
        if not self._client:
            self._client = ValkeyCluster(
                host=VALKEY_HOST,
                port=VALKEY_PORT,
                password=VALKEY_PASSWORD,
                db=VALKEY_DB,
                socket_timeout=VALKEY_SOCKET_TIMEOUT,
                socket_connect_timeout=VALKEY_SOCKET_CONNECT_TIMEOUT,
                max_connections=VALKEY_MAX_CONNECTIONS,
            )
        return self._client

    async def _get_sharded_client(self) -> ValkeyCluster:
        """Get a Valkey client configured for sharded mode"""
        from valkey.asyncio.cluster import ValkeyCluster

        return ValkeyCluster(
            startup_nodes=[{"host": VALKEY_HOST, "port": VALKEY_PORT}],
            password=VALKEY_PASSWORD,
            db=VALKEY_DB,
            max_connections_per_node=VALKEY_MAX_CONNECTIONS,
            socket_timeout=VALKEY_SOCKET_TIMEOUT,
            socket_connect_timeout=VALKEY_SOCKET_CONNECT_TIMEOUT,
            decode_responses=True,
        )

    async def shutdown(self):
        """Cleanly shutdown Valkey client"""
        if self._client:
            await self._client.close()
            self._client = None
        if self._metrics_task:
            self._metrics_task.cancel()

    async def __aenter__(self):
        if not await self.is_healthy():
            raise ConnectionError("Valkey connection failed")
        self._metrics_task = asyncio.create_task(self._update_metrics())

    @circuit(
        failure_threshold=VALKEY_FAILURE_THRESHOLD,
        recovery_timeout=VALKEY_RECOVERY_TIMEOUT,
        expected_exception=(ValkeyError, TimeoutError),
        fallback_function=lambda e: logger.warning(f"Circuit open: {str(e)}"),
    )
    async def get(self, key: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> Any:
        async def _action():
            with tracer.start_as_current_span("valkey.get") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "get")
                span.set_attribute("db.redis.key", key)
                value = await (await self.get_client()).get(key, timeout=timeout)
                span.set_status(StatusCode.OK)
                return json.loads(value) if value else None
        return await handle_valkey_exceptions(_action, logger=logger, endpoint="valkey.get")

    @circuit(
        failure_threshold=VALKEY_FAILURE_THRESHOLD,
        recovery_timeout=VALKEY_RECOVERY_TIMEOUT,
        expected_exception=(ValkeyError, TimeoutError),
    )
    async def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        timeout: float = DEFAULT_COMMAND_TIMEOUT,
    ) -> bool:
        async def _action():
            with tracer.start_as_current_span("valkey.set") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "set")
                span.set_attribute("db.redis.key", key)
                span.set_attribute("db.redis.ttl", ex or 0)
                result = await (await self.get_client()).set(
                    key, json.dumps(value), ex=ex, timeout=timeout
                )
                span.set_status(StatusCode.OK)
                return result
        return await handle_valkey_exceptions(_action, logger=logger, endpoint="valkey.set")

    async def delete(self, *keys: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> int:
        async def _action():
            with tracer.start_as_current_span("valkey.delete") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "delete")
                span.set_attribute("db.redis.keys", str(keys))
                return await (await self.get_client()).delete(*keys, timeout=timeout)
        return await handle_valkey_exceptions(_action, logger=logger, endpoint="valkey.delete")

    async def is_healthy(self) -> bool:
        try:
            return await (await self.get_client()).ping()
        except (ValkeyError, TimeoutError):
            return False

    async def incr(self, key: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> int:
        async def _action():
            with tracer.start_as_current_span("valkey.incr") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "incr")
                span.set_attribute("db.redis.key", key)
                value = await (await self.get_client()).incr(key)
                span.set_status(StatusCode.OK)
                return value
        return await handle_valkey_exceptions(_action, logger=logger, endpoint="valkey.incr")

    async def expire(
        self, key: str, ex: int, timeout: float = DEFAULT_COMMAND_TIMEOUT
    ) -> bool:
        async def _action():
            with tracer.start_as_current_span("valkey.expire") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "expire")
                span.set_attribute("db.redis.key", key)
                span.set_attribute("db.redis.ttl", ex)
                result = await (await self.get_client()).expire(key, ex)
                span.set_status(StatusCode.OK)
                return result
        return await handle_valkey_exceptions(_action, logger=logger, endpoint="valkey.expire")

    async def ttl(self, key: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> int:
        async def _action():
            with tracer.start_as_current_span("valkey.ttl") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "ttl")
                span.set_attribute("db.redis.key", key)
                value = await (await self.get_client()).ttl(key)
                span.set_status(StatusCode.OK)
                return value
        return await handle_valkey_exceptions(_action, logger=logger, endpoint="valkey.ttl")

    async def exists(self, key: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> bool:
        async def _action():
            with tracer.start_as_current_span("valkey.exists") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "exists")
                span.set_attribute("db.redis.key", key)
                exists = await (await self.get_client()).exists(key)
                span.set_status(StatusCode.OK)
                return exists == 1
        return await handle_valkey_exceptions(_action, logger=logger, endpoint="valkey.exists")

    async def pipeline(self):
        async def _action():
            with tracer.start_as_current_span("valkey.pipeline") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "pipeline")
                client = await self.get_client()
                return client.pipeline()
        return await handle_valkey_exceptions(_action, logger=logger, endpoint="valkey.pipeline")

    async def pubsub(self):
        async def _action():
            with tracer.start_as_current_span("valkey.pubsub") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "pubsub")
                client = await self.get_client()
                return client.pubsub()
        return await handle_valkey_exceptions(_action, logger=logger, endpoint="valkey.pubsub")

    async def _update_metrics(self):
        """Periodically update Valkey metrics"""
        while True:
            try:
                client = await self.get_client()
                info = await client.info("all")

                for shard, stats in info.items():
                    SHARD_SIZE_GAUGE.labels(shard=shard).set(
                        stats.get("used_memory", 0)
                    )
                    SHARD_OPS_GAUGE.labels(shard=shard).set(
                        stats.get("instantaneous_ops_per_sec", 0)
                    )

            except Exception as e:
                logger.error(f"Metrics update failed: {e}")

            await asyncio.sleep(60)  # Update every minute


# Singleton Valkey client instance
client = ValkeyClient()

# Module-level functions for convenience
get_client = client.get_client
shutdown = client.shutdown
get = client.get
set = client.set
delete = client.delete
is_healthy = client.is_healthy
incr = client.incr
expire = client.expire
ttl = client.ttl
exists = client.exists
pipeline = client.pipeline
pubsub = client.pubsub
