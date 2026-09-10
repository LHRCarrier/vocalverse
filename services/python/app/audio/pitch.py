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
# **pyin-v2（2026-09-10）**：pitch_ref 增 `onsets_ms`（参考侧音符级起音）——口径 v3 item7 要求
# 「两侧同源、同量纲的 onset」才能算真实节奏比（v1 只存 F0，评分侧被迫用 LRC 句间隔
# ≈ 秒级，与用户音符级 onset 不同量纲 → bpm_source 恒 duration，特性形同虚设）。
# 版本升级 → jobs 扫描 `_refs_ready` 自动判定"世代旧"并重建（Python 侧判断，
# 不触碰 Java 独占写的 songs 表）。
EXTRACTOR_VERSION = "pyin-v2"


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
    # 起音时刻（ms，librosa.onset_detect）：**能量/频谱起音**——用户侧评分直接用它；
    # 参考侧经 slice_window 落入 pitch_ref.onsets_ms 入库（sing.py 口径 v3 item7：
    # 两侧同量纲才能算真实 bpm_ratio；docs/06 §9.4）
    onsets_ms: list[float] = field(default_factory=list)
    # **F0 起音（2026-09-10 · 评估结论）**：音高跳变 + 有声段起点——与上面的频谱起音互补：
    # 频谱起音精于"同音重复"（能量突变），F0 起音精于"连唱/柔起音/噪声"（假起音少），
    # 两者在 sing.py:combine_bpm 内做 BPM 层仲裁（见 scripts/poc/onset_eval.py 实测）
    f0_onsets_ms: list[float] = field(default_factory=list)


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

        # 起音检测（口径 v3 item7：真实 BPM 估计用；失败返回 [] → 评分层回退时长截断比）
        onsets_ms = detect_onsets_ms(y, sr)
        # F0 起音（2026-09-10 评估结论：与频谱起音互补，评分层做 BPM 仲裁）
        f0_onsets = f0_onsets_ms(f0, HOP_LENGTH / sr * 1000.0)

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
            onsets_ms=onsets_ms,
            f0_onsets_ms=f0_onsets,
        )


def detect_onsets_ms(y, sr: int, hop_length: int = HOP_LENGTH) -> list[float]:
    """librosa.onset_detect 起音检测（docs/06 §9.4 节奏=onset 与 LRC 时间戳的偏差；口径 v3 item7）。

    输出起音时刻（ms）；任何失败 → []（非致命——评分层按　bpm_source="duration" 回退
    时长截断比，见 sing.py:bpm_ratio_info）。
    """
    try:
        import librosa

        frames = librosa.onset.onset_detect(y=y, sr=sr, hop_length=hop_length, backtrack=True)
        return [round(float(f * hop_length / sr * 1000.0), 1) for f in frames]
    except Exception as exc:  # pragma: no cover - 依赖已在 pyproject 固定；防御性回退
        logger.warning("onset detect failed (bpm falls back to duration ratio): %s", exc)
        return []


#: F0 起音参数（2026-09-10 评估标定，见 scripts/poc/onset_eval.py）
F0_ONSET_JUMP_CENT = 60.0  # 相邻有声帧（含跨短静音）音高跳变阈值：≥60 cent 视为换音
F0_ONSET_MIN_GAP_MS = 120.0  # 起音最小间隔（去抖）
F0_ONSET_BRIDGE_FRAMES = 3  # 跨静音桥接帧数（≈96ms）：断奏的音符间隔 80ms 内仍可比音高
F0_ONSET_MIN_RUN_FRAMES = 3  # 有声段最短帧数（短于此视为噪声）
F0_ONSET_SILENCE_GAP_MS = 150.0  # 判"新句起点"的前置静音


