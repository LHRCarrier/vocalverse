"""考试域两维评分公式单测（阶段 F1）。

校验 C1 关键逻辑：
- S = 0.6·A + 0.4·F（对齐推荐系统统一尺度，local/26 §2）；
- F = 0.7·mean(flu) + 0.3·mean(completeness)，completeness 缺失时仅 flu（local/20 禁 0.0 混入）；
- 档界 85/70/55 映射 L1~L4；
- 权重/阈值从配置读（A5 单源）。
"""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from app.placement import scoring


def _cfg(**overrides):
    return get_settings().model_copy(update=overrides)


def test_s_formula_two_dim():
    """S = 0.6·A + 0.4·F；F = 0.7·flu + 0.3·completeness。"""
    cfg = _cfg()
    a = 90.0
    f = scoring.compute_fluency([86.0], [80.0], cfg)
    assert f == pytest.approx(0.7 * 86.0 + 0.3 * 80.0)
    s = scoring.compute_s(a, f, cfg)
    assert s == pytest.approx(0.6 * 90.0 + 0.4 * f)


def test_completeness_missing_falls_back_to_flu_only():
    """completeness 缺失（如 Fake 桩）→ F 仅用 flu，不把 0.0 混入。"""
    cfg = _cfg()
    f = scoring.compute_fluency([86.0], [None], cfg)
    assert f == pytest.approx(86.0)


def test_completeness_none_ignored_not_zero():
    """completeness 列表含 None 时被剔除，只对非 None 求均值。"""
    cfg = _cfg()
    f = scoring.compute_fluency([80.0, 90.0], [None, 70.0], cfg)
    assert f == pytest.approx(0.7 * 85.0 + 0.3 * 70.0)


def test_accuracy_missing_returns_none():
    assert scoring.compute_accuracy([None, None]) is None
    assert scoring.compute_accuracy([]) is None


def test_fluency_missing_returns_none():
    cfg = _cfg()
    assert scoring.compute_fluency([None], [None], cfg) is None


def test_level_boundaries():
    """档界 85/70/55（进配置）——边界两侧。"""
    cfg = _cfg()
    assert scoring.level_for(85.0, cfg) == "L4"
    assert scoring.level_for(84.99, cfg) == "L3"
    assert scoring.level_for(70.0, cfg) == "L3"
    assert scoring.level_for(69.99, cfg) == "L2"
    assert scoring.level_for(55.0, cfg) == "L2"
    assert scoring.level_for(54.99, cfg) == "L1"


def test_thresholds_from_config_not_hardcoded():
    """阈值读配置：改配置档界即变（A5 单源）。"""
    cfg = _cfg(level_threshold_l4=80.0)
    assert scoring.level_for(82.0, cfg) == "L4"
    cfg2 = _cfg(level_threshold_l2=50.0)
    assert scoring.level_for(52.0, cfg2) == "L2"


def test_weights_from_config_not_hardcoded():
    """权重读配置：改 score_w_accuracy/score_w_fluency 影响 S。"""
    cfg = _cfg(score_w_accuracy=0.5, score_w_fluency=0.5)
    s = scoring.compute_s(90.0, 80.0, cfg)
    assert s == pytest.approx(85.0)
