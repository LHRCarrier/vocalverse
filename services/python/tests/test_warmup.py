"""TTS 预热调度回归（docs/06 §8「开场/常用句预合成」兑现：已知文本预热 + 测试环境跳过）。

- collect_warm_texts：保序去重 + 空白裁剪（缓存键幂等的输入侧）；
- scenario_warm_texts：开场白 + target_corpus 短语（提示/示范高频句）；
- schedule_texts_warm：testing 静默跳过（CI 零外部依赖）；重复预热由缓存命中兜底。
"""

from __future__ import annotations

from app.audio.warmup import collect_warm_texts, scenario_warm_texts, schedule_texts_warm
from app.models import Scenario


def test_collect_dedupes_trims_and_keeps_order() -> None:
    out = collect_warm_texts(
        ["  Hi there!  ", None, ""],
        ["I want a coffee.", "I want a coffee.", "  ", "How much is it?"],
        ["  Please try again.  "],
    )
    assert out == ["Hi there!", "I want a coffee.", "How much is it?", "Please try again."]


def test_scenario_warm_texts_opening_plus_corpus() -> None:
    scenario = Scenario(
        title="cafe",
        scene_type="cafe",
        difficulty=1,
        system_prompt="p",
        opening_line="Hi! Welcome to Moonbean.",
        target_corpus="I'd like a coffee, please.|请给我来杯咖啡\nHow much is it?|多少钱",
        interest_tags=[],
        status="published",
    )
    out = scenario_warm_texts(scenario)
    assert out == [
        "Hi! Welcome to Moonbean.",
        "I'd like a coffee, please.",
        "How much is it?",
    ]
    # 空场景：无文本（预热零成本跳过）
    assert scenario_warm_texts(Scenario(title="x", scene_type="cafe", difficulty=1)) == []


def test_schedule_texts_warm_skips_in_testing() -> None:
    """testing 档（conftest 恒 true）：静默跳过——不创建任务、不触外部、不抛。"""
    schedule_texts_warm(["Hi.", "Bye."])  # 无断言即通过（不抛 + 不阻塞）


def test_schedule_texts_warm_skips_empty() -> None:
    schedule_texts_warm([])
