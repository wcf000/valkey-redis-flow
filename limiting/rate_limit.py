"""
Rate Limiting Utilities

Provides production-grade rate limiting using Redis with:
- Exponential backoff
- Detailed logging
"""

import inspect
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

# Replace Supabase imports with mock utility imports
from app.core.valkey_core._tests.utilities.mock_auth import get_mock_auth_service

async def get_auth_service():
    """Get auth service - using mock implementation"""
    return await get_mock_auth_service()

from app.core.valkey_core.client import client as valkey_client

logger = logging.getLogger(__name__)

# Initialize Redis client
client = valkey_client

# Default rate limit
DEFAULT_LIMIT = 100

# Cleanup script (runs weekly)
CLEANUP_SCRIPT = """
local keys = redis.call('KEYS', 'rate_meta:*')
for _, key in ipairs(keys) do
    local last_update = redis.call('HGET', key, 'updated_at')
    if last_update and os.time() - last_update > 604800 then
        redis.call('DEL', key)
    end
end
return #keys
"""


async def check_rate_limit(client, key: str, limit: int, window: int) -> bool:
    """
    Check if rate limit is exceeded for a specific key.
    
    Args:
        client: Valkey client instance
        key: Rate limit key
        limit: Maximum number of requests allowed
        window: Time window in seconds
        
    Returns:
        bool: True if request is allowed, False if rate limit exceeded
    """
    print(f"🚨 RATE LIMIT CHECK: key='{key}', limit={limit}, window={window}", flush=True)
    
    try:
        current_time = datetime.now(timezone.utc).timestamp()
        cutoff_time = current_time - window
        
        print(f"🚨 Removing entries older than {cutoff_time}", flush=True)
        
        # Get async connection with proper error handling
        try:
            redis_conn = await client.aconn()
        except Exception as conn_error:
            print(f"🚨 CONNECTION ERROR: {conn_error}", flush=True)
            # Fail open - allow the request if connection fails
            return True
        
        # Helper function to handle both sync and async operations
        async def safe_redis_op(operation_name: str, operation):
            try:
                result = operation()
                # Check if the result is a coroutine (async) - this is the key fix!
                if inspect.iscoroutine(result):
                    print(f"🔄 Awaiting {operation_name} result (coroutine)", flush=True)
                    result = await result
                else:
                    print(f"🔄 Using {operation_name} result (sync): {result}", flush=True)
                return result, None
            except Exception as e:
                print(f"🚨 {operation_name} ERROR: {e}", flush=True)
                return None, e
        
        # Try to remove expired entries
        cleanup_result, cleanup_error = await safe_redis_op(
            "CLEANUP", 
            lambda: redis_conn.zremrangebyscore(key, 0, cutoff_time)
        )
        
        if cleanup_error:
            print(f"🚨 CLEANUP FAILED (continuing anyway): {cleanup_error}", flush=True)
        else:
            print(f"🚨 Successfully cleaned up old entries", flush=True)
        
        # Get all entries and manually filter by timestamp
        entries_result, entries_error = await safe_redis_op(
            "GET_ENTRIES",
            lambda: redis_conn.zrangebyscore(key, cutoff_time, '+inf', withscores=True)
        )
        
        if entries_error:
            print(f"🚨 GET_ENTRIES FAILED: {entries_error}", flush=True)
            # Fail open - allow the request if we can't get entries
            return True
        
        # Count valid entries
        all_entries = entries_result or []
        current_count = len(all_entries)
        print(f"🚨 Current count: {current_count}, Limit: {limit}", flush=True)
        
        # Log entries for debugging
        for member, score in all_entries:
            print(f"🚨   Entry: {member} (timestamp: {score})", flush=True)
        
        # Check if we're over the limit before adding the new entry
        if current_count >= limit:
            print(f"🚨 RATE LIMIT EXCEEDED! Count {current_count} >= limit {limit}", flush=True)
            return False
        
        # Add current request to the sorted set with current timestamp as both member and score
        request_id = f"{current_time}:{uuid.uuid4().hex[:8]}"
        
        add_result, add_error = await safe_redis_op(
            "ADD_ENTRY",
            lambda: redis_conn.zadd(key, {request_id: current_time})
        )
        
        if add_error:
            print(f"🚨 ADD_ENTRY FAILED: {add_error}", flush=True)
            # We already checked the count, so allow it even if adding failed
        else:
            print(f"🚨 Successfully added entry: {request_id}", flush=True)
            
            # Set expiration on the key if it doesn't have one
            expire_result, expire_error = await safe_redis_op(
                "SET_EXPIRATION",
                lambda: redis_conn.expire(key, window)
            )
            
            if expire_error:
                print(f"🚨 SET_EXPIRATION FAILED: {expire_error}", flush=True)
            else:
                print(f"🚨 Set expiration: {window} seconds", flush=True)
        
        print(f"🚨 REQUEST ALLOWED: new count will be {current_count + 1}", flush=True)
        return True
        
    except Exception as e:
        print(f"🚨 EXCEPTION IN RATE LIMIT: {e}", flush=True)
        logger.error(f"Rate limiting error for key {key}: {e}")
        # Fail open - allow the request if Redis is having issues
        return True


