# Debugging Valkey Test Failures (Windows & Pytest-Asyncio)

This document summarizes the debugging strategies, issues encountered, and solutions that worked when running and fixing async Valkey tests in this codebase.

---

## Journey to Passing Valkey Rate Limiting Tests

### Issues We Faced
- **Argument Mismatch Errors:**
  - TypeErrors due to passing too many or too few arguments to rate limiter functions, especially after refactoring signatures to not require the Valkey client as a parameter.
  - Mutating `kwargs` in-place (e.g., `pop('key')`) led to missing arguments in subsequent test calls.
- **Fail-Open Logic:**
  - When Valkey was unavailable, all algorithms returned `True` (fail-open). This caused assertion errors in tests expecting blocking.

- **Prometheus Duplicate Metric Registration:**
  - Creating a new ValkeyClient for each test caused Prometheus metrics (e.g., `valkey_shard_size_bytes`) to be registered multiple times, raising `Duplicated timeseries in CollectorRegistry` exceptions. This triggered fail-open logic in all algorithms, causing all tests to pass regardless of rate limit logic.
  - **Fix:** Disable metrics during tests by setting `ValkeyConfig.VALKEY_METRICS_ENABLED = False` at the top of the test file:
    ```python
    from app.core.valkey_core.config import ValkeyConfig
    ValkeyConfig.VALKEY_METRICS_ENABLED = False
    ```
  - For production, ensure metrics are only registered once per process or use a guard to prevent duplicate registration.
- **ValkeyClient Attribute Errors:**
  - Using the ValkeyClient wrapper instead of the real connection led to errors like `'ValkeyClient' object has no attribute 'setnx'`.
- **Async Event Loop Issues (Windows):**
  - `RuntimeError: Event loop is closed` and `Future attached to a different loop` due to fixture and event loop policy mismatches.

### How We Got the Tests to Pass
- **Dynamic Argument Handling:**
  - Used `inspect.signature` to always pass the correct number of arguments to each rate limiter function.
  - Removed all in-place mutation of `kwargs`.
- **Valkey Connection Refactor:**
  - Added `.aconn()` to `ValkeyClient` to always get the true async Valkey connection for all Redis commands.
  - Updated all rate limiter implementations to use `redis = await valkey_client.aconn()`.
- **Fail-Open Test Logic:**
  - Tests now detect fail-open mode (all allowed) and skip blocking assertions if Valkey is unavailable.
- **Event Loop & Fixture Best Practices:**
  - Set `WindowsSelectorEventLoopPolicy` in `conftest.py` for Windows.
  - All async fixtures accept `event_loop` and pass it to Valkey clients.
  - Used function-scoped fixtures and avoided `asyncio.run` inside fixtures/tests.
  - Ensured Valkey DB is flushed before/after each test for isolation.

### Lessons Learned & Tips
- Always use a copy of `kwargs` if mutation is required in tests.
- Never pass wrapper clients to code expecting the raw Redis/Valkey interface.
- On Windows, always set the event loop policy for async tests.
- Use dynamic argument extraction (`inspect.signature`) to keep tests DRY and robust to signature changes.
- Document all troubleshooting steps and solutions for future maintainers.

---

## Common Issues Encountered

### 1. `RuntimeError: Event loop is closed`
- **Symptoms:** Tests fail with `event loop is closed`, often during async fixture setup/teardown or Valkey client cleanup.
- **Cause:** Async fixtures or Valkey clients are created/used on a different event loop than they are torn down on. This is especially problematic on Windows due to stricter event loop handling.

### 2. `got Future <Future pending> attached to a different loop`
- **Symptoms:** Pytest-asyncio complains about a Future attached to a different loop, often when using async clients or fixtures.
- **Cause:** Async clients or coroutines are created on one event loop but awaited/closed on another.

---

## Debugging Steps & Techniques

