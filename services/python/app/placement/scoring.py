"""考试域两维评分（C1：对齐推荐系统统一尺度，避免两套标度，local/26 §2）。

依据：
- local/26 §2 / local/27 §4 / local/31：统一尺度 est_score = 0.6·发音 + 0.4·流利度，
  档界 85/70/55 —— 定档分与推荐系统动态档用**同一把 0-100 尺子**；
- local/24 v4 定稿 §2.1：考试域 S = 0.6·A + 0.4·F，F = 0.7·mean(flu) + 0.3·mean(integrity)；
- docs/06 §9.3：语法不进量化分；语法由 LLM 判定、仅作诊断（C1 拍板）；
- local/20 定稿：integrity（completeness）缺失时置 None 跳过，禁止 0.0 混入。

本模块为**纯函数**（不依赖 DB/异步），便于单测（阶段 F1）。权重/阈值全部来自
``Settings``（配置单源，A5），禁止硬编码常量。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.models.base import Levels

if TYPE_CHECKING:  # pragma: no cover
    from app.core.config import Settings


def compute_accuracy(pron_vals: Sequence[float | None]) -> float | None:
    """A（发音/准确度）= mean(读音题 pron_score)；无有效值返回 None。"""
    vals = [float(p) for p in pron_vals if p is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def compute_fluency(
    flu_vals: Sequence[float | None],
    comp_vals: Sequence[float | None],
    settings: Settings,
) -> float | None:
    """F（流利度）= score_f_fluency·mean(flu) + score_f_integrity·mean(completeness)。

    completeness 缺失时（如测试 Fake 未返回）**仅用 flu 均值**，不把 0.0 混入
    （local/20 定稿"integrity 缺失置 None 跳过，禁 0.0"）。
    """
    flu = [float(f) for f in flu_vals if f is not None]
    if not flu:
        return None
    flu_mean = sum(flu) / len(flu)
    comp = [float(c) for c in comp_vals if c is not None]
    if not comp:
        return flu_mean
    comp_mean = sum(comp) / len(comp)
    return settings.score_f_fluency * flu_mean + settings.score_f_integrity * comp_mean


def compute_s(a: float | None, f: float | None, settings: Settings) -> float:
    """综合分 S = score_w_accuracy·A + score_w_fluency·F（两维，C1 / local/24 v4 §2.1）。"""
    return round(settings.score_w_accuracy * (a or 0.0) + settings.score_w_fluency * (f or 0.0), 2)


def level_for(s: float, settings: Settings) -> str:
    """档位映射（S≥85→L4、70~84→L3、55~69→L2、<55→L1；阈值读配置，A5/C1）。"""
    if s >= settings.level_threshold_l4:
        return Levels.L4
    if s >= settings.level_threshold_l3:
        return Levels.L3
    if s >= settings.level_threshold_l2:
        return Levels.L2
    return Levels.L1


__all__ = ["compute_accuracy", "compute_fluency", "compute_s", "level_for", "Levels"]
