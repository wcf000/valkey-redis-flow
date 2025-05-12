# Debugging Valkey Test Failures (Windows & Pytest-Asyncio)

This document summarizes the debugging strategies, issues encountered, and solutions that worked when running and fixing async Valkey tests in this codebase.

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

## References
- [pytest-asyncio docs](https://pytest-asyncio.readthedocs.io/en/latest/)
- [Python asyncio event loop policy docs](https://docs.python.org/3/library/asyncio-policy.html)
- [Valkey Python client docs](https://valkey-py.readthedocs.io/)

---

*Last updated: 2025-05-11*
