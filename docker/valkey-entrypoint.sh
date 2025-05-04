#!/bin/sh
# Entrypoint for Valkey container supporting both VALKEY_* and REDIS_* env variables for backward compatibility.
# Maps REDIS_* to VALKEY_* if VALKEY_* is unset. Then launches valkey-server with all advanced options.

# Map REDIS_* to VALKEY_* if VALKEY_* is unset (for drop-in Redis compatibility)
: "${VALKEY_PASSWORD:=${REDIS_PASSWORD}}"
: "${VALKEY_PORT:=${REDIS_PORT:-6379}}"
: "${VALKEY_DATABASES:=${REDIS_DATABASES:-16}}"

# Additional advanced options (can be extended)
: "${VALKEY_MAXMEMORY:=256mb}"
: "${VALKEY_MAXMEMORY_POLICY:=allkeys-lru}"

exec valkey-server \
    --appendonly yes \
    --requirepass "$VALKEY_PASSWORD" \
    --maxmemory "$VALKEY_MAXMEMORY" \
    --maxmemory-policy "$VALKEY_MAXMEMORY_POLICY" \
    --port "$VALKEY_PORT" \
    --databases "$VALKEY_DATABASES" \
    "$@"
