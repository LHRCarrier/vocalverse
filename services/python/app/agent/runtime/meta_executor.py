"""META 结构化输出权威执行器（docs/26 runtime/meta-executor：ai4u tool-executor 的对应物）。

把模型 `[-META-]` 输出落实为编排器决策——「结构化输出即工具调用」：
- 命中合并：规则通道为权威（match_rule），LLM 兜底（语义等价/±1 词）仅边缘修正；
  retry/hint/demo 轮命中作废（docs/14 §2.1）；
- grammar 判定：无致命语法错 → 达意（命中 ok）；grammar 归一（LLM 未给时按规则降级）；
- 收尾判定：meta.conclude 或轮次上限（规则兜底，防 META 解析失败漏收尾——docs/16 §5 降级语义）。

聚合次第（docs/14 §3.5）：规则命中 state 由 grammar_ok 决定；LLM 补充命中保留其 state。
"""

from __future__ import annotations

from collections.abc import Sequence

from app.practice.corpus import CorpusItem, match_rule
from app.practice.meta import MetaResult


class MetaExecutor:
    """纯函数集合（无状态；实例化仅为语义分组，也可按模块函数使用）。"""

    def apply_hits(
        self,
        transcript: str,
        corpus: Sequence[CorpusItem],
        meta: MetaResult,
        action: str,
        grammar_errors: list,
    ) -> list[dict]:
        """O(1) 命中合并（规则权威 + LLM 兜底）；非 normal/retry 轮 → 作废（返回 []）。"""
        if action not in ("normal", "retry"):
            return []
        rule_hits = match_rule(transcript, corpus)
        grammar_ok = self.grammar_ok(meta, grammar_errors)
        hits = [{"phrase": p, "state": "ok" if grammar_ok else "fix"} for p in rule_hits]
        seen = set(rule_hits)
        for h in meta.corpus_hits or []:
            phrase = h.get("phrase") if isinstance(h, dict) else h
            if phrase and phrase not in seen:
                state_hit = h.get("state", "ok") if isinstance(h, dict) else "ok"
                hits.append({"phrase": str(phrase), "state": state_hit})
                seen.add(str(phrase))
        return hits

    def grammar_ok(self, meta: MetaResult, grammar_errors: list) -> bool:
        """无语法判定时默认达意（规则通道已确认说出表达）——与旧 _grammar_ok 同语义。"""
        if meta and meta.grammar:
            return int(meta.grammar.get("score", 100)) >= 60
        return True

    def effective_grammar(self, meta: MetaResult, grammar_errors: list) -> dict | None:
        """grammar 归一：模型给 → 用模型的；否则有错误清单 → 规则降级 60 分；否则 None。"""
        return meta.grammar or (grammar_errors and {"score": 60, "errors": grammar_errors}) or None

    def should_conclude(self, meta: MetaResult, turn_index: int, limit: int, action: str) -> bool:
        """收尾判定（meta.conclude 或轮次上限或用户放弃）。"""
        return bool(meta.conclude) or turn_index >= limit or action == "abandon"


__all__ = ["MetaExecutor"]
