"""trace 采集器测试（docs/50 §14.2 第 1 条：异常路径也必须关闭 span 并标 error）。

**为什么这些用例在修复前必红**（回归价值）：
- ``test_exception_path_closes_span_with_error``：如果 ``span()`` 只用 ``try/finally`` 之外
  的裸实现（或干脆不处理异常），span 会停在"未关闭"状态 —— 断言 ``closed is True`` 直接失败；
- ``test_no_dangling_spans``：遍历整条 trace 断言没有任何 span 悬空
  （DSH 原则之四：错误/中断/未完成流都要收口，绝不留悬挂 span）；
- ``test_cancelled_error_marked_aborted``：``asyncio.CancelledError`` 继承 ``BaseException``，
  只捕 ``Exception`` 的实现会漏掉它（用户按"停止"就是这条路径）。
"""

from __future__ import annotations

import asyncio

import pytest
from app.console.trace import recorder
from app.console.trace.context import (
    SPAN_ENTRY,
    SPAN_LLM,
    SPAN_STEP,
    current_span,
    current_trace,
)
from app.console.trace.recorder import finish_trace, span, start_trace, trace


def test_span_tree_parenting_is_automatic() -> None:
    """ENTRY → AGENT → STEP → LLM 的父子关系由 ContextVar 自动推导（不改函数签名）。"""
    with trace(kind="turn") as rec:
        assert rec is not None
        with span("AGENT"), span("STEP"), span("LLM", retry_index=0):
            pass
    assert rec is not None
    names = [s.name for s in rec.spans]
    assert names == [SPAN_ENTRY, "AGENT", SPAN_STEP, SPAN_LLM]
    entry, agent, step, llm = rec.spans
    assert agent.parent_span_id == entry.span_id
    assert step.parent_span_id == agent.span_id
    assert llm.parent_span_id == step.span_id
    assert llm.span_kind == "client"
    assert all(s.closed for s in rec.spans)


def _run_raising(exc: BaseException, out: dict) -> None:
    """在 trace+LLM span 内抛指定异常，并把两者回传给调用方断言（异常路径探针）。"""
    with trace(kind="turn") as rec, span("LLM") as s:
        out["rec"], out["span"] = rec, s
        raise exc


def test_exception_path_closes_span_with_error() -> None:
    """异常路径：span 必须关闭且标 ``error``（修复前会留悬挂 span → 本用例红）。"""
    out: dict = {}
    with pytest.raises(ValueError):
        _run_raising(ValueError("boom"), out)
    rec, llm_span = out["rec"], out["span"]
    assert rec is not None and llm_span is not None
    assert llm_span.closed is True, "异常路径必须关闭 span（否则瀑布图上是永久活动条）"
    assert llm_span.status == "error"
    assert llm_span.error_code == "ValueError"
    assert "boom" in (llm_span.error_message or "")
    assert llm_span.ended_at is not None
    assert rec.status == "error"
    assert rec.error_message == "boom"


def test_no_dangling_spans_after_finish() -> None:
    """整条 trace 收尾后不得有任何未关闭 span（DSH 原则之四的硬断言）。"""
    with trace(kind="turn") as rec, span("AGENT"), span("STEP"):
        try:
            with span("LLM"):
                raise RuntimeError("llm down")
        except RuntimeError:
            pass
    assert rec is not None
    dangling = [s.name for s in rec.spans if not s.closed or s.ended_at is None]
    assert dangling == [], f"存在悬挂 span: {dangling}"


@pytest.mark.asyncio
async def test_cancelled_error_marked_aborted() -> None:
    """``asyncio.CancelledError``（BaseException 子类）→ ``aborted`` 且照样收口。"""
    out: dict = {}
    with pytest.raises(asyncio.CancelledError):
        _run_raising(asyncio.CancelledError(), out)
    rec, llm_span = out["rec"], out["span"]
    assert rec is not None and llm_span is not None
    assert llm_span.status == "aborted"
    assert all(s.closed for s in rec.spans)


def test_span_when_trace_never_started_still_closes() -> None:
    """没有显式 start_trace 也要能采集（LLM 调用点可能没人在外层开 trace）。"""
    assert current_trace() is None
    with span("LLM", trace_kind="llm") as llm_span:
        pass
    assert llm_span is not None
    assert llm_span.parent_span_id is not None  # 自建 trace 的 ENTRY
    assert current_span() is None


def test_recorder_failure_never_propagates(monkeypatch) -> None:
    """采集层自身异常必须被吞掉（docs/50 §7.3 末条）：业务代码不受影响。"""
    monkeypatch.setattr(recorder, "start_trace", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    with span("LLM"):
        reached = True
    assert reached is True


def test_finish_trace_closes_unclosed_span_as_incomplete() -> None:
    """手工只开不收 → finish 兜底标 ``incomplete``（不是 ok，避免"看起来成功"）。"""
    rec = start_trace("turn")
    assert rec is not None
    inner = span("LLM")
    inner.__enter__()
    finish_trace()
    assert inner._span is not None
    assert inner._span.status == "incomplete"


def test_llm_retry_siblings_share_step_parent() -> None:
    """重试可见：同一 STEP 下两次 LLM 尝试，``retry_index`` 递增、父节点相同。"""
    with trace(kind="turn") as rec, span("STEP"):
        with span("LLM", retry_index=0):
            pass
        with span("LLM", retry_index=1):
            pass
    assert rec is not None
    llms = [s for s in rec.spans if s.name == SPAN_LLM]
    assert [s.retry_index for s in llms] == [0, 1]
    assert llms[0].parent_span_id == llms[1].parent_span_id


@pytest.mark.asyncio
async def test_turn_runner_emits_llm_span_under_current_trace() -> None:
    """真实调用点验证：TurnRunner（回合流式调用点）在既有 trace 下产出 LLM span。"""
    from app.agent.runtime.turn_runner import TurnRunner
    from app.audio.stubs import FakeLLMClient

    with trace(kind="turn") as rec:
        runner = TurnRunner(FakeLLMClient())
        async for _ in runner.run([{"role": "user", "content": "hi"}]):
            pass
    assert rec is not None
    assert [s.name for s in rec.spans] == [SPAN_ENTRY, SPAN_LLM]
    assert rec.spans[1].parent_span_id == rec.spans[0].span_id
    assert all(s.closed for s in rec.spans)
