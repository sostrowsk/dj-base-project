"""Behavior tests for ``base_project.redis_lock`` (W19-BP2).

Consolidates the former leasing-root ``test_redis_lock.py`` demo script into
real assertions. Uses an in-memory fake Redis client — no running Redis
required, no Django settings required.
"""

import time
from unittest import TestCase

from base_project.redis_lock import AutoRenewingRedisLock, RedisLock, distributed_task


class FakeRedis:
    """Minimal in-memory stand-in for the redis client API used by RedisLock."""

    def __init__(self):
        self.store = {}
        self.ttls = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value.encode() if isinstance(value, str) else value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def get(self, key):
        return self.store.get(key)

    def ttl(self, key):
        if key not in self.store:
            return -2
        return self.ttls.get(key, -1)

    def exists(self, key):
        return 1 if key in self.store else 0

    def delete(self, key):
        if key in self.store:
            del self.store[key]
            self.ttls.pop(key, None)
            return 1
        return 0

    def eval(self, script, numkeys, key, *args):
        # RedisLock uses exactly two lua scripts: token-checked DEL (release)
        # and token-checked EXPIRE (extend).
        token = args[0]
        current = self.store.get(key)
        if current is None or current.decode() != str(token):
            return 0
        if '"del"' in script:
            return self.delete(key)
        if '"expire"' in script:
            self.ttls[key] = int(args[1])
            return 1
        raise AssertionError(f"unexpected lua script: {script!r}")


class RedisLockBehaviorTests(TestCase):
    def setUp(self):
        self.redis = FakeRedis()

    def test_acquire_sets_prefixed_key_with_timeout(self):
        lock = RedisLock(self.redis, "indexing:all_documents", timeout=3600)
        assert lock.acquire() is True
        assert lock.key == "lock:indexing:all_documents"
        assert self.redis.exists("lock:indexing:all_documents") == 1
        assert self.redis.ttl("lock:indexing:all_documents") == 3600

    def test_second_acquire_on_held_lock_fails(self):
        first = RedisLock(self.redis, "job")
        second = RedisLock(self.redis, "job")
        assert first.acquire() is True
        assert second.acquire() is False

    def test_release_only_removes_own_token(self):
        owner = RedisLock(self.redis, "job")
        stranger = RedisLock(self.redis, "job")
        assert owner.acquire() is True
        assert stranger.release() is False
        assert owner.is_locked() is True
        assert owner.release() is True
        assert owner.is_locked() is False

    def test_extend_refreshes_ttl_only_for_owner(self):
        owner = RedisLock(self.redis, "job", timeout=100)
        stranger = RedisLock(self.redis, "job", timeout=100)
        assert owner.acquire() is True
        assert owner.extend(500) is True
        assert self.redis.ttl(owner.key) == 500
        assert stranger.extend(999) is False
        assert self.redis.ttl(owner.key) == 500

    def test_is_owned_distinguishes_holder(self):
        owner = RedisLock(self.redis, "job")
        stranger = RedisLock(self.redis, "job")
        owner.acquire()
        assert owner.is_owned() is True
        assert stranger.is_owned() is False

    def test_get_info_reports_holder_and_ttl(self):
        lock = RedisLock(self.redis, "job", timeout=60)
        lock.acquire()
        info = lock.get_info()
        assert info["locked"] is True
        assert info["owned"] is True
        assert info["holder"] == lock.token
        assert info["ttl"] == 60
        assert info["key"] == "lock:job"

    def test_force_release_removes_foreign_lock(self):
        owner = RedisLock(self.redis, "job")
        stranger = RedisLock(self.redis, "job")
        owner.acquire()
        assert stranger.force_release() is True
        assert owner.is_locked() is False

    def test_context_manager_acquires_and_releases(self):
        lock = RedisLock(self.redis, "job")
        with lock():
            assert lock.is_owned() is True
        assert lock.is_locked() is False

    def test_context_manager_raises_when_lock_held(self):
        RedisLock(self.redis, "job").acquire()
        lock = RedisLock(self.redis, "job")
        with self.assertRaises(RuntimeError):
            with lock():
                pass

    def test_blocking_acquire_times_out(self):
        RedisLock(self.redis, "job").acquire()
        lock = RedisLock(self.redis, "job", blocking=True, blocking_timeout=1)
        start = time.time()
        assert lock.acquire() is False
        assert time.time() - start >= 1


class AutoRenewingRedisLockTests(TestCase):
    def test_release_stops_renewal_thread(self):
        lock = AutoRenewingRedisLock(FakeRedis(), "job", renewal_interval=1)
        assert lock.acquire() is True
        assert lock._renewal_thread is not None
        assert lock._renewal_thread.is_alive() is True
        assert lock.release() is True
        assert lock._renewal_thread is None

    def test_failed_acquire_starts_no_renewal_thread(self):
        redis_client = FakeRedis()
        RedisLock(redis_client, "job").acquire()
        lock = AutoRenewingRedisLock(redis_client, "job")
        assert lock.acquire() is False
        assert lock._renewal_thread is None


class DistributedTaskDecoratorTests(TestCase):
    def test_runs_function_and_releases_lock(self):
        redis_client = FakeRedis()

        @distributed_task(redis_client, "job")
        def work(value):
            assert redis_client.exists("lock:job") == 1
            return value * 2

        assert work(21) == 42
        assert redis_client.exists("lock:job") == 0

    def test_skips_when_lock_already_held(self):
        redis_client = FakeRedis()
        RedisLock(redis_client, "job").acquire()
        calls = []

        @distributed_task(redis_client, "job")
        def work():
            calls.append(1)

        result = work()
        assert result["status"] == "skipped"
        assert result["reason"] == "lock_held"
        assert calls == []

    def test_releases_lock_even_when_function_raises(self):
        redis_client = FakeRedis()

        @distributed_task(redis_client, "job")
        def boom():
            raise ValueError("kaputt")

        with self.assertRaises(ValueError):
            boom()
        assert redis_client.exists("lock:job") == 0