def f0_onsets_ms(
    f0,
    hop_ms: float,
    *,
    jump_cent: float = F0_ONSET_JUMP_CENT,
    min_gap_ms: float = F0_ONSET_MIN_GAP_MS,
    bridge_frames: int = F0_ONSET_BRIDGE_FRAMES,
    min_run_frames: int = F0_ONSET_MIN_RUN_FRAMES,
    silence_gap_ms: float = F0_ONSET_SILENCE_GAP_MS,
) -> list[float]:
    """**F0 起音**（纯函数）：① 有声段起点（前置静音 ≥150ms）② 音高跳变点。

    与频谱起音（:func:`detect_onsets_ms`）互补——评估实测（6 类合成素材 + 6 段真实录音）：

    | 形态 | 频谱起音 F1 | F0 起音 F1 | 说明 |
    |---|---|---|---|
    | 断奏 | 0.47 | 0.92 | 频谱假点极多（39 检出 / 12 真值） |
    | 连奏 | 0.65 | 0.82 | F0 跳变可靠 |
    | 柔起音 300ms | 0.12 | 0.92 | 频谱几乎全漏 |
    | 连奏+柔起音 | 0.46 | 0.88 | — |
    | 断奏+噪声 | 0.28 | 0.88 | — |
    | **同音重复** | 0.44（BPM 倍速） | **0.15（全漏）** | F0 盲区：音高不变无跳变 |

    → 结论：**谁都替代不了谁**，故在评分层做 BPM 仲裁（sing.py:combine_bpm），
    而不是在 onset 列表层融合（union 实测更差）。
    音高跳变允许跨越 ≤``bridge_frames`` 帧的短静音（断奏的音符间隔 ≈80ms，
    严格相邻有声帧比较会全部漏检）。
    """
    import numpy as np

    arr = np.asarray(f0, dtype=float)
    if arr.size == 0:
        return []
    voiced = arr > 0
    gap_frames = max(1, int(round(silence_gap_ms / hop_ms)))
    out: list[float] = []
    i = 0
    while i < len(voiced):
        if not voiced[i]:
            i += 1
            continue
        start = i
        while i < len(voiced) and voiced[i]:
            i += 1
        if i - start >= min_run_frames and (
            start == 0 or not voiced[max(0, start - gap_frames) : start].any()
        ):
            out.append(round(start * hop_ms, 1))
    last_voiced = -1
    for idx in range(len(arr)):
        if not voiced[idx]:
            continue
        if last_voiced >= 0 and idx - last_voiced <= bridge_frames + 1:
            cents = abs(1200.0 * float(np.log2(arr[idx] / arr[last_voiced])))
            if cents >= jump_cent:
                out.append(round(idx * hop_ms, 1))
        last_voiced = idx
    return _dedupe(out, min_gap_ms)


def _dedupe(vals: list[float], min_gap_ms: float) -> list[float]:
    """排序 + 相邻 <min_gap_ms 合并（保留最早）——F0 跳变在颤音/滑音处会密集触发。"""
    out: list[float] = []
    for v in sorted(vals):
        if not out or v - out[-1] >= min_gap_ms:
            out.append(v)
    return out


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

    返回 JSON 兼容 dict（song_pitch_refs.pitch_ref 契约，**pyin-v2**）：
    ``{"f0s", "notes", "midi", "start_ms", "end_ms", "onsets_ms"}``
    窗口内全清音 → f0s 全 0（评分层按缺失降权处理，D5）；
    ``onsets_ms`` = 落在本句窗口内的参考**音符级起音**绝对时刻（评分侧拼接各句 →
    与用户侧 onset_detect 同量纲，算真实 bpm_ratio；docs/06 §9.4 口径 v3 item7）。
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
    hi = float("inf") if end_ms is None else float(end_ms)
    win_onsets = [round(float(t), 1) for t in (track.onsets_ms or []) if start_ms <= float(t) < hi]
    return {
        "f0s": seg,
        "notes": track.names[i0:i1] or [None],
        "midi": track.midi[i0:i1] or [None],
        "start_ms": int(start_ms),
        "end_ms": int(end_ms) if end_ms is not None else None,
        # 参考音符级起音（pyin-v2 新增；口径 v3 item7 的参考侧数据源）
        "onsets_ms": win_onsets,
        # 帧索引（v2 新增）：调用方按同一区间取能量包络（起唱检测兜底，sing.py A3）
        "frame_start": i0,
        "frame_end": i1,
    }


def _midi_to_name(midi: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[midi % 12]}{midi // 12 - 1}"
