"""`[-META-]` 尾部标记块解析（docs/14 §3.4 / docs/18 P2 POC 协议）。

LLM 流式输出约定：回复纯文本，最后输出一行
    [-META-]{grammar:{score,errors[]}, coach_note, corpus_hits[], difficulty_delta, conclude}
回复中禁止出现该标记；META 解析失败 → 本轮无元数据，conclude 由规则兜底（turn_count>=8）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

MARKER = "[-META-]"

# 宽松提取：允许标记后有空白/前导，但要求 JSON 在行尾闭合
_META_RE = re.compile(re.escape(MARKER) + r"\s*(\{.*\})\s*$", re.S)


@dataclass
class MetaResult:
    reply: str
    meta: dict | None
    ok: bool  # meta 是否成功解析
    raw_meta: str = ""

    @property
    def grammar(self) -> dict | None:
        return (self.meta or {}).get("grammar")

    @property
    def coach_note(self) -> str | None:
        return (self.meta or {}).get("coach_note")

    @property
    def corpus_hits(self) -> list[dict]:
        return (self.meta or {}).get("corpus_hits") or []

    @property
    def difficulty_delta(self) -> int:
        return int((self.meta or {}).get("difficulty_delta") or 0)

    @property
    def conclude(self) -> bool:
        return bool((self.meta or {}).get("conclude"))


def extract_meta(full_text: str) -> MetaResult:
    """从完整流式文本提取回复与尾部 META；找不到/解析失败 → meta=None。"""
    idx = full_text.rfind(MARKER)
    if idx < 0:
        return MetaResult(reply=full_text.strip(), meta=None, ok=False)
    reply = full_text[:idx].strip()
    tail = full_text[idx + len(MARKER) :].strip()
    m = _META_RE.match(full_text[idx:])
    # 优先用锚定正则（容忍行尾空白），失败再整段尝试
    raw = ""
    if m:
        raw = m.group(1)
    else:
        # 兜底：截取从首个 { 到最后一个 }
        start, end = tail.find("{"), tail.rfind("}")
        if start >= 0 and end > start:
            raw = tail[start : end + 1]
    if not raw:
        return MetaResult(reply=reply, meta=None, ok=False, raw_meta=tail)
    try:
        meta = json.loads(raw)
        if not isinstance(meta, dict):
            return MetaResult(reply=reply, meta=None, ok=False, raw_meta=raw)
        return MetaResult(reply=reply, meta=meta, ok=True, raw_meta=raw)
    except json.JSONDecodeError:
        return MetaResult(reply=reply, meta=None, ok=False, raw_meta=raw)


def render_meta(
    grammar: dict | None,
    coach_note: str | None,
    corpus_hits: list[dict],
    difficulty_delta: int,
    conclude: bool,
) -> str:
    """按约定渲染 META 行（供 Fake/POC 构造与单测）。"""
    payload = {
        "grammar": grammar,
        "coach_note": coach_note,
        "corpus_hits": corpus_hits,
        "difficulty_delta": difficulty_delta,
        "conclude": conclude,
    }
    return f"{MARKER}{json.dumps(payload, ensure_ascii=False)}"


__all__ = ["MARKER", "MetaResult", "extract_meta", "render_meta"]
