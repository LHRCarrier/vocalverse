"""参考旋律/用户音高提取（docs/06 §9.4：librosa *pyin*；唱歌域 65~800Hz、
frame 2048/hop 512、清浊门限）。

角色（2026-09-09 唱歌 P0 拍板）：
- 参考旋律输入轨（D1）：songs.vocal_ref_url 优先 → audio_url 回退（两级回退由 jobs 层负责）；
- 提取结果写入 song_pitch_refs（Python 写方），version="pyin-v1"（算法世代可追溯）；
- 用户逐帧 F0（D4）：sing 评分器复用 :func:`extract_f0_sync`（同参数），落 lines[i].user_f0。

实现约定：
- 重 CPU（librosa pyin）纯同步，调用方必须走 ``asyncio.to_thread``（docs/06 §8①）；
- 输出 F0 数组统一 ``0.0`` 表示清音帧（不存 NaN——JSON 序列化友好、DTW 前再过滤）；
- notes/midi 与 f0 逐帧对齐（清音帧为空串/None）。
"""

from __future__ import annotations

import abc
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

from app.audio.ffmpeg_utils import run_ffmpeg

logger = logging.getLogger("vocalverse")

# docs/06 §9.4：唱歌域 F0 65~800Hz；frame 2048/hop 512@16k（hop=32ms）
TARGET_SR = 16000
PYIN_FMIN = 65.0
PYIN_FMAX = 800.0
FRAME_LENGTH = 2048
HOP_LENGTH = 512
# 清浊门限（**可选叠加**）：librosa 的 voiced_flag 已含 viterbi 平滑判决（滤静音/呼吸），
# 是清浊的权威来源；再叠加 voiced_prob 下限过滤会误杀真人歌声（颤音/气声/手机麦下
# voicing prob 普遍 < 0.6——2026-09-09 实测用户录音 vprob max 0.43~0.76 / mean 0.01~0.04，
# 叠加 0.6 门限导致全句 no_pitch）。默认 0 = 关闭叠加过滤（只信 voiced_flag）；
# 需要更激进的静音剔除时经 APP_PITCH_VOICING_THRESHOLD 调高（如 0.2~0.3）。
VOICING_THRESHOLD = 0.0
# 提取算法世代（写入 song_pitch_refs.version / sing_attempts.ref_version）
EXTRACTOR_VERSION = "pyin-v1"


class PitchExtractError(RuntimeError):
    """提取失败（解码/加载/算法内部错误）——jobs 层捕获并落 failed 快照，不伪造数据。"""


@dataclass
class TrackF0:
    """整轨 F0 提取结果（纯数值，可直接 JSON 序列化）。"""

    sr: int
    hop_ms: float
    # 帧起点时间（毫秒，整数化）+ 对齐帧级数组
    times_ms: list[float] = field(default_factory=list)
    f0: list[float] = field(default_factory=list)  # 0.0 = 清音帧
    midi: list[int | None] = field(default_factory=list)
    names: list[str | None] = field(default_factory=list)  # 音名（C4/D#4 …），清音帧 None
    duration_ms: float = 0.0
    # 逐帧能量（RMS，与 f0 同帧对齐）：起唱检测的能量兜底用（sing.py A3 拍板；
    # 气声/低信噪比时 F0 全清音但确有发声，需能量定位起唱点）
    rms: list[float] = field(default_factory=list)


def apply_voicing_gate(voiced_flag, voiced_prob, threshold: float):
    """清浊判决合成（纯函数，可单测）。

    - ``voiced_flag``：librosa pyin 的 viterbi 平滑判决（**权威**；已滤静音/无音高段）；
    - ``voiced_prob``：逐帧浊音概率；``threshold > 0`` 时**额外**要求 prob 超过门限
      （默认 0 = 不叠加——真人歌声 vprob 偏低，叠加会误杀整句）；
    - ``voiced_prob is None``（全静音序列）→ 全 False。
    """
    import numpy as np

    if voiced_prob is None:
        return np.zeros(len(voiced_flag), dtype=bool)
    flag = np.asarray(voiced_flag, dtype=bool).copy()
    if threshold > 0:
        flag &= np.asarray(voiced_prob, dtype=float) > float(threshold)
    return flag


