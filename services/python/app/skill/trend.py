"""水平「进步趋势」演示映射（**诚实：无 sklearn、无 LLM**；docs/06 §9.5 演示化）。

定位：仅用于前端「进步趋势」展示的 **demo 工具**，不驱动推荐、不做「未来水平预测」、
不训练模型、不调用外部 LLM。输入为近期综合分 + 样本数，输出：
- score：`clamp(recent_score, 0, 100)`（保守直读，不伪造预测）；
- level：统一尺度纯分档（85/70/55）；
- source：固定 `score_map`（诚实标注，非默认的 `sklearn`）；
- confidence：按样本量（无样本/低样本/充足），不虚报满置信。

与 ``service.update_user_level``（动态水平 = 规则引擎当前水平的权威来源）分离：
本模块只做「当前分 → 档位」的展示映射，不改任何权威水平，也不被推荐引擎消费。
"""

from __future__ import annotations

from dataclasses import dataclass

BAND_MID = {"L1": 50.0, "L2": 62.0, "L3": 77.0, "L4": 92.0}
_CONF_FULL_SAMPLES = 10  # 满置信所需样本数（demo 口径）


def score_to_level(score: float) -> str:
    """统一尺度纯分档（85/70/55；与 skill/service 同口径）。"""
    if score >= 85:
        return "L4"
    if score >= 70:
        return "L3"
    if score >= 55:
        return "L2"
    return "L1"


@dataclass(frozen=True)
class TrendResult:
    """进步趋势展示结果（demo 口径）。"""

    score: float
    level: str
    source: str = "score_map"
    confidence: float = 0.0


def progress_trend(
    recent_score: float | None,
    sample_count: int | None = 0,
    placement_level: str | None = None,
) -> TrendResult:
    """诚实 demo 映射：无样本 → placement 档位中值+置信度0；有样本 → 分值直读+档位+置信度。"""
    n = int(sample_count) if sample_count is not None else 0
    if recent_score is None or n <= 0:
        lvl = placement_level if placement_level in BAND_MID else "L1"
        return TrendResult(score=BAND_MID[lvl], level=lvl, source="score_map", confidence=0.0)
    score = max(0.0, min(100.0, float(recent_score)))
    confidence = min(1.0, n / _CONF_FULL_SAMPLES)
    return TrendResult(
        score=round(score, 2),
        level=score_to_level(score),
        source="score_map",
        confidence=round(confidence, 2),
    )
