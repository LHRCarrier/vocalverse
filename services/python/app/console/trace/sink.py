"""trace 有界批量写入器（docs/50 §8.3）。

**为什么不是 ``asyncio.Queue`` + ``put_nowait``**（本文件的关键决定）：
本仓有 30+ 处 ``asyncio.to_thread``（如 ``practice/orchestrator.py`` 的读库、``media`` 的落盘），
``span()`` 是**跨线程可用**的通用钩子 —— 从 worker 线程调用 ``asyncio.Queue.put_nowait`` 会
绕过队列内部的 ``_get_loop()`` 唤醒逻辑（CPython 只在同线程时走 ``call_soon``，跨线程时
``put_nowait`` 直接往 deque 里塞但**不唤醒 getter**，极端情况还会与 ``get`` 的清理竞争）——
表现是"trace 偶发丢一批"，且只在并发下复现。
故采用：**``collections.deque`` + ``threading.Lock`` 做线程安全有界缓冲**，
提交方只拿锁做 O(1) 追加；唤醒消费者走 ``loop.call_soon_threadsafe(event.set)``
（唯一的跨线程 → 事件循环安全通道）。

参数对齐 DSH 导出器默认（docs/50 §7.1）：队列 2048 / 批 512 / 间隔 5s。
溢出**丢当前**（docs/50 §8.3：O(1) 且不破坏队列内既有顺序，丢最旧会让"迟到的 trace 先入库"）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections import deque
from typing import Any

from app.console.trace.context import (
    STATUS_ABORTED,
    STATUS_ERROR,
    STATUS_INCOMPLETE,
    STATUS_OK,
    SpanRecord,
    TraceRecord,
)
from app.console.trace.redact import redact

logger = logging.getLogger("vocalverse.console.trace.sink")

#: 对齐 DSH maxQueueSize / maxExportBatchSize / traceExportIntervalMs（docs/50 §7.1 / §8.3）
QUEUE_MAX = 2048
BATCH_MAX = 512
FLUSH_INTERVAL = 5.0
#: trace 写入并发上限（docs/50 §8.2：防止 trace 写抢占业务连接池 pool_size=20）
TRACE_WRITE_CONCURRENCY = 2
#: 关闭时排水上限（docs/50 §8.3）；超时即认损，计入 trace_dropped_total
DRAIN_TIMEOUT = 5.0


class TraceSink:
    """线程安全 · 有界 · 批量 · 非阻塞的 trace 写入器。"""

    def __init__(self) -> None:
        self._buf: deque[TraceRecord] = deque()
        self._lock = threading.Lock()
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._sem: asyncio.Semaphore | None = None
        self._closing = False
        #: 采集自监控（docs/50 §8.4 / §9.4：采集自身的健康也要在控制台可见）
        self.dropped_total = 0
        self.written_total = 0
        self.write_errors_total = 0
        self.flush_errors_total = 0

    # ------------------------------------------------------------------
    # 提交（任意线程可调用；绝不阻塞、绝不抛）
    # ------------------------------------------------------------------
    def submit(self, trace: TraceRecord) -> bool:
        """入队一个已结束的 trace；队列满 → 丢当前并计数（返回 False）。"""
        try:
            with self._lock:
                if len(self._buf) >= QUEUE_MAX:
                    self.dropped_total += 1
                    return False
                self._buf.append(trace)
            self._notify()
            return True
        except Exception:  # 采集失败绝不冒泡进业务（docs/50 §7.3）
            self.dropped_total += 1
            logger.warning("trace submit failed", exc_info=True)
            return False

    def _notify(self) -> None:
        """唤醒消费者：跨线程唯一安全通道是 call_soon_threadsafe。"""
        loop, event = self._loop, self._wake
        if loop is None or event is None or loop.is_closed():
            return
        with contextlib.suppress(RuntimeError):
            # 事件循环已关闭（进程退出竞态）：trace 留在缓冲里，由 drain 兜底
            loop.call_soon_threadsafe(event.set)

    # ------------------------------------------------------------------
    # 消费者生命周期（lifespan 调用）
    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self._task is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self._sem = asyncio.Semaphore(TRACE_WRITE_CONCURRENCY)
        self._closing = False
        self._task = asyncio.create_task(self._flush_loop(), name="trace-sink")

    async def stop(self, timeout: float = DRAIN_TIMEOUT) -> int:
        """关闭并排水；返回超时未写出的条数（计入 dropped）。"""
        self._closing = True
        self._notify()
        remaining = 0
        if self._task is not None:
            try:
                await asyncio.wait_for(self._drain_until_empty(), timeout=timeout)
            except TimeoutError:
                logger.warning("trace sink drain 超时（%.1fs）：剩余缓冲计入丢弃", timeout)
            finally:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._task  # 关闭路径吞异常：cancel 后 await 必抛 CancelledError
                self._task = None
        elif self._buf:
            # 消费者从未启动（单测/嵌入用法）：也要尝试写空，
            # 否则"submit 成功过"的 trace 会在关闭时被静默丢掉。
            with contextlib.suppress(TimeoutError, Exception):
                await asyncio.wait_for(self._drain_until_empty(), timeout=timeout)
        with self._lock:
            remaining = len(self._buf)
            self._buf.clear()
        if remaining:
            self.dropped_total += remaining
        return remaining

    async def _drain_until_empty(self) -> None:
        """把缓冲写空（一次性批量循环，单次等待不超过 FLUSH_INTERVAL）。"""
        while True:
            with self._lock:
                empty = not self._buf
            if empty:
                return
            await self._flush_once()

    async def _flush_loop(self) -> None:
        """后台单任务：攒到 BATCH_MAX 或间隔 FLUSH_INTERVAL → 一次事务批量 INSERT。"""
        event = self._wake
        assert event is not None
        while True:
            try:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(event.wait(), timeout=FLUSH_INTERVAL)
                event.clear()
                await self._flush_once()
                if self._closing:
                    with self._lock:
                        if not self._buf:
                            return
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 消费者自身异常不得终止循环
                self.flush_errors_total += 1
                logger.warning("trace flush loop error", exc_info=True)
                await asyncio.sleep(1.0)

    def _take_batch(self) -> list[TraceRecord]:
        with self._lock:
            n = min(len(self._buf), BATCH_MAX)
            batch = [self._buf.popleft() for _ in range(n)]
        return batch

    async def _flush_once(self) -> int:
        batch = self._take_batch()
        if not batch:
            return 0
        sem = self._sem
        if sem is None:  # 未 start（单测直连）：退化为同步线程写入，仍不阻塞事件循环
            await asyncio.to_thread(self.write_batch, batch)
            return len(batch)
        async with sem:
            try:
                await asyncio.to_thread(self.write_batch, batch)
            except Exception:
                self.write_errors_total += len(batch)
                self.dropped_total += len(batch)
                logger.warning("trace 批量写入失败：丢弃 %d 条", len(batch), exc_info=True)
                return 0
        self.written_total += len(batch)
        return len(batch)

    # ------------------------------------------------------------------
    # 同步写库（在 worker 线程内跑；一批一事务）
    # ------------------------------------------------------------------
    def write_batch(self, batch: list[TraceRecord]) -> None:  # pragma: no cover - 由 to_thread 调用
        """一批 = 一次事务（docs/50 §8.3）：trace 行 + span 行 + 可选内容行一起提交。"""
        from app.db import get_session_factory

        db = get_session_factory()()
        try:
            db.add_all([_trace_row(t) for t in batch])
            # span 明细必须同批写入：只写 trace 行会让瀑布图永远空白
            db.add_all([_span_row(t, s) for t in batch for s in t.spans])
            content_rows = [row for t in batch for row in _content_rows(t)]
            if content_rows:
                db.add_all(content_rows)
            db.commit()
        finally:
            db.close()

    # ------------------------------------------------------------------
    # 自监控（collector 每桶读一次）
    # ------------------------------------------------------------------
    def stats(self) -> dict[str, int]:
        return {
            "dropped": self.dropped_total,
            "written": self.written_total,
            "write_errors": self.write_errors_total,
            "flush_errors": self.flush_errors_total,
            "buffered": len(self._buf),
        }

    def pending(self) -> int:
        with self._lock:
            return len(self._buf)


_sink: TraceSink | None = None
_sink_lock = threading.Lock()


def get_sink() -> TraceSink:
    """进程单例（导入即存在：``span()`` 在未 start 时也能安全提交）。"""
    global _sink
    if _sink is None:
        with _sink_lock:
            if _sink is None:
                _sink = TraceSink()
    return _sink


def reset_sink_for_tests() -> TraceSink:
    """测试专用：换一个干净的 sink（避免跨用例计数串味）。"""
    global _sink
    with _sink_lock:
        _sink = TraceSink()
    return _sink


# ---------------------------------------------------------------------------
# TraceRecord → ORM 行
# ---------------------------------------------------------------------------
def _trace_row(t: TraceRecord):
    from app.models.console_telemetry import LlmTrace

    llm = t.llm_spans()
    prompt = sum(int(s.prompt_tokens or 0) for s in llm)
    completion = sum(int(s.completion_tokens or 0) for s in llm)
    ttfts = [s.ttft_ms for s in llm if s.ttft_ms is not None]
    error_codes = [s.error_code for s in t.spans if s.error_code]
    return LlmTrace(
        trace_id=t.trace_id,
        request_id=_clip(t.request_id, 64),
        service="python",
        kind=_clip(t.kind, 32) or "llm",
        session_id=_clip(t.session_id, 64),
        user_id=t.user_id,
        model=_clip(t.model, 64),
        status=t.status if t.status in _TRACE_STATUSES else STATUS_ERROR,
        started_at=t.started_at,
        ended_at=t.ended_at,
        duration_ms=t.duration_ms,
        # 「木桶最慢一次」：trace 级 TTFT 取所有 LLM span 的最大值（docs/50 §5.3.13）
        ttft_ms=max(ttfts) if ttfts else None,
        span_count=len(t.spans),
        llm_call_count=len(llm),
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        cache_hit_tokens=int(t.attrs.get("cache_hit_tokens") or 0),
        error_code=_clip(t.error_code or (error_codes[0] if error_codes else None), 64),
        error_message=_clip(t.error_message or _first_error(t.spans), 500),
        content_captured=bool(t.content_captured),
        attrs=_jsonable(t.attrs),
    )


def _span_row(t: TraceRecord, s: SpanRecord):
    from app.models.console_telemetry import LlmSpan

    return LlmSpan(
        trace_id=t.trace_id,
        span_id=s.span_id,
        parent_span_id=s.parent_span_id,
        name=_clip(s.name, 48) or "STEP",
        span_kind=s.span_kind if s.span_kind in ("internal", "client", "server") else "internal",
        seq=s.seq,
        started_at=s.started_at,
        ended_at=s.ended_at,
        duration_ms=s.duration_ms,
        ttft_ms=s.ttft_ms,
        status=s.status if s.status in _TRACE_STATUSES else STATUS_ERROR,
        retry_index=max(int(s.retry_index), 0),
        model=_clip(s.model, 64),
        prompt_tokens=s.prompt_tokens,
        completion_tokens=s.completion_tokens,
        finish_reason=_clip(s.finish_reason, 32),
        tool_name=_clip(s.tool_name, 64),
        error_code=_clip(s.error_code, 64),
        error_message=_clip(s.error_message, 500),
        attrs=_jsonable(s.attrs),
    )


def _content_rows(t: TraceRecord):
    """内容行：**默认零行**；仅当配置开 + 该 kind 不在硬禁采清单 + span 确实带了内容。"""
    from app.models.console_telemetry import LlmSpanContent

    if not t.content_captured:
        return []
    max_chars = _content_max_chars()
    out = []
    for s in t.spans:
        if s.input_messages:
            text = _render_messages(s.input_messages)
            out.append(_content_row(LlmSpanContent, t, s, "input", 0, "user", text, max_chars))
        if s.output_text:
            out.append(
                _content_row(
                    LlmSpanContent, t, s, "output", 0, "assistant", s.output_text, max_chars
                )
            )
    return out


def _content_row(model_cls, t: TraceRecord, s: SpanRecord, direction, seq, role, text, max_chars):
    clean, hit = redact(text)
    clean = clean or ""
    truncated = len(clean) > max_chars
    return model_cls(
        trace_id=t.trace_id,
        span_id=s.span_id,
        direction=direction,
        seq=seq,
        role=role,
        content=clean[:max_chars],
        content_chars=min(len(clean), max_chars),
        truncated=truncated,
        redacted=hit,
    )


def _render_messages(messages: list[dict[str, Any]]) -> str:
    return "\n\n".join(f"[{m.get('role', 'user')}]\n{m.get('content', '')}" for m in messages)


def _content_max_chars() -> int:
    from app.core.config import get_settings

    try:
        return max(int(get_settings().llm_trace_content_max_chars), 1)
    except Exception:  # noqa: BLE001 - 配置异常不阻断写入，退回 DSH 默认
        return 128000


def _first_error(spans: list[SpanRecord]) -> str | None:
    for s in spans:
        if s.error_message:
            return s.error_message
    return None


def _clip(value: str | None, n: int) -> str | None:
    if value is None:
        return None
    return str(value)[:n]


def _jsonable(data: dict[str, Any]) -> dict[str, Any]:
    """attrs 必须是 JSON 可序列化（jsonb 列）：不可序列化的值降级为 str。"""
    out: dict[str, Any] = {}
    for k, v in data.items():
        out[str(k)] = (
            v if isinstance(v, (str, int, float, bool, list, dict, type(None))) else str(v)
        )
    out.setdefault("written_by", "python-console-trace")
    return out


_TRACE_STATUSES = frozenset({STATUS_OK, STATUS_ERROR, STATUS_ABORTED, STATUS_INCOMPLETE})


__all__ = [
    "BATCH_MAX",
    "DRAIN_TIMEOUT",
    "FLUSH_INTERVAL",
    "QUEUE_MAX",
    "TRACE_WRITE_CONCURRENCY",
    "TraceSink",
    "get_sink",
    "reset_sink_for_tests",
]
