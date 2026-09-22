"""素材难度专家规则单测（local/28 §2.2 影子三维度 + local/32 A-1.2 修订回归）。

2026-09-21（酒馆迁移）：场景三维度（vocab/syntax/pron + scenario_prior）与
``app/difficulty/batch`` 写库链路随英语场景对话移除；本文件仅覆盖仍存在的
``dim_to_100`` 与 ``shadow_prior``。
"""

from __future__ import annotations

import pytest
from app.difficulty.rules import dim_to_100, shadow_prior


def test_dim_to_100() -> None:
    """B2：M(k)=30+15(k-1)，1→30/3→60/5→90。"""
    assert dim_to_100(1) == pytest.approx(30.0)
    assert dim_to_100(3) == pytest.approx(60.0)
    assert dim_to_100(5) == pytest.approx(90.0)


def test_shadow_prior_pause_direction() -> None:
    """B3：停顿方向反转——停顿越多（>16/min）=1 分（易），停顿越少=5 分（难）。"""
    slow = shadow_prior(wps=1.6, pause_per_min=16.0, links_per_100w=4.0)  # 慢+多停顿=易
    fast = shadow_prior(wps=2.5, pause_per_min=2.0, links_per_100w=12.0)  # 快+少停顿=难
    assert slow["prior"] < fast["prior"]
    assert slow["dims"] == {"wps": 2.0, "pause": 1.0, "link": 2.0}
    assert fast["dims"] == {"wps": 4.0, "pause": 5.0, "link": 4.0}


def test_shadow_prior_bounds_and_weights() -> None:
    """三维度加权（0.4/0.3/0.3）后 prior 落在 [30, 90] 端点。"""
    easiest = shadow_prior(wps=1.0, pause_per_min=20.0, links_per_100w=0.0)
    hardest = shadow_prior(wps=4.0, pause_per_min=0.0, links_per_100w=20.0)
    assert easiest["dims"] == {"wps": 1.0, "pause": 1.0, "link": 1.0}
    assert easiest["prior"] == pytest.approx(30.0)
    assert hardest["dims"] == {"wps": 5.0, "pause": 5.0, "link": 5.0}
    assert hardest["prior"] == pytest.approx(90.0)