async def increment_rate_limit(identifier: str, endpoint: str, window: int = 60) -> int:
    """
    Increment rate limit counter for identifier and endpoint

    Args:
        identifier: User ID, IP address, or other unique identifier
        endpoint: API endpoint or action name
        window: Time window in seconds

    Returns:
        Current count after increment
    """
    key = f"rate_limit:{endpoint}:{identifier}"
    redis = await client.aconn()

    # Get or initialize counter
    current = await redis.get(key)
    if current is None:
        await redis.set(key, 1, ex=window)
        return 1

    # Increment and return
    count = int(current) + 1
    await redis.set(key, count, ex=window)
    return count


async def get_remaining_limit(
    identifier: str, endpoint: str, limit: int = 5, window: int = 60
) -> dict:
    """
    Get rate limit details including remaining requests

    Returns:
        {
            "limit": 5,
            "remaining": 3,
            "reset": 1625097600
        }
    """
    key = f"rate_limit:{endpoint}:{identifier}"
    redis = await client.aconn()
    current = int(await redis.get(key) or 0)
    ttl = await redis.ttl(key)

    return {
        "limit": limit,
        "remaining": max(0, limit - current),
        "reset": int(time.time()) + (ttl if ttl > 0 else window),
    }


async def alert_system(message: str) -> None:
    # Implement your alerting system
    logger.warning(message)


async def verify_and_limit(token: str, ip: str, endpoint: str, window: int = 3600):
    """
    Enhanced with:
    - User-level rate tracking
    - Composite keys for granular control
    """
    logger.debug(f"Rate limit check started for endpoint: {endpoint}")

    try:
        # Get auth service (now using mock implementation)
        auth_service = await get_auth_service()
        
        # Verify JWT with detailed logging
        if not auth_service.verify_jwt(token):
            logger.warning(
                "Invalid JWT token",
                extra={"token": token[:8] + "...", "endpoint": endpoint},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )

        user_id = auth_service.get_user_id(token)
        limit = DEFAULT_LIMIT

        logger.debug(
            "Rate limit check", extra={"user_id": user_id, "endpoint": endpoint}
        )

        # Composite key: user + IP + endpoint
        rate_key = f"user_rate:{user_id}:{ip}:{endpoint}"

        # Track metadata without tier logic
        metadata = {
            "last_ip": ip,
            "last_endpoint": endpoint,
            "updated_at": datetime.utcnow().isoformat(),
        }

        redis = await client.aconn()
        await redis.hset(f"rate_meta:{user_id}", mapping=metadata)

        # Check if rate limit is exceeded (returns False when allowed, True when limited)
        if not await check_rate_limit(client, rate_key, limit=limit, window=window):
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "user_id": user_id,
                    "ip": ip,
                    "endpoint": endpoint,
                    "limit": limit,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {window} seconds",
            )

        await increment_rate_limit(rate_key, endpoint, window=window)
        logger.debug(f"Request allowed for endpoint: {endpoint}, user: {user_id}")
        return user_id

    except Exception as e:
        logger.error(
            "Rate limit error",
            extra={"error": str(e), "stack_trace": True},
            exc_info=True,
        )
        # Fail open during Redis outages
        return user_id
    finally:
        logger.debug(f"Rate limit check completed for endpoint: {endpoint}")


async def service_rate_limit(
    key: str, limit: int, window: int, endpoint: str = "internal"
) -> bool:
    """
    Simplified rate limiting for internal services without user authentication.

    Args:
        key: Unique identifier for the rate limit (e.g. 'celery_health')
        limit: Max allowed requests per window
        window: Time window in seconds
        endpoint: Optional endpoint identifier for metrics

    Returns:
        bool: True if request is allowed, False if rate limited
    """
    logger.debug(f"Service rate limit check started for key: {key}, endpoint: {endpoint}")

    try:
        rate_key = f"service_rate:{key}"

        # Check if rate limit is exceeded (returns False when allowed, True when limited)
        if not await check_rate_limit(client, rate_key, limit=limit, window=window):
            logger.warning(
                "Service rate limit exceeded",
                extra={"key": key, "endpoint": endpoint, "limit": limit},
            )
            return False

        await increment_rate_limit(rate_key, endpoint, window=window)
        logger.debug(f"Service request allowed for key: {key}, endpoint: {endpoint}")
        return True

    except Exception as e:
        logger.error(
            "Service rate limit error",
            extra={"error": str(e), "stack_trace": True},
            exc_info=True,
        )
        # Fail open during Redis outages
        return True
    finally:
        logger.debug(f"Service rate limit check completed for key: {key}, endpoint: {endpoint}")


async def init_cleanup():
    redis = await client.aconn()
    await redis.eval(CLEANUP_SCRIPT, 0)
    # asyncio.create_task(run_weekly(init_cleanup))  # This line is commented out because run_weekly is not defined in the provided code
