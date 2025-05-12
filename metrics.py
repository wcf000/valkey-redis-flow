"""
Valkey metrics utilities for monitoring and test instrumentation.
Provides record_metrics and other helpers for Prometheus or logging-based metrics.
"""
from prometheus_client import Counter, CollectorRegistry
import logging

# Singleton registry for metrics
_metric_registry = None
_valkey_cache_hits = None
_valkey_cache_misses = None
_valkey_cache_sets = None
_valkey_cache_deletes = None
_valkey_cache_errors = None

def get_metric_registry():
    global _metric_registry
    if _metric_registry is None:
        _metric_registry = CollectorRegistry()
    return _metric_registry

def get_valkey_cache_hits():
    global _valkey_cache_hits
    if _valkey_cache_hits is None:
        _valkey_cache_hits = Counter(
            'valkey_cache_hits_total',
            'Number of cache hits for VALKEY operations',
            registry=get_metric_registry()
        )
    return _valkey_cache_hits

def get_valkey_cache_misses():
    global _valkey_cache_misses
    if _valkey_cache_misses is None:
        _valkey_cache_misses = Counter(
            'valkey_cache_misses_total',
            'Number of cache misses for VALKEY operations',
            registry=get_metric_registry()
        )
    return _valkey_cache_misses

def get_valkey_cache_sets():
    global _valkey_cache_sets
    if _valkey_cache_sets is None:
        _valkey_cache_sets = Counter(
            'valkey_cache_sets_total',
            'Number of cache sets for VALKEY operations',
            registry=get_metric_registry()
        )
    return _valkey_cache_sets

def get_valkey_cache_deletes():
    global _valkey_cache_deletes
    if _valkey_cache_deletes is None:
        _valkey_cache_deletes = Counter(
            'valkey_cache_deletes_total',
            'Number of cache deletes for VALKEY operations',
            registry=get_metric_registry()
        )
    return _valkey_cache_deletes

def get_valkey_cache_errors():
    global _valkey_cache_errors
    if _valkey_cache_errors is None:
        _valkey_cache_errors = Counter(
            'valkey_cache_errors_total',
            'Number of errors during VALKEY cache operations',
            registry=get_metric_registry()
        )
    return _valkey_cache_errors

def record_metrics(event: str, value: int = 1, **kwargs) -> None:
    """
    * Record a metric event for Valkey operations (stub for Prometheus integration)
    Args:
        event (str): Name of the event/metric
        value (int): Value to record (default 1)
        kwargs: Additional context (e.g., shard, key, status)
    """
    logging.info(f"[valkey.metrics] Event: {event}, Value: {value}, Context: {kwargs}")
