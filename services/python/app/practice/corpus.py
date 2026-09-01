"""语言点覆盖度：target_corpus 解析与规则通道匹配（docs/14 §3.5）。

- 语料存储格式：Text 字段，每行一条 `English phrase|中文释义`（data/seed/scenarios.json 同款）；
- 规则通道为**权威**（归一化后子串/词序匹配）；LLM 兜底命中由 META 的 corpus_hits 承载
  （语义等价、±1 词），仅作边缘修正；
- 命中双态（docs/14 §2.1）：ok=自然达意（该轮无致命语法错）；fix=说出但需纠错；
  retry/hint/demo 轮次命中作废（编排器在 action 分支上过滤）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WORD_RE = re.compile(r"[a-z0-9']+")
_STRIP_LEADING = re.compile(r"^(please\s+)?(could you\s+)?(can you\s+)?(i would like\s+)?", re.I)
# 归一化：小写、去标点、去修饰性冠词（可选，保持短语可匹配性）
_ARTICLES = ("the", "a", "an")


@dataclass(frozen=True)
class CorpusItem:
    phrase: str  # 英文表达（作为参考句展示/提示）
    gloss: str  # 中文释义
    _norm: str  # 归一化后的匹配键（不含冠词/标点）

    def display(self) -> str:
        return self.phrase


def parse_corpus(raw: str | None) -> list[CorpusItem]:
    """解析 `phrase|释义` 行格式；空行/坏行跳过。"""
    items: list[CorpusItem] = []
    if not raw:
        return items
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            phrase, gloss = line.split("|", 1)
        else:
            phrase, gloss = line, ""
        phrase = phrase.strip()
        if not phrase:
            continue
        items.append(CorpusItem(phrase=phrase, gloss=gloss.strip(), _norm=normalize(phrase)))
    return items


def normalize(text: str) -> str:
    """小写 + 只留单词（去标点）；可选：去掉 be 动词/助动词弱读无益，保持原样。"""
    return " ".join(_WORD_RE.findall(text.lower()))


def _remove_articles(norm: str) -> str:
    tokens = [t for t in norm.split(" ") if t and t not in _ARTICLES]
    return " ".join(tokens)


def match_rule(user_text: str, corpus: list[CorpusItem]) -> list[str]:
    """规则通道（权威）：返回命中的 phrase 列表。

    策略（宽松但防误判）：
    - 归一化用户转写 → 去冠词 → 短语归一化去冠词；
    - 用户文本**包含**短语（词序一致）即命中——短语为整句骨架时允许辅词差异，
      因此对子串做「去标点去冠词」比较即可；
    - 短语长度 ≥2 词才有效（防止单字符误命中）。
    """
    user_norm = _remove_articles(normalize(user_text))
    hits: list[str] = []
    for item in corpus:
        item_norm = _remove_articles(item._norm)
        if len(item_norm.split(" ")) < 2:
            continue
        if item_norm in user_norm:
            hits.append(item.phrase)
    return hits


def meta_hits_to_phrases(meta_corpus_hits: list[dict]) -> list[str]:
    """META 中 corpus_hits 的短语列表（LLM 兜底；格式不定时容错）。"""
    phrases: list[str] = []
    for h in meta_corpus_hits:
        if isinstance(h, dict):
            phrase = h.get("phrase")
            if phrase:
                phrases.append(str(phrase))
        elif isinstance(h, str):
            phrases.append(h)
    return phrases
