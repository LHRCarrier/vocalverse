"""LLM trace 上下文与记录结构（docs/50 §7.3）。

**为什么用 ContextVar 而不是加函数参数**（照抄既有 ``app/core/trace.py:17`` 的
``_request_id`` 模式）：trace 的注入点分散在 orchestrator / runtime / 路由三层，
改签名会把观测诉求渗透进业务函数契约（docs/50 §7.3「最小耦合」硬要求）。
ContextVar 天然跟随 asyncio 任务上下文，``asyncio.create_task`` 复制父上下文，
所以 fire-and-forget 的摘要任务能自动挂到所属回合上。

两个 ContextVar：

- ``_current_trace``：当前 trace（trace_id / kind / session_id / user_id / request_id）；
- ``_current_span``：当前 span —— ``parent_span_id`` 由它**自动**推导，调用方不传父子关系。
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

#: span 名取值（docs/50 §7.2 的 DSH 派生树；与 models.console_telemetry.SpanNames 同集）
SPAN_ENTRY = "ENTRY"
SPAN_AGENT = "AGENT"
SPAN_STEP = "STEP"
SPAN_LLM = "LLM"
SPAN_TOOL = "TOOL"
SPAN_ASR = "ASR"
SPAN_TTS = "TTS"
SPAN_SCORE = "SCORE"
SPAN_RETRIEVE = "RETRIEVE"

#: 客户端类 span（出站调用：LLM/ASR/TTS/评分）；其余为进程内 span
CLIENT_SPAN_NAMES = frozenset({SPAN_LLM, SPAN_ASR, SPAN_TTS, SPAN_SCORE})

STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_ABORTED = "aborted"
STATUS_INCOMPLETE = "incomplete"


def new_span_id() -> str:
    """span 主键（32 位十六进制，``llm_spans.span_id`` 的 String(32) 上限内）。"""
    return uuid.uuid4().hex


def new_trace_id() -> str:
    """trace 主键（``llm_traces.trace_id`` 的 String(64) 上限内）。"""
    return uuid.uuid4().hex


@dataclass
class SpanRecord:
    """一个 span 的完整观测数据（内存态；sink 落 ``llm_spans`` + 可选 ``llm_span_contents``）。"""

    span_id: str
    name: str
    parent_span_id: str | None
    seq: int
    started_at: datetime
    span_kind: str = "internal"
    ended_at: datetime | None = None
    duration_ms: int | None = None
    ttft_ms: int | None = None
    status: str = STATUS_OK
    retry_index: int = 0
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None
    tool_name: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)
    #: 内容捕获（默认关；开启且不是禁采 kind 时才落 llm_span_contents）
    input_messages: list[dict[str, Any]] | None = None
    output_text: str | None = None
    closed: bool = False

    def close(
        self, status: str, *, error_code: str | None = None, error_message: str | None = None
    ):
        """关闭 span：补齐 ended_at/duration_ms/status（幂等——重复关闭是 no-op）。"""
        if self.closed:
            return
        self.closed = True
        self.ended_at = datetime.now(UTC)
        self.duration_ms = max(int((self.ended_at - self.started_at).total_seconds() * 1000), 0)
        self.status = status
        if error_code:
            self.error_code = error_code
        if error_message:
            self.error_message = error_message[:500]  # llm_spans.error_message String(500)


@dataclass
class TraceRecord:
    """一次调用链（1 turn = 1 trace，docs/50 §7.2）。"""

    trace_id: str
    kind: str
    started_at: datetime
    request_id: str | None = None
    session_id: str | None = None
    user_id: int | None = None
    spans: list[SpanRecord] = field(default_factory=list)
    entry_span_id: str | None = None
    model: str | None = None
    status: str = STATUS_OK
    ended_at: datetime | None = None
    duration_ms: int | None = None
    ttft_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    content_captured: bool = False
    attrs: dict[str, Any] = field(default_factory=dict)
    closed: bool = False
    #: 采样命中（未命中时 recorder 全程 no-op，不产生任何记录）
    sampled: bool = True

    def next_seq(self) -> int:
        """span 序号（瀑布图主排序键；``ix_llm_spans_trace_seq``）。"""
        return len(self.spans)

    def llm_spans(self) -> list[SpanRecord]:
        return [s for s in self.spans if s.name == SPAN_LLM]

    def mark_closed(self, status: str) -> None:
        if self.closed:
            return
        self.closed = True
        self.ended_at = datetime.now(UTC)
        self.duration_ms = max(int((self.ended_at - self.started_at).total_seconds() * 1000), 0)
        self.status = status


_current_trace: ContextVar[TraceRecord | None] = ContextVar("llm_trace", default=None)
_current_span: ContextVar[SpanRecord | None] = ContextVar("llm_span", default=None)


def current_trace() -> TraceRecord | None:
    """当前 trace（无上下文返回 None）。"""
    return _current_trace.get()


def current_span() -> SpanRecord | None:
    """当前 span（用于自动推导 parent_span_id）。"""
    return _current_span.get()


def set_current_trace(trace: TraceRecord | None) -> Token:
    return _current_trace.set(trace)


def reset_current_trace(token: Token) -> None:
    _current_trace.reset(token)


def set_current_span(span: SpanRecord | None) -> Token:
    return _current_span.set(span)


def reset_current_span(token: Token) -> None:
    _current_span.reset(token)
