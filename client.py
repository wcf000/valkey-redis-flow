"""
Valkey client initialization and configuration.

Follows best practices for:
- Connection pooling
- Timeout handling
- Error recovery
- Sharding support
- OpenTelemetry tracing for all key operations
- Structured Valkey exception handling
- Distributed locking
"""

import asyncio
import json
import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import StatusCode
from prometheus_client import Gauge, Histogram
from valkey.asyncio import Valkey, ValkeyCluster
from valkey.backoff import (
    ConstantBackoff,
    DecorrelatedJitterBackoff,
    ExponentialBackoff,
)
from valkey.retry import Retry
from app.core.valkey_core.exceptions.exceptions import TimeoutError, ValkeyError

from app.core.valkey_core.config import ValkeyConfig
from app.core.valkey_core.exceptions.exceptions import handle_valkey_exceptions

VALKEY_CLUSTER = ValkeyConfig.VALKEY_CLUSTER
VALKEY_DB = ValkeyConfig.VALKEY_DB
VALKEY_HOST = ValkeyConfig.VALKEY_HOST
VALKEY_MAX_CONNECTIONS = ValkeyConfig.VALKEY_MAX_CONNECTIONS
VALKEY_PASSWORD = ValkeyConfig.VALKEY_PASSWORD
VALKEY_PORT = ValkeyConfig.VALKEY_PORT
VALKEY_SOCKET_CONNECT_TIMEOUT = ValkeyConfig.VALKEY_SOCKET_CONNECT_TIMEOUT
VALKEY_SOCKET_TIMEOUT = ValkeyConfig.VALKEY_SOCKET_TIMEOUT

logger = logging.getLogger(__name__)

# Default timeout constants (in seconds)
DEFAULT_CONNECTION_TIMEOUT = 5.0
DEFAULT_SOCKET_TIMEOUT = 10.0
DEFAULT_COMMAND_TIMEOUT = 5.0

# Prometheus metrics
SHARD_SIZE_GAUGE = None
SHARD_OPS_GAUGE = None
REQUEST_DURATION = None

tracer = trace.get_tracer(__name__)


class ValkeyLock:
    """
    Distributed lock using Valkey's built-in lock mechanism.
    Usage:
        async with ValkeyLock(client, name, timeout=5):
            # critical section
    """
    def __init__(self, client, name: str, timeout: float | None = None, sleep: float = 0.1, blocking: bool = True, blocking_timeout: float | None = None, thread_local: bool = False):
        # thread_local=False to avoid _thread._local issues in async
        self._lock = client._client.lock(
            name,
            timeout=timeout,
            sleep=sleep,
            blocking=blocking,
            blocking_timeout=blocking_timeout,
            thread_local=thread_local,
        )

    async def __aenter__(self):
        acquired = await self._lock.acquire()
        if not acquired:
            raise TimeoutError("Could not acquire Valkey lock")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._lock.release()


