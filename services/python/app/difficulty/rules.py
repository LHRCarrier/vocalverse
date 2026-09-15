"""素材难度专家规则：三维度打分 + 场景聚合（**Python 写方**；local/28 §2.1 + local/32 修订）。

维度（均 1~5，0.5 步长；纯 Python stdlib，无 numpy——40 条量级阈值映射无向量化收益）：
- **词汇复杂度** vocab：`0.5·CEFR 语义锚定 + 0.5·文本统计`
  （CEFR 锚定表 local/32 A-1.1；混合式 local/32 A-1.2 修"长词=难词"对学习者高频长词的误伤）；
- **句法复杂度** syntax（三维度补全，local/32 A-1.3）：`0.5·平均句长 + 0.5·从句/嵌套密度`；
- **发音难点** pron：难音素模式 + 词末辅音 + 音节数（面向中文母语者）。

场景聚合：逐句 → 逐维度 `mean + λ·(max−mean)`（λ=0.5，local/27 §1）→ 加权
`prior = 0.4·M(vocab) + 0.2·M(syntax) + 0.4·M(pron)`（A-1.3：口语输出负荷为主）。
映射 `M(k)=30+15·(k−1)`（A-1.2 不对称：1→30/3→60/5→90，修 local/28 的向心偏置）。

CEFR 锚定（A-1.1 语义标尺，供审计/答辩）：1=高中基础词、2=初中高频、3=四级高频、
4=六级/职场学术、5=雅思学术。注：无 CEFR 词频库时用"共同学习者白名单 + 学术后缀启发式"
作为代理（P2 可换真词表）。
"""

from __future__ import annotations

import math
import re
from statistics import mean

# ---------------------------------------------------------------------------
# CEFR 语义锚定（local/32 A-1.1）+ 代理词集
# ---------------------------------------------------------------------------
# 共同学习者高频词（A1-A2，即便较长也不难）——修"长词=难词"对 junior/student/communication 的误伤
COMMON_LEARNER = {
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "a",
    "an",
    "the",
    "is",
    "are",
    "am",
    "have",
    "has",
    "like",
    "want",
    "please",
    "thank",
    "here",
    "there",
    "this",
    "that",
    "can",
    "where",
    "what",
    "when",
    "how",
    "much",
    "many",
    "book",
    "team",
    "window",
    "plane",
    "coffee",
    "gate",
    "seat",
    "schedule",
    "luggage",
    "baggage",
    "english",
    "student",
    "junior",
    "senior",
    "majoring",
    "communication",
    "library",
    "history",
    "passport",
    "suitcase",
    "interview",
    "appointment",
    "customer",
    "travel",
    "borrow",
    "keep",
    "open",
    "close",
    "find",
    "meet",
    "work",
    "school",
}
# 学员词频代理：非白名单的词占比 → 1~5（生词率代理，local/32 A-1.2 的 0.3 项）
_MISS_VOCAB_RATIO = ((0.10, 1), (0.22, 2), (0.36, 3), (0.50, 4), (1.0, 5))

# ---------------------------------------------------------------------------
# 词汇统计阈值表（值 ≤ 上界 → 分；与 local/28 一致）
# ---------------------------------------------------------------------------
_VOCAB_FEATURE = {
    "avg_len": ((4.0, 1), (4.6, 2), (5.2, 3), (5.8, 4), (math.inf, 5)),
    "long_ratio": ((0.05, 1), (0.10, 2), (0.18, 3), (0.28, 4), (1.0, 5)),
    "syllables": ((1.2, 1), (1.4, 2), (1.6, 3), (1.8, 4), (9.0, 5)),
}
# 句法阈值表
_SYNTAX_FEATURE = {
    "sent_len": ((6.0, 1), (9.0, 2), (13.0, 3), (18.0, 4), (math.inf, 5)),
    "clause": ((0.0, 1), (1.0, 2), (2.0, 3), (3.0, 4), (math.inf, 5)),  # 从属连词数/句
}
# 发音阈值表
_PRON_FEATURE = {
    "hard_ratio": ((0.08, 1), (0.15, 2), (0.25, 3), (0.35, 4), (1.0, 5)),
    "coda_ratio": ((0.30, 1), (0.45, 2), (0.60, 3), (0.75, 4), (1.0, 5)),
    "syllables": _VOCAB_FEATURE["syllables"],
}

