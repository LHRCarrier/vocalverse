"""TTS 预热调度回归（docs/06 §8「开场/常用句预合成」兑现：已知文本预热 + 测试环境跳过）。

2026-09-21（酒馆迁移）：场景开场白/语料预热（scenario_warm_texts /
schedule_startup_warmup）随英语场景对话移除；现役形态为影子会话逐句示范预热
（collect_warm_texts + schedule_texts_warm）。

- collect_warm_texts：保序去重 + 空白裁剪（缓存键幂等的输入侧）；
- schedule_texts_warm：testing 静默跳过（CI 零外部依赖）；重复预热由缓存命中兜底。
"""

from __future__ import annotations

from app.audio.warmup import collect_warm_texts, schedule_texts_warm


def test_collect_dedupes_trims_and_keeps_order() -> None:
    out = collect_warm_texts(
        ["  Hi there!  ", None, ""],
        ["I want a coffee.", "I want a coffee.", "  ", "How much is it?"],
        ["  Please try again.  "],
    )
    assert out == ["Hi there!", "I want a coffee.", "How much is it?", "Please try again."]


def test_collect_shadow_sentences_only() -> None:
    """现役调用形态（service._create_session_sync）：仅逐句素材文本，保序去重。"""
    out = collect_warm_texts([], [], ["Hi there.", "Hi there.", "  Bye.  "])
    assert out == ["Hi there.", "Bye."]
    # 空输入：预热零成本跳过
    assert collect_warm_texts([], [], []) == []


def test_schedule_texts_warm_skips_in_testing() -> None:
    """testing 档（conftest 恒 true）：静默跳过——不创建任务、不触外部、不抛。"""
    schedule_texts_warm(["Hi.", "Bye."])  # 无断言即通过（不抛 + 不阻塞）


def test_schedule_texts_warm_skips_empty() -> None:
    schedule_texts_warm([])
