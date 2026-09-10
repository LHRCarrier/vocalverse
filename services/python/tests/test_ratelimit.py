"""限流分桶测试（P1-13：多桶一起扣 + 全量回滚）。

测试环境 `APP_TESTING=true` → `get_redis()` 返回 None（`redis_client.py:26`）→ 走内存 `TRACE`，
计数可精确断言（hermetic，不依赖 Redis）。
"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import HTTPException


def _count(bucket: str, user_id: int) -> int:
    """当前窗口内该桶的计数（测试直读内存后端）。"""
    import app.core.ratelimit as rl

    key = (bucket, str(user_id), rl._window(time.time()))
    return int(rl.TRACE.get(key, (0, 0))[0])


def test_consume_all_charges_every_bucket_on_success():
    """全桶有余量 → 一次请求把所有桶各扣 1（成功路径与逐桶扣等价）。"""
    import app.core.ratelimit as rl

    rl.TRACE.clear()
    asyncio.run(rl.consume_all([("sing", 5), ("ise", 5)], 9001))
    assert _count("sing", 9001) == 1
    assert _count("ise", 9001) == 1


def test_consume_all_rolls_back_all_buckets_when_any_is_over():
    """**P1-13 核心**：任一桶超限 → 全量回滚（含超限桶自身那次 +1），429 指向超限桶。

    逐桶顺序扣的旧语义下，sing 已被扣走、ise 才报 429——用户重试同一会话上传会再扣一次 sing
    （一次操作计两次），且 ISE 额度耗尽期间每次重试都白扣 sing。
    """
    import app.core.ratelimit as rl

    rl.TRACE.clear()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(rl.consume_all([("sing", 30), ("ise", 0)], 9002))  # ISE 桶额度为 0
    assert exc.value.status_code == 429
    assert "ise" in exc.value.detail
    assert exc.value.headers["Retry-After"] >= "1"
    assert _count("sing", 9002) == 0, "超限时 sing 必须回滚（修复前逐桶扣会留下 1）"
    assert _count("ise", 9002) == 0, "超限桶自身的那次 +1 也应回滚"


def test_consume_all_rolls_back_when_later_bucket_exhausted_by_usage():
    """非零额度被用尽后的下一次请求：全部回滚，且不放大计数（防"越拒越多"）。"""
    import app.core.ratelimit as rl

    rl.TRACE.clear()
    asyncio.run(rl.consume_all([("sing", 30), ("ise", 1)], 9003))  # 用掉 ise 唯一额度
    assert _count("ise", 9003) == 1
    with pytest.raises(HTTPException):
        asyncio.run(rl.consume_all([("sing", 30), ("ise", 1)], 9003))
    assert _count("sing", 9003) == 1, "被拒请求不得再扣 sing"
    assert _count("ise", 9003) == 1, "被拒请求不得让 ise 计数继续增长"


def test_consume_single_bucket_keeps_limit_semantics():
    """单桶形态（`consume` = `consume_all` 单元素）：限额内放行、达限即 429 且计数不增长。"""
    import app.core.ratelimit as rl

    rl.TRACE.clear()
    asyncio.run(rl.consume("llm", 1, 9004))
    assert _count("llm", 9004) == 1
    with pytest.raises(HTTPException) as exc:
        asyncio.run(rl.consume("llm", 1, 9004))
    assert exc.value.status_code == 429
    assert _count("llm", 9004) == 1, "被拒的请求不得把计数推到 2（旧 Redis 路径会一直 INCR）"


def test_memory_bump_never_goes_negative():
    """回滚保护：未扣过的桶被回滚不得变负（否则负计数会放行超额请求）。"""
    import app.core.ratelimit as rl

    rl.TRACE.clear()
    assert rl._memory_bump("asr", "9005", -1) == 0
    assert _count("asr", 9005) == 0
