"""限流分桶（docs/06 §7：ASR/TTS/ISE 60 次/用户/时，LLM 30 次/用户/时，429 + Retry-After）。

- 固定窗口计数；Redis 可用走 Redis，否则进程内 dict（TTL 滑动清理）；
- 按**子资源**分桶：/turns 一次请求会消耗 asr+ise+llm 各 1，各桶独立计数
  （docs/16 E1 拍板：不按 /turns 单计 1 次）；
- SSE 长连接在 turn 开始时计数（本模块只管计数，不含时长维度）；
- **多桶一起扣**（2026-09-10 P1-13 修复）：一次请求要消耗多个桶时必须走 `consume_all`，
  全部扣成功才算数；任一桶超限 → 全量回滚 + 429。逐桶顺序 `await consume(a)`/`await consume(b)`
  在 b 超限时 a 已扣且不回滚 → 用户重试被重复计费（且额度被空转烧掉）。
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from fastapi import HTTPException, Request

from app.core.config import get_settings

# (bucket, key, window) -> (count, expires_at)
TRACE: dict[tuple[str, str, int], tuple[int, float]] = {}


def _window(now: float) -> int:
    """小时窗口起点（秒级时间戳）。"""
    return int(now // 3600)


def _memory_bump(bucket: str, key: str, delta: int) -> int:
    """内存计数 ±delta（窗口过期即重置）；返回变更后的计数（**不为负**）。

    `delta` 为负 = 回滚（P1-13）：钳到 0，避免"回滚未扣过的桶"把计数压成负数后放行超额请求。
    """
    now = time.time()
    win = _window(now)
    k = (bucket, key, win)
    count, expires = TRACE.get(k, (0, 0))
    if expires < now:
        count, expires = 0, now + 3600
    count = max(0, count + delta)
    TRACE[k] = (count, expires)
    # 惰性清理过期窗口（防 dict 无限增长）
    if len(TRACE) > 10_000:
        for kk in [kk for kk, (_, ex) in TRACE.items() if ex < now]:
            TRACE.pop(kk, None)
    return count


async def _redis_bump(bucket: str, key: str, delta: int) -> int:
    """Redis 计数 ±delta；Redis 不可用/异常 → 内存兜底（docs/06 §10.2 降级语义）。"""
    try:
        from app.core.redis_client import get_redis

        client = get_redis()
        if client is None:
            raise ConnectionError("no redis")
        win = _window(int(time.time()))
        rkey = f"rl:{bucket}:{key}:{win}"
        async with client.pipeline(transaction=False) as pipe:
            if delta >= 0:
                pipe.incrby(rkey, delta)
            else:
                pipe.decrby(rkey, -delta)
            pipe.expire(rkey, 7200)
            result = await pipe.execute()
        count = int(result[0])
        if count < 0:
            # 回滚落到"从未扣过"的键（Redis 抖动导致计数源切换）→ 归零，防止负计数放行
            count = 0
            await client.set(rkey, 0, ex=7200)
        return count
    except Exception:
        return _memory_bump(bucket, key, delta)


async def _redis_consume(bucket: str, key: str, limit: int) -> tuple[int, int]:
    """扣 1 并判限：返回 (code, retry_after_s)；`code==429` 表示超限（**已 +1**，可回滚）。"""
    now = int(time.time())
    win = _window(now)
    count = await _redis_bump(bucket, key, 1)
    if count > limit:
        return 429, int(win + 3600 - now)
    return 0, int(win + 3600 - now)


async def _release(bucket: str, key: str) -> None:
    """回滚一次扣减（P1-13）：`consume_all` 判定超限后把本请求扣过的桶全部归还。"""
    await _redis_bump(bucket, key, -1)


async def consume_all(buckets: Sequence[tuple[str, int]], user_id: int) -> None:
    """一次请求消耗的多个桶**一起扣**：全部通过才算数，任一超限 → 全量回滚 + 429。

    修复 P1-13（拷问报告）：旧写法 `await consume("sing", …)` → `await consume("ise", …)`，
    后一个桶超限时前一个桶**已扣且不回滚**——用户重试再扣一次（同一次上传被计两次；
    额度被"空转"烧干：ISE 桶耗尽后每次重试都白扣一个 sing，用户却始终拿不到结果）。
    现语义：本次请求要么消耗全部桶，要么一个都不消耗（`consume` = 单桶特例）。
    """
    if not buckets:
        return
    key = str(user_id)
    over: tuple[str, int] | None = None
    for bucket, limit_per_hour in buckets:
        code, retry = await _redis_consume(bucket, key, limit_per_hour)
        if code == 429 and over is None:
            over = (bucket, retry)
    if over is None:
        return
    for bucket, _limit in buckets:  # 全量回滚（含超限桶那次 +1：本请求没有执行，不该计费）
        await _release(bucket, key)
    bucket, retry = over
    raise HTTPException(
        status_code=429,
        detail=f"rate limited ({bucket})",
        headers={"Retry-After": str(max(retry, 1))},
    )


async def consume(bucket: str, limit_per_hour: int, user_id: int) -> None:
    """扣减一桶计数；超限抛 429（Retry-After 头）。= `consume_all` 的单桶形式。"""
    await consume_all([(bucket, limit_per_hour)], user_id)


def rate_limit(bucket: str, limit_per_hour: int):
    """依赖工厂：返回 (consume, retry_after_s) 的头信息由调用方组装。"""

    async def _dependency(request: Request, user_id: int) -> None:
        await consume_all([(bucket, limit_per_hour)], user_id)

    return _dependency


def bucket_limits(settings=None) -> dict[str, int]:
    s = settings or get_settings()
    return {
        "asr": s.asr_rate_per_hour,
        "tts": s.tts_rate_per_hour,
        "ise": s.ise_rate_per_hour,
        "llm": s.llm_rate_per_hour,
        "reading_tts": s.reading_tts_rate_per_hour,  # docs/45 §4：仅扣真实合成
        "media": s.media_rate_per_hour,  # docs/47 §4.1：图片/视频/头像上传
    }