HARD_PATTERNS = (
    (r"th", "θ/ð"),
    (r"sh|sure|sion\b|tion\b", "ʃ"),
    (r"\bch|ture\b|tch", "tʃ"),
    (r"dge|\bge\b|\bj\b", "dʒ"),
    (r"\br", "r"),
    (r"l\b", "dark-l"),
    (r"\bv", "v"),
    (r"\bw", "w"),
    (r"^[bcdfgpqrstvz]{2,}", "cluster"),
)
# 学术/低频词后缀（B2+ 启发式；与白名单互斥）
_ACADEMIC_SUFFIX = ("tion", "sion", "ment", "ity", "ogy", "ance", "ence", "coordinat", "responsib")


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def _syllables(word: str) -> int:
    v = len(re.findall(r"[aeiouy]+", word))
    if word.endswith("e") and len(word) > 2 and not word.endswith(("le", "ee")):
        v = max(1, v - 1)
    return v


def _threshold(value: float, table) -> float:
    for upper, score in table:
        if value <= upper:
            return float(score)
    return 5.0


# ---------------------------------------------------------------------------
# 词汇复杂度 1~5：CEFR 语义锚定（0.5）+ 文本统计（0.5）
# ---------------------------------------------------------------------------
def _cefr_band(text: str) -> float:
    """CEFR 语义锚定（1~5）：白名单词=1(容易)、学术后缀词=5(难)、其余按长度 2~4。"""
    ws = _words(text)
    if not ws:
        return 1.0
    band = 0.0
    for w in ws:
        if w in COMMON_LEARNER:
            band += 1.0
        elif len(w) >= 7 and any(w.endswith(s) for s in _ACADEMIC_SUFFIX):
            band += 5.0
        elif len(w) >= 7:
            band += 4.0
        elif len(w) >= 5:
            band += 3.0
        else:
            band += 2.0
    return band / len(ws)


def _miss_ratio(text: str) -> float:
    """生词率代理：不在白名单的词占比（0~1）。"""
    ws = _words(text)
    if not ws:
        return 0.0
    return sum(1 for w in ws if w not in COMMON_LEARNER) / len(ws)


def vocab_score(text: str) -> float:
    """词汇复杂度 1~5：0.5·CEFR 锚定 + 0.3·生词率 + 0.2·文本统计（local/32 A-1.2）。"""
    ws = _words(text)
    if not ws:
        return 1.0
    cefr = _cefr_band(text)
    miss = _threshold(_miss_ratio(text), _MISS_VOCAB_RATIO)
    text_stat = mean(
        [
            _threshold(mean(len(w) for w in ws), _VOCAB_FEATURE["avg_len"]),
            _threshold(sum(1 for w in ws if len(w) >= 7) / len(ws), _VOCAB_FEATURE["long_ratio"]),
            _threshold(mean(_syllables(w) for w in ws), _VOCAB_FEATURE["syllables"]),
        ]
    )
    return round(0.5 * cefr + 0.3 * miss + 0.2 * text_stat, 1)


# ---------------------------------------------------------------------------
# 句法复杂度 1~5（A-1.3 补全）：0.5·平均句长 + 0.5·从句/嵌套密度
# ---------------------------------------------------------------------------
_SUBORD = (
    "because",
    "although",
    "though",
    "if",
    "when",
    "while",
    "that",
    "which",
    "who",
    "where",
    "before",
    "after",
    "since",
    "until",
    "unless",
)


def syntax_score(text: str) -> float:
    """句法复杂度 1~5：平均句长 + 从属连词密度（近似从句密度）。"""
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if not sentences:
        return 1.0
    sent_len = mean(len(_words(s)) for s in sentences)
    subord = sum(1 for w in _words(text) if w in _SUBORD) / len(sentences)
    return round(
        mean(
            [
                _threshold(sent_len, _SYNTAX_FEATURE["sent_len"]),
                _threshold(subord, _SYNTAX_FEATURE["clause"]),
            ]
        ),
        1,
    )


