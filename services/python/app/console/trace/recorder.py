"""trace 采集器（docs/50 §7.2/§7.3：DSH 派生 span 树 + 最小耦合注入）。

设计要点（逐条对应 docs/50 的硬要求）：

1. **树形**：``ENTRY → AGENT → STEP → {LLM, TOOL}``，另有 ``ASR/TTS/SCORE/RETRIEVE``。
   ``parent_span_id`` 由 ``context.current_span()`` **自动**推导，调用方不改函数签名；
2. **每次 LLM 尝试一个 span**（``retry_index`` 让同一 STEP 下的重试可见，DSH 原则之二）；
3. **异常/中断/未完成必须关闭活动 span 并标 error**（DSH 原则之四）——
   捕获 ``BaseException``（含 ``asyncio.CancelledError``），绝不留下悬挂 span；
4. **采集异常绝不冒泡进业务**（docs/50 §7.3 末条）：``span()`` 的
   ``__enter__``/``__exit__`` 全程包 ``try/except``，失败只计数 ``trace_dropped_total``；
5. **内容捕获默认关**（``llm_span_contents`` 零行）；``CONTENT_DENY_KINDS`` 是**硬禁采清单**：
   答辩（defense）链路整条入参是用户粘贴的论文正文，脱敏规则只能处理邮箱/手机号/密钥形态，
   **无法**脱敏论文 —— 故无论开关如何，绝不落内容（docs/06 §9.7 只存评分/转写/元数据红线）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.console.trace.context import (
    CLIENT_SPAN_NAMES,
    SPAN_ENTRY,
    STATUS_ABORTED,
    STATUS_ERROR,
    STATUS_INCOMPLETE,
    STATUS_OK,
    SpanRecord,
    TraceRecord,
    current_span,
    current_trace,
    new_span_id,
    new_trace_id,
    reset_current_span,
    reset_current_trace,
    set_current_span,
    set_current_trace,
)
from app.console.trace.sink import get_sink

logger = logging.getLogger("vocalverse.console.trace")

#: 硬禁采内容清单（P0-2 · docs/06 §9.7）：这些 kind 的 trace **永不**写 llm_span_contents。
#: - ``defense``：答辩链路整条 prompt 是用户粘贴的论文正文（title/abstract/outline/thesis_text），
#:   脱敏规则对开放文本无能为力，只能靠"禁采"兜底；
#: - ``thesis``：defense 的上游别名（防御性冗余，避免将来改名漏网）。
CONTENT_DENY_KINDS = frozenset({"defense", "thesis"})

#: 默认 trace kind（LLM 调用点未显式 start_trace 时的兜底值）
DEFAULT_KIND = "llm"


def _settings():
    from app.core.config import get_settings

    return get_settings()


def enabled() -> bool:
    """采集总开关（``APP_LLM_TRACE_ENABLED``；缺配置时视为关闭，绝不因配置异常崩溃）。"""
    try:
        return bool(_settings().llm_trace_enabled)
    except Exception:  # noqa: BLE001
        return False


def _sampled() -> bool:
    try:
        rate = float(_settings().llm_trace_sample_rate)
    except Exception:  # noqa: BLE001
        rate = 1.0
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


def content_capture_enabled() -> bool:
    try:
        return bool(_settings().llm_trace_content_capture)
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# trace 生命周期
# ---------------------------------------------------------------------------
class _TraceCM:
    """``with trace(kind=...)``：确保 start/finish 成对（异常路径也收尾）。"""

    def __init__(self, kind: str, **kwargs: Any) -> None:
        self._kind = kind
        self._kwargs = kwargs
        self._trace: TraceRecord | None = None
        self._token = None

    def __enter__(self) -> TraceRecord | None:
        try:
            self._trace = start_trace(self._kind, **self._kwargs)
            self._token = set_current_trace(self._trace)
        except Exception:  # noqa: BLE001
            _count_dropped()
        return self._trace

    def __exit__(self, exc_type, exc, tb) -> bool:
        status = STATUS_OK
        if exc is not None:
            status = STATUS_ABORTED if _is_abort(exc) else STATUS_ERROR
        try:
            finish_trace(status=status, error=exc)
        except Exception:  # noqa: BLE001
            _count_dropped()
        finally:
            if self._token is not None:
                with contextlib.suppress(Exception):
                    reset_current_trace(self._token)
        return False  # 绝不吞业务异常


def trace(kind: str, **kwargs: Any) -> _TraceCM:
    """trace 上下文管理器（``session_id`` / ``user_id`` / 任意 attrs 透传）。"""
    return _TraceCM(kind, **kwargs)


def start_trace(
    kind: str,
    *,
    session_id: str | int | None = None,
    user_id: int | None = None,
    **attrs: Any,
) -> TraceRecord | None:
    """开启一条 trace（未开启采集/未命中采样 → None，后续 ``span()`` 全部 no-op）。

    ``ENTRY`` 根 span 由本函数隐式打开并压栈：调用方只要 ``start_trace`` 就能得到
    ``ENTRY → …`` 的树根，无需在业务函数里多写一层缩进。
    """
    if not enabled() or not _sampled():
        return None
    from app.core.trace import get_request_id

    rid = get_request_id()
    rec = TraceRecord(
        trace_id=new_trace_id(),
        kind=kind or DEFAULT_KIND,
        started_at=_utcnow(),
        request_id=None if rid == "-" else rid,
        session_id=None if session_id is None else str(session_id),
        user_id=user_id,
        attrs=dict(attrs),
    )
    entry = SpanRecord(
        span_id=new_span_id(),
        name=SPAN_ENTRY,
        parent_span_id=None,
        seq=rec.next_seq(),
        started_at=rec.started_at,
        attrs={"kind": rec.kind},
    )
    rec.spans.append(entry)
    rec.entry_span_id = entry.span_id
    # 注意：ENTRY **不压** span 栈 —— 栈只表示"当前编辑中的子 span"，
    # 压栈会让根 span 在 trace 结束后仍残留在 ContextVar 里。
    return rec


def finish_trace(
    status: str | None = None, *, error: BaseException | None = None
) -> TraceRecord | None:
    """收尾：关闭仍活动的 span（标 ``incomplete``）→ 计算 trace 汇总 → 投递 sink。"""
    rec = current_trace()
    if rec is None:
        return None
    try:
        if rec.closed:  # 迟到收尾：不重复投递
            return rec
        final = status or _aggregate_status(rec)
        if error is not None:
            rec.error_code = rec.error_code or _error_code(error)
            rec.error_message = rec.error_message or _msg(error)
        for span in rec.spans:
            if span.closed:
                continue
            # ENTRY 随 trace 状态收尾；其余未关闭的 span 只能是"泄漏"，一律标 incomplete
            span.close(final if span.span_id == rec.entry_span_id else STATUS_INCOMPLETE)
        rec.mark_closed(final)
        rec.model = rec.model or _first_model(rec)
        _apply_content_policy(rec)
        _record_trace_metrics(rec)
        if rec.spans:
            get_sink().submit(rec)
    except Exception:  # noqa: BLE001 - 采集失败绝不冒泡
        _count_dropped()
        logger.warning("finish_trace failed", exc_info=True)
    return rec


def _aggregate_status(rec: TraceRecord) -> str:
    statuses = {s.status for s in rec.spans}
    if STATUS_ERROR in statuses:
        return STATUS_ERROR
    if STATUS_ABORTED in statuses:
        return STATUS_ABORTED
    if STATUS_INCOMPLETE in statuses:
        return STATUS_INCOMPLETE
    return STATUS_OK


def _first_model(rec: TraceRecord) -> str | None:
    for s in rec.spans:
        if s.model:
            return s.model
    return None


# ---------------------------------------------------------------------------
# span 上下文管理器
# ---------------------------------------------------------------------------
class _SpanCM:
    """``with span("LLM", ...)``：同步上下文管理器（异步函数里同样可用）。"""

    def __init__(self, name: str, kwargs: dict[str, Any]) -> None:
        self._name = name
        self._kwargs = kwargs
        self._span: SpanRecord | None = None
        self._token = None
        self._owns_trace = False
        self._trace_token = None

    def __enter__(self) -> SpanRecord | None:
        try:
            self._enter()
        except Exception:  # noqa: BLE001 - 采集失败绝不冒泡
            _count_dropped()
            logger.debug("span(%s) enter failed", self._name, exc_info=True)
        return self._span

    def _enter(self) -> None:
        if not enabled():
            return
        # trace_kind 是"没有父 trace 时自建 trace 用的 kind 提示"，任何路径都不要落到 attrs
        kind_hint = self._kwargs.pop("trace_kind", None)
        rec = current_trace()
        if rec is None or rec.closed:
            # 无上下文（或父 trace 已收尾，如 create_task 里迟到的摘要素）→ 自建 trace，
            # 保证"每个 LLM 调用都可见"，也避免把 span 写进已投递的 trace。
            rec = start_trace(kind_hint or DEFAULT_KIND)
            if rec is None:
                return
            self._owns_trace = True
            self._trace_token = set_current_trace(rec)
        kwargs = dict(self._kwargs)
        retry_index = int(kwargs.pop("retry_index", 0) or 0)
        tool_name = kwargs.pop("tool_name", None)
        attrs = kwargs.pop("attrs", None) or {}
        attrs.update(kwargs)
        parent = current_span()
        # 父 span 已关闭（例如 SSE 回合先收尾、后台任务后跑到）→ 挂回 ENTRY 根，不留孤儿
        parent_id = rec.entry_span_id
        if parent is not None and not parent.closed and parent.span_id != rec.entry_span_id:
            parent_id = parent.span_id
        span = SpanRecord(
            span_id=new_span_id(),
            name=self._name,
            parent_span_id=parent_id,
            seq=rec.next_seq(),
            started_at=_utcnow(),
            span_kind="client" if self._name in CLIENT_SPAN_NAMES else "internal",
            retry_index=retry_index,
            tool_name=tool_name,
            attrs=attrs,
        )
        rec.spans.append(span)
        self._span = span
        self._token = set_current_span(span)

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            self._exit(exc)
        except Exception:  # noqa: BLE001 - 关闭失败也要把 contextvar 还原
            _count_dropped()
            logger.debug("span(%s) exit failed", self._name, exc_info=True)
        finally:
            if self._token is not None:
                with contextlib.suppress(Exception):
                    reset_current_span(self._token)
            if self._owns_trace:
                try:
                    finish_trace()
                except Exception:  # noqa: BLE001
                    _count_dropped()
                if self._trace_token is not None:
                    with contextlib.suppress(Exception):
                        reset_current_trace(self._trace_token)
        return False  # 绝不吞业务异常

    def _exit(self, exc: BaseException | None) -> None:
        span = self._span
        if span is None:
            return
        if exc is None:
            span.close(STATUS_OK)
            return
        if _is_abort(exc):
            span.close(STATUS_ABORTED, error_code="aborted", error_message=_msg(exc))
            return
        span.close(STATUS_ERROR, error_code=_error_code(exc), error_message=_msg(exc))


def span(name: str, **attrs: Any) -> _SpanCM:
    """打开一个 span（``retry_index`` / ``tool_name`` / ``attrs`` 为保留键，其余进 attrs）。"""
    return _SpanCM(name, attrs)


@contextmanager
def detached() -> Iterator[None]:
    """临时切断 trace 上下文（后台任务不希望挂到当前 trace 时使用）。"""
    t_tok = set_current_trace(None)
    s_tok = set_current_span(None)
    try:
        yield
    finally:
        reset_current_span(s_tok)
        reset_current_trace(t_tok)


# ---------------------------------------------------------------------------
# LLM 客户端回填钩子（app/audio/llm.py 调用；不改 yield 事件形状）
# ---------------------------------------------------------------------------
def note_llm_request(model: str | None, messages: list[dict[str, Any]] | None) -> None:
    """记录请求侧元数据（model / prompt）。**仅当内容捕获开启时**才留正文副本。"""
    try:
        s = current_span()
        if s is None or s.closed:
            return
        if model and not s.model:
            s.model = str(model)[:64]
        if content_capture_enabled() and messages:
            s.input_messages = [dict(m) for m in messages]
    except Exception:  # noqa: BLE001
        _count_dropped()


def note_llm_result(
    *,
    ttft_ms: int | None = None,
    finish_reason: str | None = None,
    model: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    output_text: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """回填 LLM 结果（TTFT / finish_reason / tokens / 正文）。

    为什么走"回填当前 span"而不是改 ``stream_rich`` 的事件形状：``stream_rich`` 的
    ``("delta"|"usage", payload)`` 契约被 ``turn_runner`` / 既有测试依赖，加新事件种类
    会让未识别的 payload 走进 ``MetaStreamSplitter.push()``（对 dict 做字符串拼接 → TypeError）。
    回填只写内存记录，调用方零感知。
    """
    try:
        s = current_span()
        if s is None or s.closed:
            return
        if ttft_ms is not None and s.ttft_ms is None:
            s.ttft_ms = max(int(ttft_ms), 0)
        if finish_reason and not s.finish_reason:
            s.finish_reason = str(finish_reason)[:32]
        if model and not s.model:
            s.model = str(model)[:64]
        if prompt_tokens is not None:
            s.prompt_tokens = int(prompt_tokens)
        if completion_tokens is not None:
            s.completion_tokens = int(completion_tokens)
        if output_text and content_capture_enabled():
            s.output_text = output_text
        if duration_ms is not None:
            s.attrs.setdefault("llm_duration_ms", int(duration_ms))
    except Exception:  # noqa: BLE001
        _count_dropped()


def note_error(exc: BaseException) -> None:
    """把业务异常翻译成 span 错误详情（HTTP 状态码 / 响应体，docs/50 §7.3 要求的"错误详情"）。"""
    try:
        s = current_span()
        if s is None or s.closed:
            return
        s.error_code = s.error_code or _error_code(exc)
        s.error_message = s.error_message or _msg(exc)
        status_code, body = _http_detail(exc)
        if status_code is not None:
            s.attrs.setdefault("http_status", status_code)
        if body:
            s.attrs.setdefault("error_body", body[:500])
    except Exception:  # noqa: BLE001
        _count_dropped()


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------
def _is_abort(exc: BaseException) -> bool:
    """中断类异常（取消 / 生成器关闭 / 进程退出信号）→ ``aborted`` 而非 ``error``。"""
    return isinstance(exc, (asyncio.CancelledError, GeneratorExit, KeyboardInterrupt, SystemExit))


def _msg(exc: BaseException | None) -> str | None:
    if exc is None:
        return None
    text = str(exc) or exc.__class__.__name__
    return text[:500]


def _error_code(exc: BaseException | None) -> str | None:
    if exc is None:
        return None
    resp = getattr(exc, "response", None)  # httpx.HTTPStatusError
    code = getattr(resp, "status_code", None) or getattr(exc, "status_code", None)
    if code is not None:
        return str(code)[:64]
    return exc.__class__.__name__[:64]


def _http_detail(exc: BaseException) -> tuple[int | None, str | None]:
    """从 httpx 异常里取 (状态码, 响应体)：``raise_for_status()`` 只留状态码，正文要自己捞。"""
    resp = getattr(exc, "response", None)
    if resp is None:
        return None, None
    status = getattr(resp, "status_code", None)
    body: str | None = None
    try:
        body = resp.text
    except Exception:  # noqa: BLE001 - 流式响应体可能已被消费
        body = None
    return status, body


def _apply_content_policy(rec: TraceRecord) -> None:
    """内容捕获闸门：默认关 → 零行；硬禁采 kind → 零行（并把原因记进 attrs）。"""
    if rec.kind in CONTENT_DENY_KINDS:
        rec.content_captured = False
        rec.attrs["content_capture"] = "denied"
        rec.attrs["content_capture_reason"] = "deny_list:thesis-bearing-kind"
        for s in rec.spans:
            s.input_messages = None
            s.output_text = None
        return
    if not content_capture_enabled():
        rec.content_captured = False
        rec.attrs.setdefault("content_capture", "disabled")
        return
    has_content = any(s.input_messages or s.output_text for s in rec.spans)
    rec.content_captured = has_content
    rec.attrs.setdefault("content_capture", "enabled" if has_content else "enabled_empty")


def _record_trace_metrics(rec: TraceRecord) -> None:
    """把 trace 结果喂进进程内指标（docs/50 §8.4：llm.* 来自 trace 聚合）。"""
    try:
        from app.console.ops.metrics import record_trace

        record_trace(rec)
    except Exception:  # noqa: BLE001 - 指标侧失败不影响 trace 落库
        logger.debug("record_trace metrics failed", exc_info=True)


def _count_dropped() -> None:
    with contextlib.suppress(Exception):
        get_sink().dropped_total += 1


def _utcnow():
    from datetime import UTC, datetime

    return datetime.now(UTC)


__all__ = [
    "CONTENT_DENY_KINDS",
    "DEFAULT_KIND",
    "content_capture_enabled",
    "detached",
    "enabled",
    "finish_trace",
    "note_error",
    "note_llm_request",
    "note_llm_result",
    "span",
    "start_trace",
    "trace",
]
