"""
* Token Bucket Rate Limiter using VALKEY
* DRY, SOLID, CI/CD, and type safety best practices
"""
import logging
import time
from app.core.valkey_core.client import get_valkey_client

# ! Uses atomic Lua script for token refill and consume
# todo: Add fail-open logic and Prometheus metrics if needed

TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local interval = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local bucket = redis.call('HMGET', key, 'tokens', 'last')
local tokens = tonumber(bucket[1]) or capacity
local last = tonumber(bucket[2]) or now
local delta = math.max(0, now - last)
local refill = math.floor(delta / interval) * refill_rate
local new_tokens = math.min(capacity, tokens + refill)
if new_tokens > 0 then
  new_tokens = new_tokens - 1
  redis.call('HMSET', key, 'tokens', new_tokens, 'last', now)
  redis.call('EXPIRE', key, interval * 2)
  return 1
else
  redis.call('HMSET', key, 'tokens', new_tokens, 'last', now)
  redis.call('EXPIRE', key, interval * 2)
  return 0
end
""" 

async def is_allowed_token_bucket(
    key: str, capacity: int, refill_rate: int, interval: int
) -> bool:
    try:
        import time
        valkey_client = get_valkey_client()
        redis = await valkey_client.aconn()
        now = int(time.time())
        allowed = await redis.eval(
            TOKEN_BUCKET_LUA,
            1,
            key,
            capacity,
            refill_rate,
            interval,
            now,
        )
        return allowed == 1
    except Exception as e:
        import logging
        logging.warning(f"[token_bucket] VALKEY unavailable, allowing event (fail-open): {e}")
        return True
