"""RedisStateStore 分布式会话语义测试（docs/19 P0-1 · 拍板 2026-09-07 分级降级）。

- 真实 Redis 容器验证：SET NX 锁语义、Lua 比较删除、TTL/序列化（testcontainers.redis）；
- 降级路径（无需容器）：客户端故障 → 默认降级内存；`redis_required=True` → 抛错可感知。
"""

from __future__ import annotations

import pytest
from app.practice.state import MemoryStateStore, RedisStateStore, SessionState

pytestmark = pytest.mark.redis


@pytest.fixture(scope="module")
def redis_container():
    """Redis 容器（模块级启动一次）；无 Docker/拉取失败 → skip。"""
    try:
        # testcontainers 4.15：legacy testcontainers.redis 正常（community 版有启动兼容问题；
        # legacy 类无 get_connection_url() → 手工拼 URL，2026-09-07 实测）
        from testcontainers.redis import RedisContainer
    except ImportError:  # 兼容未迁移 community 的旧版本
        from testcontainers.community.redis import RedisContainer

    try:
        with RedisContainer("redis:7-alpine") as rc:
            yield rc
    except Exception as exc:  # Docker 不可用/拉取失败 → 安全网按可选项处理
        pytest.skip(f"Docker 不可用，Redis 集成测试跳过: {exc}")


@pytest.fixture
def redis_client(redis_container):
    """每测试独立客户端——pytest-asyncio 每用例独立事件循环，redis 连接绑定创建时的 loop
    （模块级共享客户端会在第二个用例看到已关闭 loop 的连接，见 2026-09-07 实测）。"""
    import redis.asyncio as aioredis

    url = f"redis://127.0.0.1:{redis_container.get_exposed_port(6379)}/0"
    return aioredis.from_url(url, decode_responses=True)


def _state() -> SessionState:
    return SessionState(
        session_id=42,
        kind="dialog",
        state="awaiting_user",
        digest=["hi there"],
        assembled={"scenario_id": 1, "tags": ["cafe", "coffee"]},
    )


async def test_put_get_roundtrip_and_ttl(redis_client) -> None:
    """put → get 全字段往返（含嵌套 dict/list）；键带 TTL（1800s，docs/06 §10.2）。"""
    store = RedisStateStore(redis_client)
    await store.put(_state())
    got = await store.get(42)
    assert got is not None
    assert got.session_id == 42 and got.state == "awaiting_user"
    assert got.digest == ["hi there"]
    assert got.assembled == {"scenario_id": 1, "tags": ["cafe", "coffee"]}
    ttl = await redis_client.ttl("session:42")
    assert 0 < ttl <= 30 * 60
    await store.delete(42)
    assert await store.get(42) is None


async def test_lock_setnx_semantics(redis_client) -> None:
    """锁：SET NX 互斥（第二次返回 None）；Lua 比较删除——错 nonce 删不掉、对 nonce 可释放。"""
    store = RedisStateStore(redis_client)
    first = await store.acquire_lock(42)
    assert first is not None
    assert await store.acquire_lock(42) is None  # 互斥
    await store.release_lock(42, "wrong-nonce")  # 错 nonce：不得释放
    assert await store.acquire_lock(42) is None
    await store.release_lock(42, first)  # 正确 nonce
    assert await store.acquire_lock(42) is not None  # 释放成功可重获
    await store.delete(42)


async def test_degrade_to_memory_on_client_failure(monkeypatch) -> None:
    """健壮性：客户端故障 → 默认降级内存（不抛错，限频告警）；状态语义保持。"""

    class _Broken:
        async def get(self, *a, **k):
            raise RuntimeError("redis down")

        async def set(self, *a, **k):
            raise RuntimeError("redis down")

        async def pipeline(self, *a, **k):
            raise RuntimeError("redis down")

        async def eval(self, *a, **k):
            raise RuntimeError("redis down")

    store = RedisStateStore(_Broken(), fallback=MemoryStateStore())
    await store.put(_state())  # 降级写入内存
    got = await store.get(42)  # 降级读取
    assert got is not None and got.state == "awaiting_user"
    n = await store.acquire_lock(42)
    assert n is not None
    await store.release_lock(42, n)  # 降级释放不抛


async def test_redis_required_raises_on_failure(monkeypatch) -> None:
    """严格模式（redis_required=True）：Redis 故障必须可感知（抛错），不允许静默降级。"""
    import app.practice.state as st

    class _Broken:
        async def get(self, *a, **k):
            raise RuntimeError("redis down")

    from app.core.config import Settings

    monkeypatch.setattr(
        st,
        "get_settings",
        lambda: Settings(
            app_env="development", testing=False, redis_required=True, jwt_secret="x" * 40
        ),
    )
    store = RedisStateStore(_Broken(), fallback=MemoryStateStore())
    with pytest.raises(RuntimeError, match="Redis required but unavailable"):
        await store.get(42)
