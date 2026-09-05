"""轻量有效语音检测（docs/19-M2 §2 有效性前置过滤 · docs/24-B1 线性域作用域规则）。

背景：``faster-whisper`` 对空录音/纯静音会「幻听」出短词（如 ``You``），讯飞 ISE 又给静音打出高分，
导致「没说话却拿高分」且白白消耗 ASR/ISE 额度。docs/06 §8 承诺的 Silero VAD 尚未落地（asr.py 无
vad_filter，审计 V2 R-09 确认），此模块为**无外部模型**的能量近似，仅做「空/近空音频」硬拒绝。

约定（docs/24-B1 作用域规则）：VAD 全部在**线性 RMS 帧能量域**（``sqrt(mean(x²))``，noise=p10、
``thresh=min(max(noise*4,1e-4), p90*0.5)``、``p90<1e-4 → 全静音``）；dB 只在报告端用，绝不用 dB
喂 VAD。
"""

from __future__ import annotations

import numpy as np
import soundfile as sf

_SAMPLE_RATE = 16000
_FRAME_MS = 30  # 帧长（线性域）
_SILENCE_FLOOR = 1e-4  # 绝对静音帧 RMS 下限（docs/24-B1：p90<1e-4 → 全静音）
_NOISE_MULT = 4.0  # noise 底倍数（thresh = min(max(noise*4, 1e-4), p90*0.5)）
_P90_FACTOR = 0.5  # p90 上限框（thresh 上限）
# 语音帧占比下限：低于此视为「无有效语音」→ 拒绝。
# 用「语音帧下限」而非 docs/19 的「静音比>60%」全局上限，避免把有停顿但确实说了话的作答误拒
# （如 2s 起手静音 + 0.5s 说话：静音比≈80%，但确有语音）。默认 5% ≈ 每 20 帧至少 1 帧有声音。
DEFAULT_MIN_VOICED_RATIO = 0.05


def _frame_rms(pcm: np.ndarray, sr: int, frame_size: int) -> np.ndarray:
    """逐帧线性 RMS（float64；不足一帧用整段 RMS，避免除零/NaN，docs/24-B1 case4 防御）。"""
    frame_size = max(1, int(round(sr * _FRAME_MS / 1000.0)))
    if pcm.size < frame_size:
        rms = float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2)))
        return np.array([rms])
    trimmed = pcm[: pcm.size // frame_size * frame_size].astype(np.float64)
    frames = trimmed.reshape(-1, frame_size)
    return np.sqrt(np.mean(frames**2, axis=1))


def silence_ratio(pcm: np.ndarray, sr: int = _SAMPLE_RATE, frame_ms: int = _FRAME_MS) -> float:
    """返回静音帧占比 [0,1]（docs/24-B1 线性域 VAD）。

    帧移=帧长（无重叠，足够判定）；空/全零输入返回 1.0（全静音）。
    """
    pcm = np.asarray(pcm).astype(np.float64)
    if pcm.size == 0:
        return 1.0
    frame_size = max(1, int(round(sr * frame_ms / 1000.0)))
    rms = _frame_rms(pcm, sr, frame_size)
    if rms.size == 0:
        return 1.0
    p10 = float(np.percentile(rms, 10))
    p90 = float(np.percentile(rms, 90))
    if p90 < _SILENCE_FLOOR:
        return 1.0  # 全静音（docs/24-B1）
    thresh = min(max(p10 * _NOISE_MULT, _SILENCE_FLOOR), p90 * _P90_FACTOR)
    return float(float(np.mean(rms <= thresh)))


def has_speech(
    pcm: np.ndarray,
    sr: int = _SAMPLE_RATE,
    min_voiced_ratio: float = DEFAULT_MIN_VOICED_RATIO,
) -> bool:
    """是否有有效语音：语音帧（RMS>阈值）占比 ≥ ``min_voiced_ratio``（默认 0.05）。

    全静音 → 语音帧占比 0 → False（拒绝）；带停顿但确有语音段 → 占比达标 → True（放行）。
    """
    return (1.0 - silence_ratio(pcm, sr)) >= min_voiced_ratio


def load_audio_16k_mono(path: str) -> np.ndarray:
    """读取 16k WAV 为 float32 单声道数组（多声道取均值，含 check_same_thread 无关）。"""
    data, sr = sf.read(path, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return np.asarray(data)


# 转写最少词数：低于此视为「无有效语音」→ 不送评测（docs/19-M2 §2：转写词数 < 5 不送评测）。
# 兜底防 whisper 对非语音（纯音/噪声）幻听出短词（如 ``You``）仍被 ISE 打高分。
DEFAULT_MIN_TRANSCRIPT_WORDS = 5


def has_min_words(text: str, min_words: int = DEFAULT_MIN_TRANSCRIPT_WORDS) -> bool:
    """转写是否达到最少词数（防 whisper 对静音/噪声幻听出短词）。"""
    return len(text.split()) >= min_words
