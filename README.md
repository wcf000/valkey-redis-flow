# Valkey Core (High-Performance Caching & Rate Limiting)

**Production-ready Python/FastAPI Redis-compatible Caching, Limiting, and Data Structures**

This module provides robust, scalable, and observable caching, distributed locks, and rate limiting for Python microservices using Valkey (open-source Redis alternative).

---

## 📁 Folder Structure & Conventions

```
valkey_core/
├── _docs/           # Markdown docs, best practices, diagrams, usage
├── _tests/          # Unit/integration tests for all core logic
├── config.py        # Singleton config (class-based, imports from global settings)
├── docker/          # Dockerfile, docker-compose, Valkey configs, .env.example
├── models/          # Pydantic models or cache schemas
├── exceptions/      # Custom exceptions for cache/limiting
├── algorithims/     # Caching, locking, and limiting algorithms
├── cache/           # Core cache logic, adapters, and utilities
├── limiting/        # Rate limiting, circuit breakers, and related logic
├── health_check.py  # Health endpoints and readiness checks
├── metrics.py       # Prometheus metrics integration
├── valkey.conf      # Valkey server config
├── <core>.py        # Main implementation (client.py, etc.)
├── README.md        # Main readme (this file)
```

- **_docs/**: All documentation, diagrams, and best practices for this module.
- **_tests/**: All tests for this module, including integration, failover, and performance tests.
- **config.py**: Singleton config pattern, imports from global settings, exposes all constants for this module.
- **docker/**: Containerization assets (Dockerfile, docker-compose, valkey.conf, .env.example, etc).
- **models/**: Pydantic models or schemas for cache/lock payloads.
- **exceptions/**: Custom exception classes for robust error handling.
- **algorithims/**: Pluggable caching, locking, and rate limiting algorithms.
- **cache/**: Core cache logic, adapters, and utilities.
- **limiting/**: Rate limiting, circuit breaker, and related patterns.
- **health_check.py**: Health endpoints and readiness checks.
- **metrics.py**: Prometheus metrics and monitoring integration.
- **valkey.conf**: Valkey server configuration.
- **<core>.py**: Main implementation modules (e.g., client.py).

---

## 🏗️ Singleton & Config Pattern
- Use a single class (e.g., `ValkeyConfig`) in `config.py` to centralize all env, server, and integration settings.
- Import from global settings to avoid duplication and ensure DRY config.
- Document all config keys in `_docs/usage.md` and in this README.

---

## 📄 Documentation & Testing
- Place all best practices, diagrams, and usage guides in `_docs/`.
- All tests (unit, integration, smoke, failover, performance) go in `_tests/` with clear naming.
- Use `_tests/_docs/` for test-specific docs if needed.

---

## 🐳 Docker & Valkey Configs
- Place Dockerfile(s), docker-compose, and Valkey configs in `docker/`.
- Provide `.env.example` for local/dev/prod setups.
- Place all Valkey server configs in root or `docker/` (valkey.conf).

---

## 🔐 Required Environment Variables

See `.env.example` for all required environment variables for Valkey, authentication, and integration.

---

## 📦 Usage

1. **Clone this repo or add as a submodule.**
2. **Configure environment variables as per `.env.example`.**
3. **Build and start services:**
   ```bash
   docker-compose -f docker/docker-compose.valkey.yml up --build
   ```
4. **Access Valkey at:** redis://localhost:6379 (default)
5. **Run integration and failover tests as needed.**

---

## 🏷️ Tags

`python, fastapi, valkey, redis, caching, rate-limiting, distributed-locks, docker, pytest, pydantic, production-ready`
