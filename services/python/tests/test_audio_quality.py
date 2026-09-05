"""有效语音检测单测（docs/19-M2 §2 前置过滤 · docs/24-B1 线性域）。

纯函数：帧级线性 RMS / 自适应阈值 → 静音占比；只用合成 PCM，不依赖 ffmpeg/whisper。
"""

from __future__ import annotations

import numpy as np
from app.audio.audio_quality import has_min_words, has_speech, silence_ratio


def _zeros(dur_s: float = 1.0, sr: int = 16000) -> np.ndarray:
    return np.zeros(int(sr * dur_s), dtype=np.float64)


def _tone(freq: float = 440.0, dur_s: float = 1.0, amp: float = 0.5, sr: int = 16000) -> np.ndarray:
    t = np.arange(int(sr * dur_s)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float64)


def test_pure_silence_is_silent() -> None:
    pcm = _zeros()
    assert silence_ratio(pcm) == 1.0
    assert has_speech(pcm) is False


def test_empty_input_is_silent() -> None:
    assert silence_ratio(np.array([], dtype=np.float64)) == 1.0
    assert has_speech(np.array([], dtype=np.float64)) is False


def test_tone_has_speech() -> None:
    pcm = _tone(amp=0.5)
    ratio = silence_ratio(pcm)
    assert ratio <= 0.1, f"稳态音不应判静音，ratio={ratio}"
    assert has_speech(pcm) is True


def test_very_quiet_tone_is_silent() -> None:
    """幅度 ≈1e-5 的几乎无信号：帧 RMS 低于 1e-4 下限 → 全静音（docs/24-B1 p90<1e-4）。"""
    pcm = _tone(amp=1e-5)
    assert silence_ratio(pcm) == 1.0
    assert has_speech(pcm) is False


def test_mostly_silence_with_speech_burst() -> None:
    """2s 前静音 + 0.5s 音：静音占比应显著 < 1（有语音段），不被误判为全静音。"""
    pcm = np.concatenate([_zeros(2.0), _tone(amp=0.5, dur_s=0.5)])
    ratio = silence_ratio(pcm)
    assert 0.0 < ratio < 1.0, f"应有语音段，ratio={ratio} 不应为全静音"
    # 静音 2s / 总 2.5s = 0.8，但能量段让 max_rms 达标；此处断言存在可识别语音
    assert has_speech(pcm) is True


def test_min_words_short_hallucination_rejected() -> None:
    """whisper 对静音/噪声幻听的短词（如 ``You``，1 词）应视为无有效语音 → 拒绝。"""
    assert has_min_words("You") is False
    assert has_min_words("My name is Alex") is False  # 4 词 < 5


def test_min_words_real_answer_accepted() -> None:
    assert has_min_words("Good morning! I would like a cup of coffee, please.") is True  # 10 词
    assert has_min_words("Tell me something about yourself") is True  # 5 词 = 阈值


def test_min_words_custom_threshold() -> None:
    assert has_min_words("hello there", min_words=2) is True
    assert has_min_words("hello", min_words=2) is False
    assert has_min_words("", min_words=1) is False
