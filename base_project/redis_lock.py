import logging
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Optional

import redis

logger = logging.getLogger(__name__)


class RedisLock:
    def __init__(
        self,
        redis_client: redis.Redis,
        key: str,
        timeout: int = 3600,
        renewal_interval: int = 30,
        blocking: bool = False,
        blocking_timeout: Optional[int] = None,
    ):
        self.redis_client = redis_client
        self.key = f"lock:{key}"
        self.timeout = timeout
        self.renewal_interval = renewal_interval
        self.blocking = blocking
        self.blocking_timeout = blocking_timeout
        self.token = str(uuid.uuid4())

    def acquire(self) -> bool:
        if self.blocking:
            return self._acquire_blocking()
        else:
            return self._acquire_non_blocking()

    def _acquire_non_blocking(self) -> bool:
        result = self.redis_client.set(self.key, self.token, nx=True, ex=self.timeout)
        if result:
            logger.info(f"Acquired lock for key: {self.key}")
            return True
        else:
            current_holder = self.redis_client.get(self.key)
            ttl = self.redis_client.ttl(self.key)
            logger.warning(
                f"Failed to acquire lock for key: {self.key}. " f"Current holder: {current_holder}, TTL: {ttl}s"
            )
            return False

    def _acquire_blocking(self) -> bool:
        start_time = time.time()
        while True:
            if self._acquire_non_blocking():
                return True
            if self.blocking_timeout and time.time() - start_time > self.blocking_timeout:
                logger.error(f"Timeout while waiting for lock: {self.key} " f"after {self.blocking_timeout}s")
                return False
            time.sleep(1)

    def release(self) -> bool:
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            result = self.redis_client.eval(lua_script, 1, self.key, self.token)
            if result:
                logger.info(f"Released lock for key: {self.key}")
                return True
            else:
                logger.warning(f"Failed to release lock for key: {self.key} - token mismatch")
                return False
        except Exception as e:
            logger.error(f"Error releasing lock for key {self.key}: {str(e)}")
            return False

    def extend(self, additional_time: Optional[int] = None) -> bool:
        additional_time = additional_time or self.timeout
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        try:
            result = self.redis_client.eval(lua_script, 1, self.key, self.token, additional_time)
            if result:
                logger.debug(f"Extended lock for key: {self.key} by {additional_time}s")
                return True
            else:
                logger.warning(f"Failed to extend lock for key: {self.key}")
                return False
        except Exception as e:
            logger.error(f"Error extending lock for key {self.key}: {str(e)}")
            return False

    def is_locked(self) -> bool:
        return self.redis_client.exists(self.key) > 0

    def is_owned(self) -> bool:
        current_value = self.redis_client.get(self.key)
        return current_value is not None and current_value.decode() == self.token

    def get_info(self) -> dict:
        current_holder = self.redis_client.get(self.key)
        ttl = self.redis_client.ttl(self.key)
        return {
            "locked": self.is_locked(),
            "owned": self.is_owned(),
            "holder": current_holder.decode() if current_holder else None,
            "ttl": ttl if ttl > 0 else None,
            "key": self.key,
        }

    def force_release(self) -> bool:
        try:
            result = self.redis_client.delete(self.key)
            if result:
                logger.warning(f"Force-released lock for key: {self.key}")
                return True
            else:
                logger.info(f"No lock to force-release for key: {self.key}")
                return False
        except Exception as e:
            logger.error(f"Error force-releasing lock for key {self.key}: {str(e)}")
            return False

    @contextmanager
    def __call__(self):
        acquired = self.acquire()
        if not acquired:
            raise RuntimeError(f"Could not acquire lock for {self.key}")
        try:
            yield self
        finally:
            self.release()


class AutoRenewingRedisLock(RedisLock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._renewal_thread = None
        self._stop_event = threading.Event()

    def acquire(self) -> bool:
        result = super().acquire()
        if result:
            self._start_renewal()
        return result

    def release(self) -> bool:
        self._stop_renewal_thread()
        return super().release()

    def _start_renewal(self):
        self._stop_event.clear()

        def renew_lock():
            while not self._stop_event.is_set():
                if self._stop_event.wait(timeout=self.renewal_interval):
                    break
                try:
                    if not self.extend():
                        logger.error(f"Failed to renew lock for key: {self.key}")
                        self._stop_event.set()
                        break
                except redis.ConnectionError as e:
                    logger.error(f"Lost Redis connection during renewal: {str(e)}")
                    self._stop_event.set()
                    break
                except Exception as e:
                    logger.error(f"Unexpected error during lock renewal: {str(e)}")
                    self._stop_event.set()
                    break

        self._renewal_thread = threading.Thread(target=renew_lock, daemon=True)
        self._renewal_thread.start()
        logger.debug(f"Started auto-renewal thread for lock: {self.key}")

    def _stop_renewal_thread(self):
        if self._renewal_thread:
            self._stop_event.set()
            self._renewal_thread.join(timeout=1)
            self._renewal_thread = None
            logger.debug(f"Stopped auto-renewal thread for lock: {self.key}")


def distributed_task(
    redis_client: redis.Redis,
    lock_key: str,
    timeout: int = 3600,
    renewal_interval: int = 30,
):
    def decorator(func):
        def wrapper(*args, **kwargs):
            lock = AutoRenewingRedisLock(
                redis_client=redis_client,
                key=lock_key,
                timeout=timeout,
                renewal_interval=renewal_interval,
                blocking=False,
            )
            if not lock.acquire():
                lock_info = lock.get_info()
                logger.warning(f"Task {func.__name__} skipped - lock already held. " f"Lock info: {lock_info}")
                return {
                    "status": "skipped",
                    "reason": "lock_held",
                    "lock_info": lock_info,
                }
            try:
                return func(*args, **kwargs)
            finally:
                lock.release()

        return wrapper

    return decorator
