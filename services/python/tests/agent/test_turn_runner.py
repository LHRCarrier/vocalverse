"""TurnRunner / MetaStreamSplitter 单测（docs/26 runtime/turn-runner）。

覆盖：跨 chunk 标记拆分、二重标记泄漏截断（防 rfind 污染回复）、TurnRunner 全流程
（FakeLLM 协议）、泄漏降级。修复前必失败语义：旧 orchestrator 内联循环无泄漏防护
（二重标记会经 rfind 锚定污染 reply），本文件用例在旧实现下不存在。
"""

from __future__ import annotations

import pytest
from app.agent.runtime.turn_runner import MetaStreamSplitter, TurnRunner
from app.practice.meta import MARKER, render_meta


def test_splitter_cross_chunk_marker() -> None:
    s = MetaStreamSplitter()
    out: list[str] = []
    out += s.push("Hello there, ")
    out += s.push("let me [-ME")
    out += s.push("TA-]{...}")
    full, meta, pending = s.finish()
    assert "".join(out) == "Hello there, let me "
    assert full == "Hello there, let me "
    assert meta == "{...}"
    assert s.found and s.leak_count == 0
    assert pending is None


def test_splitter_second_marker_truncates_tail() -> None:
    """二重标记：尾段在第二个标记处截断（否则 extract_meta rfind 会锚定并污染 reply）。"""
    s = MetaStreamSplitter()
    s.push("Great job. " + MARKER + '{"grammar":null}')
    s.push(" " + MARKER + "leaked")
    full, meta, _ = s.finish()
    assert s.leak_count == 1
    assert meta.strip() == '{"grammar":null}'
    assert full == "Great job. "


def test_splitter_keeps_partial_marker_boundary() -> None:
    s = MetaStreamSplitter()
    out: list[str] = []
    out += s.push("abc[-")
    out += s.push("META-]x")
    assert "".join(out) == "abc"
    assert s.found and s.finish()[1] == "x"


class _FakeLLM:
    """协议同 FakeLLMClient：正文 3 段 + 尾部 META。"""

    async def stream(self, messages):
        for c in ["Of course! ", "Would you like it hot ", "or iced?"]:
            yield c
        yield render_meta(
            grammar={"score": 92, "errors": []},
            coach_note="Nice and clear!",
            corpus_hits=[{"phrase": "I would like a coffee, please", "state": "ok"}],
            difficulty_delta=0,
            conclude=False,
        )


class _LeakyLLM:
    async def stream(self, messages):
        yield "Great job! "
        yield MARKER + '{"grammar":null,"conclude":false} '
        yield MARKER + "leaked junk"


@pytest.mark.anyio
async def test_turn_runner_full_flow() -> None:
    runner = TurnRunner(_FakeLLM())
    deltas = [d async for d in runner.run([])]
    assert "".join(deltas) == "Of course! Would you like it hot or iced?"
    assert runner.result is not None
    assert runner.result.reply_text == "Of course! Would you like it hot or iced?"
    assert runner.result.meta.ok
    assert runner.result.meta.grammar["score"] == 92
    assert runner.result.leaked is False


@pytest.mark.anyio
async def test_turn_runner_leak_degrades_meta() -> None:
    runner = TurnRunner(_LeakyLLM())
    deltas = [d async for d in runner.run([])]
    assert "".join(deltas) == "Great job! "
    assert runner.result is not None
    assert runner.result.leaked is True
    # 修复必失败点：旧实现（meta 尾段含标记 + rfind 锚定第二个标记）→ reply 被污染
    # 成 "Great job! [-META-]{...}..."；本实现泄漏降级为纯正文
    assert runner.result.reply_text == "Great job!"
    assert runner.result.meta.ok is False
