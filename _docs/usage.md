# Valkey Integration Usage Guide

This guide covers best practices for using the Valkey (Redis-compatible) integration in this codebase, including configuration, advanced client features, caching decorators, error handling, tracing, and monitoring. All examples use type hints and follow DRY, SOLID, and CI/CD-aligned patterns.

---

## 1. Configuration

All Valkey settings are centralized in `ValkeyConfig` and sourced from environment variables or `settings`.

```python
from app.core.valkey.config import ValkeyConfig

host: str = ValkeyConfig.VALKEY_HOST
port: int = ValkeyConfig.VALKEY_PORT
# ...and so on
```

---

## 2. Built-in Utilities and Resilience Features

Valkey provides robust built-in utilities for connection resilience, retry, and backoff, which are now used natively in this codebase. These features are production-grade and configurable via `ValkeyConfig`.

### Retry & Backoff
- **What:** Automatically retries failed commands (e.g., timeouts, transient network errors) using configurable strategies.
- **How to configure:**
  - `VAPI_RETRY_ATTEMPTS`: Number of retry attempts (default: 3)
  - `VAPI_RETRY_BACKOFF_TYPE`: Backoff strategy (`exponential`, `jitter`, `constant`)
  - `VAPI_RETRY_BACKOFF_BASE`, `VAPI_RETRY_BACKOFF_CAP`: Timing parameters for backoff
- **How it works:**
  - The `Retry` object is passed to the Valkey/ValkeyCluster client. All commands (get/set/etc.) are retried automatically on supported errors.
  - Example:
    ```python
    from valkey.backoff import ExponentialBackoff
    from valkey.retry import Retry
    from valkey.asyncio import Valkey

    backoff = ExponentialBackoff(base=0.01, cap=0.5)
    retry = Retry(backoff, retries=3)
    client = Valkey(host="localhost", retry=retry)
    ```
- **Best Practice:** Use exponential or jitter for distributed systems to avoid thundering herd.

### Error Handling
- **What:** Only specific exceptions (e.g., `TimeoutError`, `ValkeyError`) trigger retries; others are raised immediately.
- **How to extend:**
  - Update `supported_errors` in your `Retry` config if you want to retry on additional error types.

### Monitoring & Tracing
- **What:** All retry attempts and failures are automatically traced and can be monitored via Prometheus and OpenTelemetry integrations in this codebase.
- **How to use:**
  - Prometheus metrics are updated on each retry/failure.
  - Tracing spans (`valkey.get`, `valkey.set`) are annotated with retry information.

### Example: Using the Client with Built-in Resilience
```python
async def cache_lookup(key: str):
    value = await valkey_client.get(key)
    if value is None:
        # handle cache miss
        ...
```
- No need to add manual retry logic—it's handled by the client.

---

## 3. Initializing the Valkey Client

The singleton client is async-ready and supports connection pooling, sharding/cluster, circuit breaking, and OpenTelemetry tracing.

```python
from app.core.valkey.client import client  # Singleton instance

# Async usage
valkey = await client.get_client()
await valkey.ping()
```

---

## 4. Advanced Features

- **Async/Await**: All operations are fully async for high performance.
- **Connection Pooling**: Efficient resource use for both standalone and cluster modes.
- **Circuit Breaking**: Built-in with `circuitbreaker` for resilience.
- **Timeouts**: Configurable per operation.
- **OpenTelemetry Tracing**: All major operations are traced for observability.
- **Prometheus Metrics**: Shard memory and ops/second tracked by default.
- **Health Checks**: `await client.is_healthy()` for readiness probes.
- **Pipeline & Pub/Sub**: Batch and streaming support out of the box.
- **Production-Grade Error Handling**: All exceptions are mapped and structured for FastAPI/HTTP.

---

## 5. Usage Patterns

### Basic Get/Set
```python
# Get a value
value = await client.get("my_key")

# Set a value with TTL (seconds)
await client.set("my_key", {"foo": "bar"}, ex=600)

# Delete keys
await client.delete("my_key", "other_key")

# Increment
await client.incr("counter")

# Expire
await client.expire("my_key", ex=3600)

# TTL
ttl = await client.ttl("my_key")

# Exists
exists = await client.exists("my_key")
```

