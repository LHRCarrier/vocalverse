"""素材难度专家规则：影子跟读三维度打分（**Python 写方**；local/28 §2.1 + local/32 修订）。

维度（均 1~5，0.5 步长；纯 Python stdlib，无 numpy——40 条量级阈值映射无向量化收益）：
- **语速** wps、**停顿密度** pause、**连读密度** link（local/28 §2.2）；
- 权重 `0.4/0.3/0.3`（语速主导），映射 `M(k)=30+15·(k−1)`（A-1.2 不对称：1→30/3→60/5→90）。

2026-09-21（酒馆迁移）：场景语料三维度（词汇/句法/发音 + CEFR 锚定 + λ 聚合）随英语
场景对话移除——`material_difficulty` 现仅服务影子跟读推荐候选。
"""

from __future__ import annotations

import math

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


def _threshold(value: float, table) -> float:
    for upper, score in table:
        if value <= upper:
            return float(score)
    return 5.0


def dim_to_100(k: float) -> float:
    """1~5 → 0-100（A-1.2 不对称：1→30/3→60/5→90，修向心偏置）。"""
    return 30.0 + (k - 1.0) * 15.0


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
