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

## 2. Initializing the Valkey Client

The singleton client is async-ready and supports connection pooling, sharding/cluster, circuit breaking, and OpenTelemetry tracing.

```python
from app.core.valkey.client import client  # Singleton instance

# Async usage
valkey = await client.get_client()
await valkey.ping()
```

---

## 3. Advanced Features

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

## 4. Usage Patterns

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

## 5. Decorators & Batch Caching

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

## 6. Exception Handling

All Valkey exceptions are mapped to HTTP responses and structured for FastAPI. Use `handle_valkey_exceptions` for robust error-to-HTTP mapping and OpenTelemetry error tracing.

```python
from app.core.valkey.exceptions import handle_valkey_exceptions

async def my_valkey_op():
    ...

result = await handle_valkey_exceptions(my_valkey_op, logger=logger, endpoint="/valkey/op")
```

---

## 7. Observability: Tracing & Metrics

- **OpenTelemetry**: All client methods are traced (`db.system`, `db.operation`, key context, errors).
- **Prometheus**: Memory and ops/second per shard.
- **Health Checks**: Use `await client.is_healthy()` for readiness/liveness endpoints.

---

## 8. Best Practices

- Use decorators for DRY caching logic.
- Always handle exceptions with `handle_valkey_exceptions` in API/business logic.
- Monitor with both tracing and Prometheus metrics.
- Centralize all config in `ValkeyConfig`.
- Prefer async/await everywhere for scalability.
- Use pipelines for batch operations and pubsub for real-time features.
- Review `_docs/best_practices/open-telmentry.md` for tracing and observability guidance.

---

## 9. Troubleshooting
- For anti-patterns and advanced diagnostics, see the anti-patterns doc and health check endpoints.
- For questions, refer to the `_docs/best_practices` folder.

---

**Valkey is now your production-ready, observable, and scalable caching and pub/sub backend.**
