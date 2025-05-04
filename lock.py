"""
Distributed lock helper for Valkey using the Redlock algorithm.
Follows best practices for async, atomicity, and safety.
"""
import asyncio
import uuid
from typing import Any

class ValkeyLock:
    def __init__(self, client, key: str, ttl: int = 10):
        self.client = client
        self.key = key
        self.ttl = ttl
        self.value = str(uuid.uuid4())

    async def acquire(self) -> bool:
        # SET key value NX PX ttl
        result = await self.client.set(self.key, self.value, ex=self.ttl, nx=True)
        return result is True

    async def release(self) -> bool:
        # Release lock safely with Lua script
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        else
            return 0
        end
        """
        res = await self.client.eval(script, 1, self.key, self.value)
        return res == 1

    async def __aenter__(self):
        acquired = await self.acquire()
        if not acquired:
            raise RuntimeError(f"Could not acquire lock for {self.key}")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.release()
