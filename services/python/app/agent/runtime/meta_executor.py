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
        """无语法判定时默认达意（规则通道已确认说出表达）——与旧 _grammar_ok 同语义；
        防御：模型可能输出 grammar 为裸数字/字符串（冒烟实测），非 dict 视为无判定。"""
        g = meta.grammar if meta else None
        if isinstance(g, dict):
            return int(g.get("score", 100)) >= 60
        return True

    def effective_grammar(self, meta: MetaResult, grammar_errors: list) -> dict | None:
        """grammar 归一：模型给 → 用模型的；否则有错误清单 → 规则降级 60 分；否则 None。"""
        return meta.grammar or (grammar_errors and {"score": 60, "errors": grammar_errors}) or None

    def should_conclude(self, meta: MetaResult, turn_index: int, limit: int, action: str) -> bool:
        """收尾判定（meta.conclude 或轮次上限或用户放弃）。"""
        return bool(meta.conclude) or turn_index >= limit or action == "abandon"


_COMPENSATE_SYSTEM = (
    "You extract structured metadata for one turn of an English speaking-practice role-play. "
    "Reply with ONLY a JSON object of exactly this shape (no prose, no code fence):\n"
    '{"grammar":{"score":0-100,"errors":[{"word":"...","fix":"..."}]},'
    '"coach_note":"<=15 words","corpus_hits":[{"phrase":"...","state":"ok|fix"}],'
    '"difficulty_delta":-1|0|1,"conclude":false,'
    '"content":{"score":0-100,"note":"<=20 words"},'
    '"vocab":{"score":0-100,"note":"<=20 words"}}'
)


async def compensate_meta(
    llm,
    *,
    reply_text: str,
    transcript: str,
    action: str,
    concluded_by_turn: bool,
) -> MetaResult:
    """META 缺失补偿调用（docs/26 §9.4：流式未守契约时后置一次性提取，temperature 0.2）。

    代价：每补偿轮多 1 次 LLM 调用（演示 20 轮 × ~40% ≈ 8 次 ≤ 30/h 桶，docs/14 登记）；
    失败 → 返回 ok=False（编排器走既有降级：rule conclude 兜底，不伪造元数据）。
    """
    user = (
        "Turn data:\n"
        f"- learner speech (ASR): {transcript or '(none)'}\n"
        f"- action: {action}\n"
        f"- assistant reply: {reply_text}\n"
        "Note: conclude=true only if the conversation reached the turn limit or the user ended "
        f"(turn limit reached: {concluded_by_turn}).\n"
        "corpus_hits: phrases from the reply that the learner actually expressed (empty if none); "
        "state=ok if no fatal grammar error, else fix.\n"
        "content.score = relevance & fullness of this turn to the current topic (0-100); "
        "vocab.score = vocabulary variety & word choice (0-100); notes are short, actionable."
    )
    try:
        fn = getattr(llm, "chat_with_usage", None)
        if fn is not None:
            raw, usage = await fn(
                [
                    {"role": "system", "content": _COMPENSATE_SYSTEM},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=300,
            )
            if usage:
                try:
                    from app.agent.domains.usage import log_usage

                    log_usage("meta_compensate", usage, meta=None)
                except Exception:
                    pass
        else:
            raw = await llm.chat(
                [
                    {"role": "system", "content": _COMPENSATE_SYSTEM},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=300,
            )
    except Exception:
        return MetaResult(reply=reply_text, meta=None, ok=False)
    return _parse_meta_json(raw, reply_text)


def _parse_meta_json(raw: str, reply_text: str) -> MetaResult:
    """宽松提取首个 {…} 并解析（容忍模型加废话/围栏）。"""
    import json

    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return MetaResult(reply=reply_text, meta=None, ok=False)
    try:
        meta = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return MetaResult(reply=reply_text, meta=None, ok=False)
    if not isinstance(meta, dict):
        return MetaResult(reply=reply_text, meta=None, ok=False)
    return MetaResult(reply=reply_text, meta=meta, ok=True)


__all__ = ["MetaExecutor", "compensate_meta"]
