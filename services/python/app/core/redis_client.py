"""Redis 客户端（懒连接 + 不可用降级，docs/06 §10.2：不拒绝启动、readyz 报 degraded）。

- `get_redis()` 返回连接实例或 None（连接失败缓存负结果 30s，避免每次请求都重试）；
- 会话/缓存/限流/任务状态全走本例；业务主数据一律不入 Redis。

**2026-09-10 修复（docs/50 §15 G-4）**：`redis_available()` 旧实现是
`get_redis() is not None` —— 而 `aioredis.from_url` **不做任何网络 IO**，
所以 Redis 死了它也恒返回 True，控制台的 `redis.available` 指标与 `/readyz`
依赖探测因此都是**假信号**。现改为真实 PING：
- 同步版 `redis_available()`：用**独立同步客户端**（1s 连接/读写超时）——
  同步函数不能 await 异步客户端；
- 异步版 `redis_ping()`：复用业务异步客户端 + `asyncio.wait_for` 兜底超时，
  供 collector / `probe_dependencies()` 使用。
"""

from __future__ import annotations

import asyncio
import time

#: 真实 PING 的超时（秒）——探测绝不允许拖慢 /readyz 或采集桶
PING_TIMEOUT_S = 1.0

#: 同步探测结果缓存（防高频道探测打爆 Redis/端口）
_SYNC_CACHE_TTL = 5.0

_redis = None
_last_fail = 0.0
_FAIL_TTL = 30.0
_sync_cache: tuple[float, bool] | None = None


def get_redis():
    global _redis, _last_fail
    if _redis is not None:
        return _redis
    if time.time() - _last_fail < _FAIL_TTL:
        return None
    try:
        from app.core.config import get_settings

        settings = get_settings()
        if settings.testing:
            return None  # 测试/CI：强制内存后端（限流/会话走进程内，保证 hermetic）

        import redis.asyncio as aioredis

        _redis = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        return _redis
    except Exception:
        _last_fail = time.time()
        return None


def _probe_sync_client(timeout_s: float):
    """探测专用**同步**客户端（`redis.Redis`）——同步上下文里唯一能直接 PING 的形态。"""
    import redis

    from app.core.config import get_settings

    return redis.Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=timeout_s,
        socket_timeout=timeout_s,
    )


def redis_available(timeout_s: float = PING_TIMEOUT_S) -> bool:
    """Redis 是否真的可用（**真实 PING**，结果缓存 5s）。

    回归口径（docs/50 §14.2 第 3 条）：修复前本函数只判"客户端对象是否造出来"，
    Redis 进程已死仍返回 True —— 本函数必须对"PING 失败"返回 False。
    """
    global _sync_cache
    now = time.time()
    if _sync_cache is not None and now - _sync_cache[0] < _SYNC_CACHE_TTL:
        return _sync_cache[1]
    if get_redis() is None:  # 未配置 / 测试档 / 连接期已判失败
        _sync_cache = (now, False)
        return False
    try:
        ok = bool(_probe_sync_client(timeout_s).ping())
    except Exception:  # noqa: BLE001 - 探测失败=不可用（含超时/拒绝/认证失败）
        ok = False
    _sync_cache = (now, ok)
    return ok


async def redis_ping(timeout_s: float = PING_TIMEOUT_S) -> bool:
    """异步真实 PING（collector / 依赖探测用；异常一律视为不可用）。"""
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(await asyncio.wait_for(client.ping(), timeout=timeout_s))
    except Exception:  # noqa: BLE001
        return False


def reset_probe_cache() -> None:
    """测试专用：清掉同步探测缓存。"""
    global _sync_cache
    _sync_cache = None


__all__ = ["PING_TIMEOUT_S", "get_redis", "redis_available", "redis_ping", "reset_probe_cache"]
