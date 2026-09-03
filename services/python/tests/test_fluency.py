"""流利度时间戳特征（app/audio/fluency.py）纯函数单测。

口径 docs/06 §9.3（辅助指标）：有效说话段 = 首词 start → 末词 end（排除首尾静默）；
停顿 = 相邻两词间隙 ≥0.5s（仅词间，不含首尾静默）；长停顿 ≥1.0s。
"""

from __future__ import annotations

from app.audio.fluency import (
    LONG_PAUSE_THRESHOLD_S,
    PAUSE_THRESHOLD_S,
    compute_fluency_features,
)

# 7 词，"a"→"coffee," 间 1.05s 停顿（≥1.0 → 长停顿）；说话段 0.10→2.98 = 2.88s
_WORDS = [
    {"word": "hello", "start": 0.10, "end": 0.34, "probability": 0.98},
    {"word": "I", "start": 0.42, "end": 0.50, "probability": 0.97},
    {"word": "would", "start": 0.58, "end": 0.86, "probability": 0.99},
    {"word": "like", "start": 0.94, "end": 1.14, "probability": 0.98},
    {"word": "a", "start": 1.22, "end": 1.30, "probability": 0.95},
    {"word": "coffee,", "start": 2.35, "end": 2.72, "probability": 0.99},
    {"word": "please.", "start": 2.80, "end": 2.98, "probability": 0.98},
]

_FIELDS = {
    "word_count",
    "speech_s",
    "total_s",
    "wpm",
    "articulation_rate",
    "pause_count",
    "long_pause_count",
    "pause_total_s",
    "mean_pause_s",
    "max_pause_s",
    "pause_ratio",
}


def test_empty_inputs_are_zeros():
    f = compute_fluency_features([])
    assert all(v == 0 for v in f.values())
    assert compute_fluency_features(None, duration_s=3.0) == compute_fluency_features([])


def test_feature_key_set_is_stable():
    """恒定键集（前端/测试台按此渲染；改键=契约变更需同步前端）。"""
    assert set(compute_fluency_features(_WORDS)) == _FIELDS


def test_basic_features():
    f = compute_fluency_features(_WORDS, duration_s=3.2)
    assert f["word_count"] == 7
    assert f["speech_s"] == 2.88  # 0.10 → 2.98
    assert f["total_s"] == 3.2  # 音频总时长（duration_s 优先）
    assert f["wpm"] == round(7 / (2.88 / 60), 2)  # ≈145.83
    # 停顿 1.05s：1 次、长停顿 1 次、均值=最大=1.05
    assert f["pause_count"] == 1
    assert f["long_pause_count"] == 1
    assert f["pause_total_s"] == 1.05
    assert f["mean_pause_s"] == 1.05
    assert f["max_pause_s"] == 1.05
    assert f["pause_ratio"] == round(1.05 / 2.88, 4)  # 0.3646
    # 纯发音速率：去掉停顿后 1.83s → 229.51
    assert f["articulation_rate"] == round(7 / (1.83 / 60), 2)


def test_duration_falls_back_to_last_word_end():
    f = compute_fluency_features(_WORDS, duration_s=0.0)
    assert f["total_s"] == 2.98


def test_subthreshold_gap_not_counted_as_pause():
    words = [
        {"word": "one", "start": 0.5, "end": 0.7},
        {"word": "two", "start": 0.9, "end": 1.1},  # 间隙 0.2s < 0.5
    ]
    f = compute_fluency_features(words, duration_s=1.5)
    assert f["pause_count"] == 0
    assert f["pause_total_s"] == 0
    assert f["max_pause_s"] == 0
    assert f["wpm"] == round(2 / (0.6 / 60), 2) == 200.0


def test_gap_at_threshold_counted():
    words = [
        {"word": "one", "start": 0.0, "end": 0.5},
        {"word": "two", "start": 1.0, "end": 1.4},
    ]
    f = compute_fluency_features(words)
    assert f["pause_count"] == 1  # 0.5s == 阈值 → 计入
    assert f["long_pause_count"] == 0  # < 1.0s


def test_leading_trailing_silence_not_counted_as_pause():
    """首词前 1s / 末词后 1s 静默不算停顿（录音边沿噪声）；语速按说话段算。"""
    words = [
        {"word": "hello", "start": 1.0, "end": 1.3},
        {"word": "world", "start": 1.5, "end": 1.9},
    ]
    f = compute_fluency_features(words, duration_s=3.0)
    assert f["pause_count"] == 0
    assert f["speech_s"] == 0.9
    assert f["wpm"] == round(2 / (0.9 / 60), 2)


def test_single_word_no_speech_span():
    f = compute_fluency_features([{"word": "yes.", "start": 0.2, "end": 0.5}], duration_s=1.0)
    assert f["word_count"] == 1
    assert f["speech_s"] == 0  # 单词不构成说话段
    assert f["wpm"] == 0
    assert f["pause_count"] == 0
    assert f["total_s"] == 1.0


def test_junk_rows_skipped():
    words = [
        {"word": "a", "start": "0.1", "end": 0.3},  # 字符串数值容忍
        {"word": "b", "start": None, "end": 0.6},  # 缺 start → 跳过
        {"word": "c", "start": 0.9, "end": "x"},  # 坏 end → 跳过
        {"word": "d", "start": 1.1, "end": 0.9},  # end <= start → 跳过
        {"word": "e", "start": 1.3, "end": 1.7},
    ]
    f = compute_fluency_features(words)
    assert f["word_count"] == 2  # 只剩 a / e
    # 剩余 a(0.1–0.3) 与 e(1.3–1.7)：间隙 1.0s → 长停顿 1 次；说话段 1.6s
    assert f["pause_count"] == 1 and f["long_pause_count"] == 1
    assert f["wpm"] == round(2 / (1.6 / 60), 2)  # 75.0


def test_overlapping_words_tolerated():
    """whisper 偶发相邻词时间戳重叠（负间隙）→ 不抛异常、不计停顿。"""
    words = [
        {"word": "a", "start": 0.0, "end": 0.4},
        {"word": "b", "start": 0.3, "end": 0.8},  # 与前词重叠
        {"word": "c", "start": 0.9, "end": 1.5},
    ]
    f = compute_fluency_features(words)
    assert f["word_count"] == 3
    assert f["pause_count"] == 0
    assert f["speech_s"] == 1.5


def test_thresholds_configurable_constants():
    assert PAUSE_THRESHOLD_S == 0.5
    assert LONG_PAUSE_THRESHOLD_S == 1.0