class PitchExtractor(abc.ABC):
    """参考旋律提取抽象（CI 零真 Key/零模型：APP_TESTING 时注入 Fake；docs/06 第 6 章）。"""

    @abc.abstractmethod
    def extract_track(self, wav_path: str) -> TrackF0:
        """从 16k mono wav 提取整轨 F0（同步重活，调用方自行 to_thread）。"""
        raise NotImplementedError


class PyinPitchExtractor(PitchExtractor):
    """librosa.pyin 实现（docs/06 §9.4 参数：fmin 65 / fmax 800 / frame 2048 / hop 512）。

    :param voicing_threshold: 可选叠加的 voiced_prob 下限（0=只用 librosa voiced_flag，
        默认；真人歌声 voicing prob 偏低，叠加高门限会整句误判清音——见模块常量注释）。
    """

    def __init__(self, voicing_threshold: float = VOICING_THRESHOLD):
        self._voicing_threshold = float(voicing_threshold)

    def extract_track(self, wav_path: str) -> TrackF0:
        try:
            import librosa
            import numpy as np
        except ImportError as exc:  # pragma: no cover - 依赖已在 pyproject 固定
            raise PitchExtractError(f"librosa 不可用: {exc}") from exc
        try:
            y, sr = librosa.load(wav_path, sr=TARGET_SR, mono=True)
        except Exception as exc:
            raise PitchExtractError(f"音频加载失败: {exc}") from exc
        if y.size == 0:
            raise PitchExtractError("音频为空")
        try:
            f0, voiced_flag, voiced_prob = librosa.pyin(
                y,
                fmin=PYIN_FMIN,
                fmax=PYIN_FMAX,
                sr=sr,
                frame_length=FRAME_LENGTH,
                hop_length=HOP_LENGTH,
                fill_na=0.0,
            )
        except Exception as exc:
            raise PitchExtractError(f"pyin 提取失败: {exc}") from exc
        flag = apply_voicing_gate(voiced_flag, voiced_prob, self._voicing_threshold)
        f0 = np.asarray(f0, dtype=float)
        f0[~flag] = 0.0  # 清音帧统一置 0（静音/无音高段）

        # 逐帧 RMS（起唱检测能量兜底；与 f0 帧数对齐——librosa.feature.rms 帧数可能差 1）
        try:
            rms_raw = librosa.feature.rms(y=y, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)
            rms = np.asarray(rms_raw[0], dtype=float)
            if len(rms) < len(f0):
                rms = np.pad(rms, (0, len(f0) - len(rms)))
            rms = rms[: len(f0)]
        except Exception:  # 能量计算失败不阻塞（起唱检测退化为 F0 单路径）
            rms = np.zeros(len(f0), dtype=float)

        times = np.arange(len(f0)) * (HOP_LENGTH / sr * 1000.0)
        midi: list[int | None] = []
        names: list[str | None] = []
        for hz in f0:
            if hz <= 0:
                midi.append(None)
                names.append(None)
                continue
            m = int(round(69 + 12 * math.log2(hz / 440.0)))
            midi.append(m)
            names.append(_midi_to_name(m))
        return TrackF0(
            sr=sr,
            hop_ms=HOP_LENGTH / sr * 1000.0,
            times_ms=[float(t) for t in times],
            f0=[float(v) for v in f0],
            midi=midi,
            names=names,
            duration_ms=float(len(y)) / sr * 1000.0,
            rms=[float(v) for v in rms],
        )


