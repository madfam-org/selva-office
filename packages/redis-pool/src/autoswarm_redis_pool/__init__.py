"""Shared Redis connection pool for AutoSwarm services."""

from .pool import RedisPool, get_redis_pool

__all__ = ["RedisPool", "get_redis_pool"]
