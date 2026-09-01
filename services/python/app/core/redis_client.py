"""Redis 客户端（懒连接 + 不可用降级，docs/06 §10.2：不拒绝启动、readyz 报 degraded）。

- `get_redis()` 返回连接实例或 None（连接失败缓存负结果 30s，避免每次请求都重试）；
- 会话/缓存/限流/任务状态全走本例；业务主数据一律不入 Redis。
"""

from __future__ import annotations

import time

_redis = None
_last_fail = 0.0
_FAIL_TTL = 30.0


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


def redis_available() -> bool:
    return get_redis() is not None
