"""MetaExecutor 单测（docs/26 runtime/meta-executor）。

覆盖：命中合并（规则权威 + LLM 兜底 + 作废轮）、grammar 判定/归一、收尾判定。
修复前必失败语义：这些逻辑原内联在 orchestrator._dialog_turn，抽取后以纯函数可测；
「再练」口径（docs/14 §2.1）经 should_conclude/conclude 降级在此固化。
"""

from __future__ import annotations

import pytest
from app.agent.runtime.meta_executor import MetaExecutor, _parse_meta_json, compensate_meta
from app.practice.corpus import parse_corpus
from app.practice.meta import MetaResult

ex = MetaExecutor()

_CORPUS = parse_corpus(
    "I'd like a coffee, please.|请给我来杯咖啡\nCan I have a cappuccino?|卡布奇诺"
)


def _meta(
    grammar: dict | None = None, hits: list | None = None, conclude: bool = False
) -> MetaResult:
    return MetaResult(
        reply="ok",
        meta={"grammar": grammar, "corpus_hits": hits or [], "conclude": conclude},
        ok=True,
    )


def test_hits_rule_authority_with_llm_tail() -> None:
    # 规则命中 "I'd like a coffee, please."（达意）+ LLM 补充一个语义等价短语
    m = _meta(
        grammar={"score": 90, "errors": []},
        hits=[{"phrase": "Could I get one to go?", "state": "fix"}],
    )
    hits = ex.apply_hits("I'd like a coffee please", _CORPUS, m, "normal", [])
    phrases = [h["phrase"] for h in hits]
    assert "I'd like a coffee, please." in phrases
    assert hits[0]["state"] == "ok"  # 规则命中且无致命语法错
    assert len(hits) == 2  # 规则 1 + LLM 补充 1


def test_hits_voided_on_rescue_actions() -> None:
    # 行为等价：旧实现为 `action in ("normal","retry")`（retry 计命中——docs/14 §2.1
    # 注释与之不符，已登记待拍板；本次重构不改语义）；hint/demo 作废
    m = _meta(hits=[{"phrase": "I'd like a coffee, please.", "state": "ok"}])
    for action in ("hint", "demo"):
        assert ex.apply_hits("I'd like a coffee please", _CORPUS, m, action, []) == []
    assert len(ex.apply_hits("I'd like a coffee please", _CORPUS, m, "retry", [])) == 1


def test_hits_grammar_fix_state() -> None:
    m = _meta(grammar={"score": 58, "errors": [{"word": "coffee", "fix": "coffee"}]})
    hits = ex.apply_hits("I'd like a coffee please", _CORPUS, m, "normal", [])
    assert hits == [{"phrase": "I'd like a coffee, please.", "state": "fix"}]


def test_grammar_ok_default_true_without_meta() -> None:
    assert ex.grammar_ok(MetaResult(reply="x", meta=None, ok=False), []) is True
    assert ex.grammar_ok(_meta(grammar={"score": 60, "errors": []}), []) is True
    assert ex.grammar_ok(_meta(grammar={"score": 59, "errors": []}), []) is False


def test_effective_grammar_normalization() -> None:
    assert ex.effective_grammar(_meta(grammar={"score": 80, "errors": []}), []) == {
        "score": 80,
        "errors": [],
    }
    errs = [{"word": "x", "fix": "y"}]
    assert ex.effective_grammar(MetaResult(reply="x", meta=None, ok=False), errs) == {
        "score": 60,
        "errors": errs,
    }
    assert ex.effective_grammar(MetaResult(reply="x", meta=None, ok=False), []) is None


def test_should_conclude_rules() -> None:
    assert ex.should_conclude(_meta(conclude=True), 3, 8, "normal") is True
    assert ex.should_conclude(_meta(conclude=False), 8, 8, "normal") is True  # 轮次上限兜底
    assert ex.should_conclude(MetaResult(reply="x", meta=None, ok=False), 2, 8, "abandon") is True
    assert ex.should_conclude(_meta(conclude=False), 2, 8, "normal") is False


# ---------------------------------------------------------------------------
# 补偿调用（docs/26 §9.4：META 缺失后置提取）
# ---------------------------------------------------------------------------
class _JsonLLM:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.calls = 0

    async def chat(self, messages, temperature=0.7, max_tokens=512) -> str:
        self.calls += 1
        return self.raw


@pytest.mark.anyio
async def test_compensate_meta_parses_json() -> None:
    llm = _JsonLLM(
        '{"grammar":{"score":91,"errors":[]},"coach_note":"Nice!","corpus_hits":'
        '[{"phrase":"How much is it?","state":"ok"}],"difficulty_delta":0,"conclude":false}'
    )
    m = await compensate_meta(
        llm,
        reply_text="That'll be three dollars.",
        transcript="How much is it?",
        action="normal",
        concluded_by_turn=False,
    )
    assert m.ok and m.coach_note == "Nice!" and len(m.corpus_hits) == 1
    assert llm.calls == 1


@pytest.mark.anyio
async def test_compensate_meta_tolerates_prose_fence() -> None:
    llm = _JsonLLM('Here you go:\n```json\n{"conclude":false}\n```')
    m = await compensate_meta(
        llm, reply_text="x", transcript="", action="normal", concluded_by_turn=False
    )
    assert m.ok and m.meta == {"conclude": False}


@pytest.mark.anyio
async def test_compensate_meta_failure_degrades() -> None:
    llm = _JsonLLM("sorry, no json today")
    m = await compensate_meta(
        llm, reply_text="x", transcript="", action="normal", concluded_by_turn=False
    )
    assert m.ok is False and m.meta is None


def test_parse_meta_json_malformed_grammar_guarded() -> None:
    # 防御：grammar 裸数字（冒烟实测）→ ok=True 但不崩溃（grammar_ok 判 dict）
    m = _parse_meta_json('{"grammar":90,"coach_note":"ok"}', "reply")
    assert m.ok is True
    assert ex.grammar_ok(m, []) is True  # 非 dict → 默认达意（不崩）
