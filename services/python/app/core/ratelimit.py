"""限流分桶（docs/06 §7：ASR/TTS/ISE 60 次/用户/时，LLM 30 次/用户/时，429 + Retry-After）。

- 固定窗口计数；Redis 可用走 Redis，否则进程内 dict（TTL 滑动清理）；
- 按**子资源**分桶：/turns 一次请求会消耗 asr+ise+llm 各 1，各桶独立计数
  （docs/16 E1 拍板：不按 /turns 单计 1 次）；
- SSE 长连接在 turn 开始时计数（本模块只管计数，不含时长维度）。
"""

from __future__ import annotations

import time

from fastapi import HTTPException, Request

from app.core.config import get_settings

# (bucket, key, window) -> (count, expires_at)
TRACE: dict[tuple[str, str, int], tuple[int, float]] = {}


def _window(now: float) -> int:
    """小时窗口起点（秒级时间戳）。"""
    return int(now // 3600)


def _memory_consume(bucket: str, key: str, limit: int) -> int:
    now = time.time()
    win = _window(now)
    k = (bucket, key, win)
    count, expires = TRACE.get(k, (0, 0))
    if expires < now:
        count, expires = 0, now + 3600
    if count >= limit:
        return 429, 0
    TRACE[k] = (count + 1, expires)
    # 惰性清理过期窗口（防 dict 无限增长）
    if len(TRACE) > 10_000:
        for kk in [kk for kk, (_, ex) in TRACE.items() if ex < now]:
            TRACE.pop(kk, None)
    return 0, int(now + 3600 - now)


async def _redis_consume(bucket: str, key: str, limit: int) -> tuple[int, int]:
    from app.core.redis_client import get_redis

    try:
        client = get_redis()
        if client is None:
            raise ConnectionError("no redis")
        now = int(time.time())
        win = _window(now)
        rkey = f"rl:{bucket}:{key}:{win}"
        async with client.pipeline(transaction=False) as pipe:
            pipe.incr(rkey)
            pipe.expire(rkey, 7200)
            result = await pipe.execute()
        count = int(result[0])
        if count > limit:
            return 429, int(win + 3600 - now)
        return 0, int(win + 3600 - now)
    except Exception:  # Redis 不可用 → 内存兜底（docs/06 §10.2 降级语义）
        return _memory_consume(bucket, key, limit)


async def consume(bucket: str, limit_per_hour: int, user_id: int) -> None:
    """扣减一桶计数；超限抛 429（Retry-After 头）。"""
    code, retry = await _redis_consume(bucket, str(user_id), limit_per_hour)
    if code == 429:
        raise HTTPException(
            status_code=429,
            detail=f"rate limited ({bucket})",
            headers={"Retry-After": str(max(retry, 1))},
        )


def rate_limit(bucket: str, limit_per_hour: int):
    """依赖工厂：返回 (consume, retry_after_s) 的头信息由调用方组装。"""

    async def _dependency(request: Request, user_id: int) -> None:
        key = str(user_id)
        code, retry = await _redis_consume(bucket, key, limit_per_hour)
        if code == 429:
            raise HTTPException(
                status_code=429,
                detail=f"rate limited ({bucket})",
                headers={"Retry-After": str(max(retry, 1))},
            )

    return _dependency


def bucket_limits(settings=None) -> dict[str, int]:
    s = settings or get_settings()
    return {
        "asr": s.asr_rate_per_hour,
        "tts": s.tts_rate_per_hour,
        "ise": s.ise_rate_per_hour,
        "llm": s.llm_rate_per_hour,
    }
