"""SSE 心跳包装器测试（R-18 / 审计 R-18：静默 ≥ 间隔推 ': ping'，不取消内部流）。"""

from __future__ import annotations

import asyncio

import pytest
from app.practice import events as ev


async def test_fast_stream_no_ping() -> None:
    """事件间隔小于心跳间隔 → 零 ping，事件顺序透传。"""

    async def core():
        for i in range(3):
            await asyncio.sleep(0)
            yield f"data: {i}\n\n"

    out = [p async for p in ev.heartbeat_stream(core(), 30.0, serialize=lambda x: x)]
    assert out == ["data: 0\n\n", "data: 1\n\n", "data: 2\n\n"]


async def test_slow_stream_emits_ping_and_resumes() -> None:
    """长静默段 → 每间隔一行 ': ping'（注释行），且流继续（不取消内部生成器）。"""

    async def core():
        yield "data: a\n\n"
        await asyncio.sleep(0.25)
        yield "data: b\n\n"

    out = [p async for p in ev.heartbeat_stream(core(), 0.1, serialize=lambda x: x)]
    assert out[0] == "data: a\n\n"
    assert ev.PING_LINE in out
    assert out[-1] == "data: b\n\n"


async def test_inner_exception_propagates() -> None:
    """内部异常必须透传（上层 error 事件/日志处理，不吞）。"""

    async def core():
        yield "ok\n\n"
        raise ValueError("boom")

    with pytest.raises(ValueError):
        [p async for p in ev.heartbeat_stream(core(), 0.1, serialize=lambda x: x)]


async def test_inner_end_stops_heartbeat() -> None:
    """生成器正常结束 → 心跳结束（无多余 ping 后闭包）。"""

    async def core():
        await asyncio.sleep(0.03)
        yield "x\n\n"

    out = [p async for p in ev.heartbeat_stream(core(), 0.01, serialize=lambda x: x)]
    assert "x\n\n" in out
    assert out[-1] == "x\n\n"


async def test_serialize_called_per_event() -> None:
    """默认 serializer 走 sse_payload（事件对象 → data: 行）。"""

    async def core():
        yield ev.TextDelta(text="hi")

    out = [p async for p in ev.heartbeat_stream(core(), 30.0)]
    assert out == ['data: {"type": "text_delta", "text": "hi"}\n\n']


async def test_zero_interval_passthrough_no_ping() -> None:
    """interval<=0 = 关闭心跳：纯透传零 ping（2026-09-07 评审：修复前 0 → sleep(0) 忙循环洪泛）。"""

    async def core():
        await asyncio.sleep(0.001)
        yield "a"
        await asyncio.sleep(0.001)
        yield "b"

    out = [p async for p in ev.heartbeat_stream(core(), 0.0, serialize=lambda x: x)]
    assert out == ["a", "b"]
    assert ev.PING_LINE not in out
