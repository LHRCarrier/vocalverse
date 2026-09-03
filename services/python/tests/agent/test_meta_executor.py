"""MetaExecutor 单测（docs/26 runtime/meta-executor）。

覆盖：命中合并（规则权威 + LLM 兜底 + 作废轮）、grammar 判定/归一、收尾判定。
修复前必失败语义：这些逻辑原内联在 orchestrator._dialog_turn，抽取后以纯函数可测；
「再练」口径（docs/14 §2.1）经 should_conclude/conclude 降级在此固化。
"""

from __future__ import annotations

from app.agent.runtime.meta_executor import MetaExecutor
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