# ---------------------------------------------------------------------------
# 发音难点 1~5（面向中文母语者）
# ---------------------------------------------------------------------------
def pron_score(text: str) -> float:
    ws = _words(text)
    if not ws:
        return 1.0
    hard = sum(1 for w in ws if any(re.search(p, w) for p, _ in HARD_PATTERNS)) / len(ws)
    coda = sum(1 for w in ws if re.search(r"[b-df-hj-np-tv-z]$", w)) / len(ws)
    syll = mean(_syllables(w) for w in ws)
    return round(
        mean(
            [
                _threshold(hard, _PRON_FEATURE["hard_ratio"]),
                _threshold(coda, _PRON_FEATURE["coda_ratio"]),
                _threshold(syll, _PRON_FEATURE["syllables"]),
            ]
        ),
        1,
    )


# ---------------------------------------------------------------------------
# 映射与聚合
# ---------------------------------------------------------------------------
def dim_to_100(k: float) -> float:
    """1~5 → 0-100（A-1.2 不对称：1→30/3→60/5→90，修向心偏置）。"""
    return 30.0 + (k - 1.0) * 15.0


def _level_for(est: float) -> str:
    if est >= 85:
        return "L4"
    if est >= 70:
        return "L3"
    if est >= 55:
        return "L2"
    return "L1"


def scenario_prior(lines: list[str], lam: float = 0.5) -> dict:
    """逐句三维度 → 逐维度 λ 聚合 → 加权映射 100（local/31 §2.2）。"""
    per_line = [
        {"vocab": vocab_score(t), "syntax": syntax_score(t), "pron": pron_score(t)} for t in lines
    ]
    dims = {}
    for d in ("vocab", "syntax", "pron"):
        vals = [row[d] for row in per_line]
        m, mx = mean(vals), max(vals)
        dims[d] = round(m + lam * (mx - m), 2)
    prior = (
        0.4 * dim_to_100(dims["vocab"])
        + 0.2 * dim_to_100(dims["syntax"])
        + 0.4 * dim_to_100(dims["pron"])
    )
    return {
        "per_line": per_line,
        "dims": dims,
        "prior": round(prior, 2),
        "level": _level_for(prior),
        "source": "expert",
    }


# ---------------------------------------------------------------------------
# 影子跟读三维度（local/28 §2.2）：语速 wps / 停顿密度 / 连读密度
# ---------------------------------------------------------------------------
_SHADOW_TABLE = {
    # 值≤上界 → 分（wps/link 用 ≤）
    "wps": ((1.5, 1), (1.8, 2), (2.2, 3), (2.6, 4), (math.inf, 5)),
    "link": ((3.0, 1), (6.0, 2), (10.0, 3), (14.0, 4), (math.inf, 5)),
    # 值≥下界 → 分（pause 用 ≥：停顿越少越难）
    "pause": ((16.0, 1), (12.0, 2), (8.0, 3), (4.0, 4), (0.0, 5)),
}
W_SHADOW = {"wps": 0.4, "pause": 0.3, "link": 0.3}


def _threshold_ge(value: float, table) -> float:
    for lower, score in table:
        if value >= lower:
            return float(score)
    return 1.0


def shadow_prior(wps: float, pause_per_min: float, links_per_100w: float) -> dict:
    """影子跟读三维度 → 1~5 → 加权 → 100（权重 0.4/0.3/0.3，语速主导）。"""
    dims = {
        "wps": _threshold(wps, _SHADOW_TABLE["wps"]),
        "pause": _threshold_ge(pause_per_min, _SHADOW_TABLE["pause"]),
        "link": _threshold(links_per_100w, _SHADOW_TABLE["link"]),
    }
    prior = (
        W_SHADOW["wps"] * dim_to_100(dims["wps"])
        + W_SHADOW["pause"] * dim_to_100(dims["pause"])
        + W_SHADOW["link"] * dim_to_100(dims["link"])
    )
    return {"dims": dims, "prior": round(prior, 2)}
