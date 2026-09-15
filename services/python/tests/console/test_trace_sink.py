"""trace sink 测试（docs/50 §14.2 第 2 条 + P0 复核项）。

覆盖：
1. 队列满 → **丢当前**（新来的那条）、``trace_dropped_total`` 递增、调用方不阻塞；
2. 批量写出（一批一事务）落 ``llm_traces`` / ``llm_spans``；
3. **跨线程提交**：``asyncio.to_thread`` worker 里调 ``span()`` 也要能落库
   （本仓 30+ 处 ``to_thread``；``asyncio.Queue.put_nowait`` 跨线程不唤醒消费者，
   所以 sink 用 deque+Lock + ``call_soon_threadsafe`` —— 这条用例就是那个决定的回归）；
4. 关闭排水：超时未写出的条数计入 dropped，不静默消失。
"""

from __future__ import annotations

import asyncio
import time

import pytest
from app.console.trace.context import SpanRecord, TraceRecord, new_span_id, new_trace_id
from app.console.trace.recorder import span
from app.console.trace.sink import (
    BATCH_MAX,
    QUEUE_MAX,
    get_sink,
    reset_sink_for_tests,
)
from sqlalchemy import func, select

from .helpers import wait_for


def _make_trace(idx: int) -> TraceRecord:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    rec = TraceRecord(trace_id=new_trace_id(), kind="turn", started_at=now)
    rec.spans.append(
        SpanRecord(span_id=new_span_id(), name="ENTRY", parent_span_id=None, seq=0, started_at=now)
    )
    rec.attrs["idx"] = idx
    rec.mark_closed("ok")
    return rec


def _count_rows(model) -> int:
    from app.db import get_session_factory

    db = get_session_factory()()
    try:
        return int(db.execute(select(func.count()).select_from(model)).scalar() or 0)
    finally:
        db.close()


def test_overflow_drops_newest_and_counts_without_blocking() -> None:
    """队列满 → 丢**当前**（新来的），计数递增，且调用方零等待。"""
    sink = reset_sink_for_tests()
    for i in range(QUEUE_MAX):
        assert sink.submit(_make_trace(i)) is True
    assert sink.pending() == QUEUE_MAX

    started = time.perf_counter()
    accepted = sink.submit(_make_trace(99999))
    elapsed = time.perf_counter() - started

    assert accepted is False, "溢出必须丢当前这条"
    assert sink.dropped_total == 1
    assert sink.pending() == QUEUE_MAX, "溢出不得改变队列中既有条目（丢最旧会破坏顺序）"
    assert elapsed < 0.2, "溢出路径必须 O(1) 且不阻塞调用方"
    # 「丢当前」语义：最早那条仍在队首（迟到 trace 不会插队）
    assert sink._buf[0].attrs["idx"] == 0


def test_batch_write_lands_trace_and_spans() -> None:
    """批量写出：trace 行 + span 行一次事务落库。"""
    from app.models.console_telemetry import LlmSpan, LlmTrace

    sink = reset_sink_for_tests()
    recs = [_make_trace(i) for i in range(3)]
    for r in recs:
        assert sink.submit(r) is True
    written = sink._take_batch()
    assert len(written) == 3
    assert len(written) <= BATCH_MAX
    sink.write_batch(written)

    assert _count_rows(LlmTrace) == 3
    assert _count_rows(LlmSpan) == 3


@pytest.mark.asyncio
async def test_span_from_to_thread_worker_is_persisted() -> None:
    """跨线程提交回归：``asyncio.to_thread`` worker 里的 span 必须最终落库。

    旧式 ``asyncio.Queue.put_nowait`` 从 worker 线程调用不会唤醒事件循环消费者
    （CPython 的 ``_wakeup_next`` 只在同线程走 ``call_soon``），trace 会"偶发丢一批"。
    """
    from app.models.console_telemetry import LlmSpan, LlmTrace

    sink = reset_sink_for_tests()
    await sink.start()
    try:

        def _worker() -> None:
            # worker 线程里没有 trace 上下文 → recorder 自建 trace（kind 由 trace_kind 指定）
            with span("LLM", trace_kind="thread_test", origin="worker"):
                pass

        await asyncio.to_thread(_worker)
        ok = await wait_for(lambda: sink.written_total >= 1, timeout=5.0)
        assert ok, "跨线程提交的 trace 未被写出（消费者没被唤醒）"
    finally:
        await sink.stop()

    assert _count_rows(LlmTrace) == 1
    assert _count_rows(LlmSpan) == 2  # ENTRY + LLM


@pytest.mark.asyncio
async def test_stop_drains_bounded_and_counts_loss() -> None:
    """关闭排水：正常排水写空；未启动消费者时缓冲剩余计入 dropped（有界，不挂进程）。"""
    from app.models.console_telemetry import LlmTrace

    sink = reset_sink_for_tests()
    for i in range(5):
        assert sink.submit(_make_trace(i)) is True
    remaining = await sink.stop(timeout=5.0)
    assert remaining == 0
    assert sink.dropped_total == 0
    assert _count_rows(LlmTrace) == 5


def test_submit_never_raises_even_when_buffer_broken(monkeypatch) -> None:
    """采集异常绝不冒泡进业务：submit 内部异常也只能计数返回 False，不许抛。"""
    sink = reset_sink_for_tests()
    monkeypatch.setattr(sink, "_notify", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert sink.submit(_make_trace(0)) is False  # 不抛；调用方看到"这条丢了"
    assert sink.dropped_total == 1
    assert get_sink() is sink
