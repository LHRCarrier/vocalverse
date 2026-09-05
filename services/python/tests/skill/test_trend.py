"""水平「进步趋势」演示映射单测（诚实 demo：无 sklearn、无 LLM）。"""

from __future__ import annotations

from app.skill.trend import TrendResult, progress_trend, score_to_level


class TestScoreToLevel:
    def test_boundaries(self) -> None:
        assert score_to_level(0) == "L1"
        assert score_to_level(54) == "L1"
        assert score_to_level(55) == "L2"
        assert score_to_level(69) == "L2"
        assert score_to_level(70) == "L3"
        assert score_to_level(84) == "L3"
        assert score_to_level(85) == "L4"
        assert score_to_level(100) == "L4"


class TestProgressTrend:
    def test_no_data_returns_placement_default(self) -> None:
        """无样本/缺近期分 → placement 档位中值 + confidence=0（demo 诚实标注）。"""
        r = progress_trend(recent_score=None, sample_count=0, placement_level="L3")
        assert isinstance(r, TrendResult)
        assert r.source == "score_map"
        assert r.level == "L3"
        assert r.confidence == 0.0
        # 无 placement → 兜底 L1
        assert progress_trend(None, 0).level == "L1"

    def test_score_read_through_clamped(self) -> None:
        """有样本 → 分值直读（非伪造预测），越界钳制到 [0,100]，source=score_map。"""
        r = progress_trend(72.0, 8)
        assert r.source == "score_map"
        assert r.score == 72.0
        assert r.level == "L3"
        # 越界钳制
        assert progress_trend(150.0, 3).score == 100.0
        assert progress_trend(-5.0, 3).score == 0.0

    def test_confidence_scales_with_samples(self) -> None:
        """置信度随样本量（10 样本满置信），不虚报满置信。"""
        assert progress_trend(60.0, 0).confidence == 0.0
        assert progress_trend(60.0, 5).confidence == 0.5
        assert progress_trend(60.0, 10).confidence == 1.0
        assert 0.0 <= progress_trend(60.0, 3).confidence <= 1.0

    def test_sample_count_none_treated_as_zero(self) -> None:
        """sample_count=None 视同无样本 → 走兜底，不崩。"""
        r = progress_trend(60.0, None)
        assert r.confidence == 0.0
        assert r.level in {"L1", "L2", "L3", "L4"}