### Pipeline Example
```python
pipe = await client.pipeline()
await pipe.set("foo", 1)
await pipe.set("bar", 2)
results = await pipe.execute()
```

### Pub/Sub Example
```python
pubsub = await client.pubsub()
await pubsub.subscribe("my_channel")
async for message in pubsub.listen():
    print(message)
```

---

## 6. Decorators & Batch Caching

### Cache Decorator
```python
from app.core.valkey.decorators import valkey_cache

@valkey_cache(ttl=300, key_prefix="user:")
async def get_user(user_id: str):
    ...
```

### Batch Warm Cache
```python
from app.core.valkey.decorators import warm_valkey_cache_batch

# Preload multiple keys efficiently
await warm_valkey_cache_batch(["key1", "key2"], loader=my_loader, ttl=600)
```

---

## 7. Exception Handling

All Valkey exceptions are mapped to HTTP responses and structured for FastAPI. Use `handle_valkey_exceptions` for robust error-to-HTTP mapping and OpenTelemetry error tracing.

```python
from app.core.valkey.exceptions import handle_valkey_exceptions

async def my_valkey_op():
    ...

result = await handle_valkey_exceptions(my_valkey_op, logger=logger, endpoint="/valkey/op")
```

---

## 8. Observability: Tracing & Metrics

- **OpenTelemetry**: All client methods are traced (`db.system`, `db.operation`, key context, errors).
- **Prometheus**: Memory and ops/second per shard.
- **Health Checks**: Use `await client.is_healthy()` for readiness/liveness endpoints.

---

## 9. Distributed Locking with Valkey

Valkey provides a robust, distributed lock mechanism for synchronizing access to shared resources across processes and machines. This is essential for preventing race conditions in critical sections, such as cache updates, job scheduling, or resource allocation.

### How to Use the Valkey Lock

You can use the built-in lock via the `ValkeyClient.lock()` context manager. This is fully async and safe for use in FastAPI and other async Python environments.

#### Basic Example
```python
from app.core.valkey.client import client

async def critical_section():
    async with client.lock("my:lock:key", timeout=10):
        # Only one process can execute this block at a time
        do_critical_work()
```

#### Parameters
- `name` (str): Unique lock name/key (e.g., "resource:123:lock").
- `timeout` (float, optional): How long (in seconds) the lock will be held before auto-expiry.
- `sleep` (float, optional): Sleep interval between lock acquire attempts (default: 0.1s).
- `blocking` (bool, optional): If False, return immediately if lock is not acquired.
- `blocking_timeout` (float, optional): Max seconds to wait for lock acquisition.
- `thread_local` (bool, optional): Scope lock to thread (default: True).

#### Advanced Example: Non-blocking Acquire
```python
async def try_lock():
    try:
        async with client.lock("resource:lock", blocking=False):
            # Acquired lock, do work
            ...
    except TimeoutError:
        # Could not acquire lock
        pass
```

#### Best Practices
- Always use a unique `name` per resource to avoid deadlocks.
- Use reasonable `timeout` values to prevent stale locks.
- Handle `TimeoutError` for non-blocking or time-limited acquisition.
- Do not hold locks longer than necessary.

#### When to Use
- Cache stampede protection
- Distributed job scheduling
- Resource allocation (e.g., inventory, quotas)

---

## 10. Best Practices

- Use decorators for DRY caching logic.
- Always handle exceptions with `handle_valkey_exceptions` in API/business logic.
- Monitor with both tracing and Prometheus metrics.
- Centralize all config in `ValkeyConfig`.
- Prefer async/await everywhere for scalability.
- Use pipelines for batch operations and pubsub for real-time features.
- Review `_docs/best_practices/open-telmentry.md` for tracing and observability guidance.

---

## 11. Troubleshooting
- For anti-patterns and advanced diagnostics, see the anti-patterns doc and health check endpoints.
- For questions, refer to the `_docs/best_practices` folder.

---

**Valkey is now your production-ready, observable, and scalable caching and pub/sub backend.**
