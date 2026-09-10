"""LLM trace 采集（docs/50 §7）。对外只有四个入口：``span`` / ``trace`` / ``start_trace`` /
``finish_trace``；LLM 客户端回填用 ``note_llm_*``。
"""

from app.console.trace.context import (
    SPAN_AGENT,
    SPAN_ASR,
    SPAN_ENTRY,
    SPAN_LLM,
    SPAN_RETRIEVE,
    SPAN_SCORE,
    SPAN_STEP,
    SPAN_TOOL,
    SPAN_TTS,
    SpanRecord,
    TraceRecord,
)
from app.console.trace.recorder import (
    CONTENT_DENY_KINDS,
    content_capture_enabled,
    detached,
    enabled,
    finish_trace,
    note_error,
    note_llm_request,
    note_llm_result,
    span,
    start_trace,
    trace,
)
from app.console.trace.redact import redact, redact_messages
from app.console.trace.sink import get_sink, reset_sink_for_tests

__all__ = [
    "CONTENT_DENY_KINDS",
    "SPAN_AGENT",
    "SPAN_ASR",
    "SPAN_ENTRY",
    "SPAN_LLM",
    "SPAN_RETRIEVE",
    "SPAN_SCORE",
    "SPAN_STEP",
    "SPAN_TOOL",
    "SPAN_TTS",
    "SpanRecord",
    "TraceRecord",
    "content_capture_enabled",
    "detached",
    "enabled",
    "finish_trace",
    "get_sink",
    "note_error",
    "note_llm_request",
    "note_llm_result",
    "redact",
    "redact_messages",
    "reset_sink_for_tests",
    "span",
    "start_trace",
    "trace",
]
