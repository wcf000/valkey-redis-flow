# Use official Valkey Alpine image (drop-in Redis replacement)
FROM valkey/valkey:latest-alpine

# Create data directory
RUN mkdir -p /data

# Compatibility: Accept both VALKEY_* and REDIS_* env vars for config, password, port, databases, etc.
# If only REDIS_* is set, use those for Valkey (backward compatible with Redis environments)

COPY docker/valkey-entrypoint.sh /valkey-entrypoint.sh
RUN chmod +x /valkey-entrypoint.sh

# # Optional: Copy valkey.conf for SSL/TLS support (if present)
# COPY docker/valkey.conf /usr/local/etc/valkey/valkey.conf

# Expose standard and optional TLS ports
EXPOSE ${VALKEY_PORT:-${REDIS_PORT:-6379}}
EXPOSE ${VALKEY_TLS_PORT:-6380}

# Health check (works for both Valkey and Redis CLI)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD valkey-cli -a "${VALKEY_PASSWORD:-$REDIS_PASSWORD}" -p "${VALKEY_PORT:-$REDIS_PORT}" ping || exit 1

# Use shell entrypoint to map REDIS_* to VALKEY_* if needed, then launch valkey-server
ENTRYPOINT ["/valkey-entrypoint.sh"]

# Notes:
# - Both VALKEY_* and REDIS_* env variables are supported for config, port, password, etc.
# - This enables drop-in replacement in legacy Redis environments.
# - For advanced config, mount/copy valkey.conf and adjust entrypoint/CMD as needed.
# - To enable SSL/TLS, mount your certs to /certs and use the provided valkey.conf.
# - See _docs/best_practices and https://valkey.io/docs/topics/encryption.html for advanced SSL usage and tuning.