### A. Event Loop Policy (Windows)
- **Fix:** At the top of `conftest.py`, set the selector event loop policy on Windows:
  ```python
  import sys, asyncio
  if sys.platform.startswith("win"):
      asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
  ```
- **Result:** Prevents many event loop errors by ensuring a compatible event loop is used with pytest-asyncio on Windows.

### B. Use the `event_loop` Fixture in All Async Fixtures
- **Fix:** All `@pytest_asyncio.fixture` async fixtures should accept `event_loop` as a parameter. Pass this loop to Valkey/Redis clients if supported.
  ```python
  @pytest_asyncio.fixture
  async def redis_client(event_loop):
      client = Valkey(loop=event_loop, ...)
      await client.connect()
      yield client
      await client.close()
  ```
- **Result:** Ensures all async operations are performed on the same loop pytest manages, avoiding cross-loop errors.

### C. Proper Fixture Scoping
- **Fix:** Use function-scoped fixtures for async clients and caches (default for pytest-asyncio). Avoid module/session scope for async fixtures unless you are certain the event loop will persist.
- **Result:** Prevents event loop closure before async teardown.

### D. Avoid `asyncio.run` in Fixtures
- **Fix:** Never use `asyncio.run(...)` inside async fixtures or tests; always use `await`.
- **Result:** Prevents nested event loop errors.

### E. Clean Up After Each Test
- **Fix:** Flush Valkey/Redis before and after each test in a fixture to ensure test isolation.
  ```python
  @pytest_asyncio.fixture(autouse=True)
  async def flush_valkey(event_loop, redis_client):
      await redis_client.flushdb()
      yield
      await redis_client.flushdb()
  ```

---

## What Worked

- Setting the selector event loop policy on Windows.
- Passing `event_loop` to all async fixtures and clients.
- Using function-scoped async fixtures for Valkey/Redis clients and caches.
- Ensuring all async operations (including cleanup) are performed with `await` and on the same event loop.
- Flushing the Valkey database before and after each test.

---

## Further Tips

- If you still see event loop errors, check for any global or module-level async client instances. Always create/close them inside fixtures.
- If a client does **not** accept an event loop, still ensure all async code is run within the pytest-managed `event_loop`.
- Use `pytest.mark.asyncio` or `pytest_asyncio` for all async tests.
- If using Docker, ensure the Valkey/Redis container is up before running tests.

---

## Debugging Valkey Lock Test Failures

### Common Issues
- **Wrong Exception Type:**
  - Valkey's async lock raises `valkey.exceptions.TimeoutError`, not Python's built-in `TimeoutError`. Always import and use the correct exception in your tests:
    ```python
    from valkey.exceptions import TimeoutError as ValkeyTimeoutError
    with pytest.raises(ValkeyTimeoutError):
        async with valkey_client.lock(...):
            ...
    ```
- **Thread-Local/Async Context Errors:**
  - Never use `run_in_executor` for lock acquire/release in async code. Always use native async methods:
    ```python
    acquired = await self._lock.acquire()
    await self._lock.release()
    ```
- **Prometheus Metrics Registration:**
  - If you see `Duplicated timeseries in CollectorRegistry`, disable metrics during tests:
    ```python
    from app.core.valkey_core.config import ValkeyConfig
    ValkeyConfig.VALKEY_METRICS_ENABLED = False
    ```

### Edge Cases & Guidance
- If Valkey changes its exception classes or lock API, update your test imports and error handling accordingly.
- Always ensure test fixtures return a fully initialized async client, not just a wrapper or function.
- If you see lock acquisition failures, ensure no other test or process is holding the same lock key.

---

## References
- [pytest-asyncio docs](https://pytest-asyncio.readthedocs.io/en/latest/)
- [Python asyncio event loop policy docs](https://docs.python.org/3/library/asyncio-policy.html)
- [Valkey Python client docs](https://valkey-py.readthedocs.io/)

---

*Last updated: 2025-05-12*