class FakePitchExtractor(PitchExtractor):
    """CI 零音频/零模型打桩：合成 440Hz 正弦（周期 127.27 frames/秒），帧级 F0 恒定。

    仅供测试（APP_TESTING 注入）；产出与 Pyin 同结构，保证 jobs/评分链路可测。
    """

    def extract_track(self, wav_path: str) -> TrackF0:
        sr = TARGET_SR
        # 以文件时长推导帧数（无音频时退化为 100 帧）；wav_path 仅为保持签名一致
        n_frames = 100
        try:
            # 真实 wav 存在时按音频时长派生帧数（测试一般传合成 wav）
            import soundfile as sf

            info = sf.info(wav_path)
            n_frames = max(1, int(info.duration / (HOP_LENGTH / sr)) + 1)
        except Exception:
            pass
        times = [i * (HOP_LENGTH / sr * 1000.0) for i in range(n_frames)]
        f0 = [440.0] * n_frames
        midi = [int(round(69 + 12 * math.log2(440.0 / 440.0)))] * n_frames  # A4=69
        names = ["A4"] * n_frames
        return TrackF0(
            sr=sr,
            hop_ms=HOP_LENGTH / sr * 1000.0,
            times_ms=times,
            f0=f0,
            midi=midi,
            names=names,
            duration_ms=n_frames * (HOP_LENGTH / sr * 1000.0),
            rms=[0.1] * n_frames,  # 恒定能量（起唱检测在测试里走 F0 主路径）
        )


def get_pitch_extractor() -> PitchExtractor:
    """依赖注入（docs/06 第 6 章）：APP_TESTING → Fake；production 缺 pyin 配置则 fail-fast。"""
    from app.core.config import get_settings

    settings = get_settings()
    if settings.testing:
        return FakePitchExtractor()
    if (settings.pitch_extractor or "pyin").lower() != "pyin":
        raise PitchExtractError(f"未知 pitch_extractor={settings.pitch_extractor}")
    return PyinPitchExtractor(voicing_threshold=settings.pitch_voicing_threshold)


def resolve_audio_path(url: str | None, audio_dir: str = "./data/audio") -> str | None:
    """songs.audio_url/vocal_ref_url 路径归一（A-G7 路径语义三义性）。

    约定（docs/06 §8 本地卷 + D-G2 共享卷）：Java 侧存共享卷路径字符串
    （如 ``/data/audio/twinkle.wav``）；Python 容器内共享卷挂 ``<audio_dir>``
    （dev 相对路径 ``./data/audio`` / 容器 ``/app/data/audio``）。
    解析顺序：① 原样存在 → 用之；② ``<audio_dir>/<basename>`` → 用之；③ http(s) 或不存在 → None。
    """
    if not url:
        return None
    if Path(url).exists():
        return url
    if url.startswith("http://") or url.startswith("https://"):
        logger.warning("vocal_ref/audio_url 为远程 URL 且非下载语义（D1 不引下载）：%s", url)
        return None
    candidate = Path(audio_dir) / Path(url).name
    if candidate.exists():
        return str(candidate)
    logger.warning("音频文件不存在（vocal_ref/audio_url）：%s", url)
    return None


async def to_16k_mono_wav(src: str, dst: str, timeout_s: float = 15.0) -> None:
    """任意容器格式 → 16k mono wav（ffmpeg；同 asr 护栏：async + 超时 kill，docs/19 P0-2）。"""
    await run_ffmpeg(
        ["-y", "-i", src, "-ar", str(TARGET_SR), "-ac", "1", "-f", "wav", dst],
        timeout_s=timeout_s,
    )


def slice_window(track: TrackF0, start_ms: float, end_ms: float | None) -> dict:
    """按句窗口切片（linspace 区间采样：窗口内帧保留，端点外剔除）。

    返回 JSON 兼容 dict（song_pitch_refs.pitch_ref 契约）：
    ``{"f0s": [...], "notes": [...], "midi": [...], "start_ms": ..., "end_ms": ...}``
    窗口内全清音 → f0s 全 0（评分层按缺失降权处理，D5）。
    """
    hop = track.hop_ms or 32.0
    i0 = max(0, int(start_ms / hop))
    i1 = (
        len(track.f0)
        if end_ms is None
        else min(len(track.f0), max(i0 + 1, int(math.ceil(end_ms / hop))))
    )
    seg = track.f0[i0:i1]
    if not seg:
        seg = [0.0]
    return {
        "f0s": seg,
        "notes": track.names[i0:i1] or [None],
        "midi": track.midi[i0:i1] or [None],
        "start_ms": int(start_ms),
        "end_ms": int(end_ms) if end_ms is not None else None,
        # 帧索引（v2 新增）：调用方按同一区间取能量包络（起唱检测兜底，sing.py A3）
        "frame_start": i0,
        "frame_end": i1,
    }


def _midi_to_name(midi: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[midi % 12]}{midi // 12 - 1}"