class ValkeyClient:
    # ...
    async def scan(self, match: str = "*") -> list[str]:
        """
        Asynchronously scan for all keys matching the pattern.
        Uses the underlying Redis/Valkey SCAN command.
        """
        cursor = 0
        keys = []
        while True:
            cursor, batch = await self._client.scan(cursor=cursor, match=match)
            keys.extend(batch)
            if cursor == 0:
                break
        return keys

    async def lrem(self, key: str, count: int, value: str) -> int:
        """
        Remove elements from a list (like Redis LREM).
        """
        async def _action():
            with tracer.start_as_current_span("valkey.lrem") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "lrem")
                span.set_attribute("db.redis.key", key)
                result = await (await self.get_client()).lrem(key, count, value)
                span.set_status(StatusCode.OK)
                return result
        return await handle_valkey_exceptions(_action, logger=logger, endpoint="valkey.lrem")

    async def rpush(self, key: str, value: str) -> int:
        """
        Append a value to a list (like Redis RPUSH).
        """
        async def _action():
            with tracer.start_as_current_span("valkey.rpush") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "rpush")
                span.set_attribute("db.redis.key", key)
                result = await (await self.get_client()).rpush(key, value)
                span.set_status(StatusCode.OK)
                return result
        return await handle_valkey_exceptions(_action, logger=logger, endpoint="valkey.rpush")

    async def llen(self, key: str) -> int:
        """
        Get the length of a list (like Redis LLEN).
        """
        async def _action():
            with tracer.start_as_current_span("valkey.llen") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "llen")
                span.set_attribute("db.redis.key", key)
                result = await (await self.get_client()).llen(key)
                span.set_status(StatusCode.OK)
                return result
        return await handle_valkey_exceptions(_action, logger=logger, endpoint="valkey.llen")

    async def rpop(self, key: str) -> str | None:
        """
        Remove and get the last element in a list (like Redis RPOP).
        """
        async def _action():
            with tracer.start_as_current_span("valkey.rpop") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "rpop")
                span.set_attribute("db.redis.key", key)
                result = await (await self.get_client()).rpop(key)
                span.set_status(StatusCode.OK)
                return result
        return await handle_valkey_exceptions(_action, logger=logger, endpoint="valkey.rpop")

    # ... existing code ...
    @property
    def conn(self):
        """Return the underlying Valkey/ValkeyCluster connection (sync, may be None if not initialized)."""
        return self._client

    async def aconn(self):
        """Return the underlying Valkey/ValkeyCluster connection, initializing if needed (async)."""
        return await self.get_client()

    """
    Valkey client wrapper with connection management and utilities.

    Handles:
    - Connection pooling
    - Automatic reconnections
    - Timeout handling
    - Sharding support
    - OpenTelemetry tracing for all key operations
    - Structured Valkey exception handling
    - Distributed locking (see lock method)
    """

    def __init__(self):
        """Initialize with automatic cluster detection"""
        self._client = None
        self._cluster_mode = VALKEY_CLUSTER
        self._metrics_task = None
        self._metrics_enabled = ValkeyConfig.VALKEY_METRICS_ENABLED
        self._metrics_namespace = getattr(
            ValkeyConfig, "REDIS_METRICS_NAMESPACE", "valkey"
        )

        # Only register metrics if enabled
        if self._metrics_enabled:
            self._register_metrics()

    def _register_metrics(self):
        global SHARD_SIZE_GAUGE, SHARD_OPS_GAUGE, REQUEST_DURATION
        # Register Prometheus metrics with namespace if needed
        SHARD_SIZE_GAUGE = Gauge(
            f"{self._metrics_namespace}_shard_size_bytes",
            "Size of Valkey shards in bytes",
            ["shard"],
        )
        SHARD_OPS_GAUGE = Gauge(
            f"{self._metrics_namespace}_shard_ops_per_sec",
            "Operations per second per shard",
            ["shard"],
        )
        REQUEST_DURATION = Histogram(
            f"{self._metrics_namespace}_request_duration_seconds",
            "Valkey request duration",
            ["operation", "shard"],
        )

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
            # Choose backoff strategy based on config
            backoff_type = ValkeyConfig.VALKEY_RETRY_BACKOFF_TYPE
            if backoff_type == "exponential":
                backoff = ExponentialBackoff(
                    base=ValkeyConfig.VALKEY_RETRY_BACKOFF_BASE,
                    cap=ValkeyConfig.VALKEY_RETRY_BACKOFF_CAP,
                )
            elif backoff_type == "jitter":
                backoff = DecorrelatedJitterBackoff(
                    base=ValkeyConfig.VALKEY_RETRY_BACKOFF_BASE,
                    cap=ValkeyConfig.VALKEY_RETRY_BACKOFF_CAP,
                )
            else:
                backoff = ConstantBackoff(ValkeyConfig.VALKEY_RETRY_BACKOFF_BASE)
            retry = Retry(
                backoff,
                retries=ValkeyConfig.VALKEY_RETRY_ATTEMPTS,
                supported_errors=(TimeoutError, ValkeyError),
            )
            self._client = ValkeyCluster(
                host=VALKEY_HOST,
                port=VALKEY_PORT,
                password=VALKEY_PASSWORD,
                db=VALKEY_DB,
                socket_timeout=VALKEY_SOCKET_TIMEOUT,
                socket_connect_timeout=VALKEY_SOCKET_CONNECT_TIMEOUT,
                max_connections=VALKEY_MAX_CONNECTIONS,
                ssl=ValkeyConfig.VALKEY_SSL,
                ssl_cert_reqs=ValkeyConfig.VALKEY_SSL_CERT_REQS,
                ssl_ca_certs=ValkeyConfig.VALKEY_SSL_CA_CERTS,
                ssl_keyfile=ValkeyConfig.VALKEY_SSL_KEYFILE,
                ssl_certfile=ValkeyConfig.VALKEY_SSL_CERTFILE,
                retry=retry,
                cluster_error_retry_attempts=ValkeyConfig.VALKEY_RETRY_ATTEMPTS,
            )
        return self._client

    async def _get_sharded_client(self) -> Valkey:
        """Get a sharded Valkey client based on configuration"""
        if not self._client:
            backoff_type = ValkeyConfig.VALKEY_RETRY_BACKOFF_TYPE
            if backoff_type == "exponential":
                backoff = ExponentialBackoff(
                    base=ValkeyConfig.VALKEY_RETRY_BACKOFF_BASE,
                    cap=ValkeyConfig.VALKEY_RETRY_BACKOFF_CAP,
                )
            elif backoff_type == "jitter":
                backoff = DecorrelatedJitterBackoff(
                    base=ValkeyConfig.VALKEY_RETRY_BACKOFF_BASE,
                    cap=ValkeyConfig.VALKEY_RETRY_BACKOFF_CAP,
                )
            else:
                backoff = ConstantBackoff(ValkeyConfig.VALKEY_RETRY_BACKOFF_BASE)
            retry = Retry(
                backoff,
                retries=ValkeyConfig.VALKEY_RETRY_ATTEMPTS,
                supported_errors=(TimeoutError, ValkeyError),
            )
            self._client = Valkey(
                host=VALKEY_HOST,
                port=VALKEY_PORT,
                password=VALKEY_PASSWORD,
                db=VALKEY_DB,
                socket_timeout=VALKEY_SOCKET_TIMEOUT,
                socket_connect_timeout=VALKEY_SOCKET_CONNECT_TIMEOUT,
                max_connections=VALKEY_MAX_CONNECTIONS,
                ssl=ValkeyConfig.VALKEY_SSL,
                ssl_cert_reqs=ValkeyConfig.VALKEY_SSL_CERT_REQS,
                ssl_ca_certs=ValkeyConfig.VALKEY_SSL_CA_CERTS,
                ssl_keyfile=ValkeyConfig.VALKEY_SSL_KEYFILE,
                ssl_certfile=ValkeyConfig.VALKEY_SSL_CERTFILE,
                retry=retry,
            )
        return self._client

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

    @staticmethod
    def _maybe_json_decode(value: str | bytes) -> Any:
        """
        Safely decode JSON if value looks like JSON, else return as-is.
        Handles bytes by decoding to str first.
        """
        if not value:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        v = value.strip()
        # Accepts JSON primitives, objects, arrays
        if v[:1] in ('"', '{', '[', 't', 'f', 'n') or v.replace('.', '', 1).isdigit():
            try:
                return json.loads(v)
            except Exception:
                pass
        return value

    async def get(self, key: str, timeout: float = None, wrap_http_exception: bool = True) -> Any:
        if timeout is None:
            timeout = ValkeyConfig.VALKEY_COMMAND_TIMEOUT

        async def _action():
            with tracer.start_as_current_span("valkey.get") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "get")
                span.set_attribute("db.redis.key", key)
                # Remove 'timeout' from direct call to backend client
                value = await (await self.get_client()).get(key)
                span.set_status(StatusCode.OK)
                return self._maybe_json_decode(value)

        return await handle_valkey_exceptions(
            _action, logger=logger, endpoint="valkey.get", wrap_http_exception=wrap_http_exception
        )

    async def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        timeout: float = None,
    ) -> bool:
        if timeout is None:
            timeout = ValkeyConfig.VALKEY_COMMAND_TIMEOUT

        async def _action():
            with tracer.start_as_current_span("valkey.set") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "set")
                span.set_attribute("db.redis.key", key)
                span.set_attribute("db.redis.ttl", ex or 0)
                # Remove 'timeout' from direct call to backend client
                result = await (await self.get_client()).set(
                    key, json.dumps(value), ex=ex
                )
                span.set_status(StatusCode.OK)
                return result

        return await handle_valkey_exceptions(
            _action, logger=logger, endpoint="valkey.set"
        )

    async def delete(self, *keys: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> int:
        async def _action():
            with tracer.start_as_current_span("valkey.delete") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "delete")
                span.set_attribute("db.redis.keys", str(keys))
                # Remove 'timeout' from direct call to backend client (see debugging_tests.md)
                return await (await self.get_client()).delete(*keys)

        return await handle_valkey_exceptions(
            _action, logger=logger, endpoint="valkey.delete"
        )

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

        return await handle_valkey_exceptions(
            _action, logger=logger, endpoint="valkey.incr"
        )

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

        return await handle_valkey_exceptions(
            _action, logger=logger, endpoint="valkey.expire"
        )

    async def ttl(self, key: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> int:
        async def _action():
            with tracer.start_as_current_span("valkey.ttl") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "ttl")
                span.set_attribute("db.redis.key", key)
                value = await (await self.get_client()).ttl(key)
                span.set_status(StatusCode.OK)
                return value

        return await handle_valkey_exceptions(
            _action, logger=logger, endpoint="valkey.ttl"
        )

    async def flushdb(self):
        """
        Flush the current Valkey database (for test isolation).
        """
        async def _action():
            with tracer.start_as_current_span("valkey.flushdb") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "flushdb")
                client = await self.get_client()
                result = await client.flushdb()
                span.set_status(StatusCode.OK)
                return result

        return await handle_valkey_exceptions(
            _action, logger=logger, endpoint="valkey.flushdb"
        )

    async def exists(self, key: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> bool:

        async def _action():
            with tracer.start_as_current_span("valkey.exists") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "exists")
                span.set_attribute("db.redis.key", key)
                exists = await (await self.get_client()).exists(key)
                span.set_status(StatusCode.OK)
                return exists == 1

        return await handle_valkey_exceptions(
            _action, logger=logger, endpoint="valkey.exists"
        )

    async def pipeline(self):
        async def _action():
            with tracer.start_as_current_span("valkey.pipeline") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "pipeline")
                client = await self.get_client()
                return client.pipeline()

        return await handle_valkey_exceptions(
            _action, logger=logger, endpoint="valkey.pipeline"
        )

    async def pubsub(self):
        async def _action():
            with tracer.start_as_current_span("valkey.pubsub") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "pubsub")
                client = await self.get_client()
                return client.pubsub()

        return await handle_valkey_exceptions(
            _action, logger=logger, endpoint="valkey.pubsub"
        )

    async def publish(self, channel: str, message: str):
        """
        Publish a message to a channel.
        """
        async def _action():
            with tracer.start_as_current_span("valkey.publish") as span:
                span.set_attribute("db.system", "valkey")
                span.set_attribute("db.operation", "publish")
                client = await self.get_client()
                return await client.publish(channel, message)
        return await handle_valkey_exceptions(
            _action, logger=logger, endpoint="valkey.publish"
        )

    async def _update_metrics(self):
        """Periodically update Valkey metrics"""
        while True:
            try:
                client = await self.get_client()
                info = await client.info("all")

                for shard, stats in info.items():
                    if SHARD_SIZE_GAUGE:
                        SHARD_SIZE_GAUGE.labels(shard=shard).set(
                            stats.get("used_memory", 0)
                        )
                    if SHARD_OPS_GAUGE:
                        SHARD_OPS_GAUGE.labels(shard=shard).set(
                            stats.get("instantaneous_ops_per_sec", 0)
                        )

            except Exception as e:
                logger.error(f"Metrics update failed: {e}")

            await asyncio.sleep(60)  # Update every minute

    def lock(self, name: str, timeout: float | None = None, sleep: float = 0.1, blocking: bool = True, blocking_timeout: float | None = None, thread_local: bool = True):
        """
        Acquire a distributed lock using Valkey's built-in locking.
        Usage:
            async with client.lock("resource_key", timeout=5):
                ...
        """
        return ValkeyLock(self, name, timeout, sleep, blocking, blocking_timeout, thread_local)


# Factory for Valkey client instance

def get_valkey_client():
    """
    Returns a new ValkeyClient instance for the current event loop.
    Use this in async code to avoid event loop issues with singletons.
    """
    return ValkeyClient()
# todo: Remove global singleton if not needed for legacy compatibility
import warnings
warnings.warn("The global 'client' singleton is deprecated. Use get_valkey_client() instead.", DeprecationWarning)
client = get_valkey_client()

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
lock = client.lock
