import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import pybreaker
import redis
from redis.exceptions import ConnectionError

from .redis_lock import AutoRenewingRedisLock, RedisLock
from .retry_utils import RetryStrategy

logger = logging.getLogger(__name__)

# Create circuit breaker
redis_breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=30, exclude=[ConnectionError])

# Default retry settings
DEFAULT_INITIAL_RETRY_DELAY = 0.1  # 100ms
DEFAULT_MAX_RETRY_DELAY = 30.0  # 30 seconds
DEFAULT_MAX_RETRIES = 5
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_JITTER = 0.1  # 10% jitter


class RedisClient:
    def __init__(
        self,
        host="localhost",
        port=6379,
        db=0,
        password=None,
        socket_timeout=10,
        enable_retry=True,
        initial_retry_delay=DEFAULT_INITIAL_RETRY_DELAY,
        max_retry_delay=DEFAULT_MAX_RETRY_DELAY,
        max_retries=DEFAULT_MAX_RETRIES,
        backoff_factor=DEFAULT_BACKOFF_FACTOR,
        jitter=DEFAULT_JITTER,
    ):
        """
        Initialize Redis client with connection parameters and retry settings.

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (optional)
            socket_timeout: Socket timeout in seconds
            enable_retry: Whether to enable automatic retries
            initial_retry_delay: Initial delay between retries in seconds
            max_retry_delay: Maximum delay between retries in seconds
            max_retries: Maximum number of retry attempts
            backoff_factor: Factor to increase delay between retries
            jitter: Amount of randomness to add to delay times (0-1)
        """
        self.connection_params = {
            "host": host,
            "port": port,
            "db": db,
            "password": password,
            "socket_timeout": socket_timeout,
            "socket_connect_timeout": socket_timeout,
            "socket_keepalive": True,
            "socket_keepalive_options": {},
            "health_check_interval": 30,
        }
        self.client: Optional[redis.Redis] = None
        self.enable_retry = enable_retry
        self.metrics = {
            "connect_attempts": 0,
            "connect_failures": 0,
            "connect_retries": 0,
            "last_connect_time": 0,
            "last_error": None,
            "current_retry_count": 0,
        }

        # Initialize retry strategy if enabled
        self.retry_strategy = (
            RetryStrategy(
                initial_delay=initial_retry_delay,
                max_delay=max_retry_delay,
                max_retries=max_retries,
                backoff_factor=backoff_factor,
                jitter=jitter,
            )
            if enable_retry
            else None
        )

    @redis_breaker
    def connect(self) -> redis.Redis:
        """
        Connect to Redis and return a client instance.

        Uses exponential backoff retry if enabled.

        Returns:
            redis.Redis: An established Redis client

        Raises:
            Exception: If connection fails after retries
        """
        # Reset retry strategy before each connection attempt
        if self.retry_strategy:
            self.retry_strategy.reset()

        return self._connect_with_retry()

    def _connect_with_retry(self) -> redis.Redis:
        """
        Internal method to connect with retry logic.

        Returns:
            redis.Redis: An established Redis client

        Raises:
            Exception: If connection fails after retries
        """
        # Update metrics
        self.metrics["connect_attempts"] += 1
        start_time = time.time()

        def connect_attempt():
            if self.client is None:
                logger.info("Establishing new Redis connection")
                self.client = redis.Redis(**self.connection_params)
            # Test the connection
            self.client.ping()
            return self.client

        if not self.enable_retry or self.retry_strategy is None:
            # No retry logic, just try once
            try:
                return connect_attempt()
            except Exception as e:
                self.metrics["connect_failures"] += 1
                self.metrics["last_error"] = str(e)
                logger.error(f"Failed to connect to Redis: {str(e)}")
                self.close()
                raise

        # With retry logic
        try:
            client = self.retry_strategy.execute(connect_attempt)
            # Update metrics on success
            self.metrics["last_connect_time"] = time.time() - start_time
            self.metrics["current_retry_count"] = 0  # Reset on success
            return client
        except Exception as e:
            # Update metrics on failure
            self.metrics["connect_failures"] += 1
            self.metrics["last_error"] = str(e)
            self.metrics["connect_retries"] += self.retry_strategy.retry_count
            self.metrics["current_retry_count"] = self.retry_strategy.retry_count
            logger.error(f"Failed to connect to Redis after {self.retry_strategy.retry_count} retries: {str(e)}")
            self.close()
            raise

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set a key-value pair in Redis with optional expiration."""
        if not self.enable_retry or self.retry_strategy is None:
            # Without retry
            try:
                client = self.connect()
                return client.set(key, value, ex=ex)
            except Exception as e:
                logger.error(f"Failed to set value in Redis: {str(e)}")
                self.close()
                raise

        # With retry logic
        self.retry_strategy.reset()

        def set_attempt():
            client = self.connect()
            return client.set(key, value, ex=ex)

        try:
            return self.retry_strategy.execute(set_attempt)
        except Exception as e:
            logger.error(f"Failed to set value in Redis after retries: {str(e)}")
            self.close()
            raise

    def get(self, key: str) -> Optional[bytes]:
        """Get a value from Redis."""
        if not self.enable_retry or self.retry_strategy is None:
            # Without retry
            try:
                client = self.connect()
                return client.get(key)
            except Exception as e:
                logger.error(f"Failed to get value from Redis: {str(e)}")
                self.close()
                raise

        # With retry logic
        self.retry_strategy.reset()

        def get_attempt():
            client = self.connect()
            return client.get(key)

        try:
            return self.retry_strategy.execute(get_attempt)
        except Exception as e:
            logger.error(f"Failed to get value from Redis after retries: {str(e)}")
            self.close()
            raise

    def delete(self, *keys: str) -> int:
        """Delete one or more keys from Redis."""
        if not self.enable_retry or self.retry_strategy is None:
            # Without retry
            try:
                client = self.connect()
                return client.delete(*keys)
            except Exception as e:
                logger.error(f"Failed to delete keys from Redis: {str(e)}")
                self.close()
                raise

        # With retry logic
        self.retry_strategy.reset()

        def delete_attempt():
            client = self.connect()
            return client.delete(*keys)

        try:
            return self.retry_strategy.execute(delete_attempt)
        except Exception as e:
            logger.error(f"Failed to delete keys from Redis after retries: {str(e)}")
            self.close()
            raise

    def exists(self, *keys: str) -> int:
        """Check if one or more keys exist."""
        if not self.enable_retry or self.retry_strategy is None:
            # Without retry
            try:
                client = self.connect()
                return client.exists(*keys)
            except Exception as e:
                logger.error(f"Failed to check key existence in Redis: {str(e)}")
                self.close()
                raise

        # With retry logic
        self.retry_strategy.reset()

        def exists_attempt():
            client = self.connect()
            return client.exists(*keys)

        try:
            return self.retry_strategy.execute(exists_attempt)
        except Exception as e:
            logger.error(f"Failed to check key existence in Redis after retries: {str(e)}")
            self.close()
            raise

    def publish(self, channel: str, message: str) -> int:
        """Publish a message to a Redis channel."""
        if not self.enable_retry or self.retry_strategy is None:
            # Without retry
            try:
                client = self.connect()
                return client.publish(channel, message)
            except Exception as e:
                logger.error(f"Failed to publish message to Redis: {str(e)}")
                self.close()
                raise

        # With retry logic
        self.retry_strategy.reset()

        def publish_attempt():
            client = self.connect()
            return client.publish(channel, message)

        try:
            return self.retry_strategy.execute(publish_attempt)
        except Exception as e:
            logger.error(f"Failed to publish message to Redis after retries: {str(e)}")
            self.close()
            raise

    def close(self):
        """Close the connection."""
        if self.client:
            try:
                self.client.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {str(e)}")
        self.client = None

    def get_metrics(self) -> Dict[str, Any]:
        """Get connection metrics."""
        return self.metrics

    def get_lock(
        self,
        key: str,
        timeout: int = 3600,
        auto_renew: bool = True,
        renewal_interval: int = 30,
        blocking: bool = False,
        blocking_timeout: Optional[int] = None,
    ) -> RedisLock:
        """
        Get a distributed lock.

        Args:
            key: Lock key
            timeout: Lock timeout in seconds
            auto_renew: Whether to auto-renew the lock
            renewal_interval: Interval for auto-renewal in seconds
            blocking: Whether to block waiting for the lock
            blocking_timeout: Maximum time to wait for the lock

        Returns:
            RedisLock or AutoRenewingRedisLock instance
        """
        client = self.connect()
        if auto_renew:
            return AutoRenewingRedisLock(
                redis_client=client,
                key=key,
                timeout=timeout,
                renewal_interval=renewal_interval,
                blocking=blocking,
                blocking_timeout=blocking_timeout,
            )
        else:
            return RedisLock(
                redis_client=client,
                key=key,
                timeout=timeout,
                renewal_interval=renewal_interval,
                blocking=blocking,
                blocking_timeout=blocking_timeout,
            )


def get_redis_client_from_env() -> RedisClient:
    """
    Create a Redis client from environment variables.

    The following environment variables are supported:
    - CELERY_BROKER_URL: The Redis URL (default: redis://localhost:6379/0)
    - REDIS_HOST: Redis host (overrides URL)
    - REDIS_PORT: Redis port (overrides URL)
    - REDIS_DB: Redis database number (overrides URL)
    - REDIS_PASSWORD: Redis password
    - REDIS_RETRY_ENABLED: Whether to enable retry (default: True)
    - REDIS_INITIAL_RETRY_DELAY: Initial retry delay in seconds (default: 0.1)
    - REDIS_MAX_RETRY_DELAY: Maximum retry delay in seconds (default: 30)
    - REDIS_MAX_RETRIES: Maximum number of retries (default: 5)
    - REDIS_BACKOFF_FACTOR: Backoff factor for retry delay (default: 2.0)
    - REDIS_JITTER: Jitter factor for retry delay (default: 0.1)

    Returns:
        RedisClient: A configured Redis client
    """
    # First try to get individual Redis settings
    redis_host = os.getenv("REDIS_HOST")
    redis_port = os.getenv("REDIS_PORT")
    redis_db = os.getenv("REDIS_DB", "0")
    redis_password = os.getenv("REDIS_PASSWORD")

    # If not set, parse from CELERY_BROKER_URL
    if not redis_host:
        broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        if broker_url.startswith("redis://"):
            parsed = urlparse(broker_url)
            redis_host = parsed.hostname or "localhost"
            redis_port = str(parsed.port or 6379)
            redis_password = parsed.password
            # Extract database number from path
            if parsed.path and len(parsed.path) > 1:
                redis_db = parsed.path[1:]

    # Convert to correct types
    redis_host = redis_host or "localhost"
    redis_port = int(redis_port or 6379)
    redis_db = int(redis_db)

    # Get retry settings from environment
    enable_retry = os.getenv("REDIS_RETRY_ENABLED", "True").lower() in (
        "true",
        "1",
        "t",
        "yes",
    )
    initial_retry_delay = float(os.getenv("REDIS_INITIAL_RETRY_DELAY", str(DEFAULT_INITIAL_RETRY_DELAY)))
    max_retry_delay = float(os.getenv("REDIS_MAX_RETRY_DELAY", str(DEFAULT_MAX_RETRY_DELAY)))
    max_retries = int(os.getenv("REDIS_MAX_RETRIES", str(DEFAULT_MAX_RETRIES)))
    backoff_factor = float(os.getenv("REDIS_BACKOFF_FACTOR", str(DEFAULT_BACKOFF_FACTOR)))
    jitter = float(os.getenv("REDIS_JITTER", str(DEFAULT_JITTER)))

    return RedisClient(
        host=redis_host,
        port=redis_port,
        db=redis_db,
        password=redis_password,
        enable_retry=enable_retry,
        initial_retry_delay=initial_retry_delay,
        max_retry_delay=max_retry_delay,
        max_retries=max_retries,
        backoff_factor=backoff_factor,
        jitter=jitter,
    )
