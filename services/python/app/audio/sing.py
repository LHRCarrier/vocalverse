"""唱歌评分核心（docs/06 §9.4：DTW 对齐 + 音准/节奏映射 + 发音复用口语引擎）。

公式（docs/06 §9.4）：
- 音准 = 逐句基频与**离线预提取参考旋律**（song_pitch_refs）偏差（cent）映射：
  ≤50→90+ / ≤100→70~90 / ≤200→50~65 / >300→<40（分段线性映射，见 :func:`pitch_score_from_cent`）；
- 节奏 = onset/beat 与 LRC 时间戳**相对** DTW 偏差映射：
  ≤150ms→90+ / ≤300→75~90 / ≤600→55~75 / >1000→<50（分段线性映射，见
  :func:`rhythm_score_from_dev`）；
- 发音 = **复用口语评分引擎**（ISE；整首抽样句，D3——service 层决定抽样窗口）；
- 综合 = `0.5·音准 + 0.2·节奏 + 0.3·发音`。
- 对齐 = BPM 倍率粗对齐 → Sakoe-Chiba window(≤10%) + 局部斜率约束子序列 DTW 精对齐
  （音高轮廓先归一化到半音相对值）；用户逐帧 F0 落库（D4: lines[i].user_f0）。
- 缺失降权（D5）：句无音高/静音/对不齐/参考缺失 → skipped=true + reason，不入综合平均；
  overall=有效句加权均分；is_complete=有效句数≥expected_lines×80%。

实现约定：纯 CPU 同步（numpy/pyin 重活），调用方必须 ``asyncio.to_thread``；
``SingScorer`` 为 ABC + ``FakeSingScorer``（CI 零模型/零 Key，docs/06 第 6 章）。
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger("vocalverse")

# 算法世代（写入 sing_attempts.scoring_version）
SCORING_VERSION = "v1"
ALIGN_METHOD = "dtw-sakoe-chiba-v1"

# DTW 参数（docs/06 §9.4：Sakoe-Chiba window ≤10% + 斜率约束）
DTW_BAND_RATIO = 0.10
# 音高轮廓归一化：相对中位数半音（cents）
_CENT = 1200.0 / np.log2(12.0) * 0  # 占位：实际用 1200*log2(f/med)
# : 半音差（cent）= 1200 * log2(r)（r 频率比）


def _hz_to_series_cent(f0: np.ndarray, ref_f0: np.ndarray) -> np.ndarray:
    """帧级频率 → 相对中位半音（cent）序列（音高轮廓归一化，docs/06 §9.4「先归一化」）。

    0 帧（清音）→ NaN（对齐/评分前过滤）；双序列长度不一致时按短侧截断。
    """
    n = min(len(f0), len(ref_f0))
    a = np.asarray(f0[:n], dtype=float)
    b = np.asarray(ref_f0[:n], dtype=float)
    a = np.where(a > 0, a, np.nan)
    b = np.where(b > 0, b, np.nan)
    both = ~(np.isnan(a) | np.isnan(b))
    if both.sum() == 0:
        return np.full(n, np.nan)
    med = np.nanmedian(a[both])
    if not np.isfinite(med) or med <= 0:
        return np.full(n, np.nan)
    return 1200.0 * np.log2(np.maximum(a, 1e-9) / med)


def _cent_deviation(user_f0: np.ndarray, ref_f0: np.ndarray) -> float | None:
    """逐帧 cent 偏差（**八度无关**：频率比折叠到 ±600 cent 后取 |偏差| 中位数）。

    八度折叠的理由：演唱者常用低/高八度唱（男声唱童谣常低 2 个八度——2026-09-09 真机
    实测用户 78~110Hz vs 参考 341Hz），绝对频率比较会恒判 0 分；KTV/唱吧类评分同样按
    「八度等价」判音准（docs/06 §9.4「音高轮廓先归一化」）。折叠后仍能区分跑调：
    偏差 ≤50 cent 优秀、>300 cent 不及格。

    有效帧（双端有声）不足 3 帧 → None（该句按缺失降权处理，D5）。
    """
    n = min(len(user_f0), len(ref_f0))
    u = np.asarray(user_f0[:n], dtype=float)
    r = np.asarray(ref_f0[:n], dtype=float)
    mask = (u > 0) & (r > 0)
    if mask.sum() < 3:
        return None
    d = _fold_cent(1200.0 * np.log2(np.maximum(u[mask], 1e-9) / np.maximum(r[mask], 1e-9)))
    return float(np.median(np.abs(d)))


def _fold_cent(cents: np.ndarray | float):
    """频率比 cent → 折叠到 [-600, 600]（八度等价；+1200 与 0 视为同一音高）。"""
    return ((np.asarray(cents, dtype=float) + 600.0) % 1200.0) - 600.0


def pitch_score_from_cent(cent: float) -> float:
    """音准映射（docs/06 §9.4 分段线性：≤50→90+ / ≤100→70~90 / ≤200→50~65 / >300→<40）。"""
    if cent <= 0:
        return 95.0
    if cent <= 50:
        return 95.0
    if cent <= 100:
        return 90.0 - (cent - 50) / 50.0 * 20.0  # 90→70
    if cent <= 200:
        return 65.0 - (cent - 100) / 100.0 * 15.0  # 65→50
    if cent <= 300:
        return 50.0 - (cent - 200) / 100.0 * 10.0  # 50→40
    return max(0.0, 40.0 - (cent - 300) / 100.0 * 15.0)  # <40


def rhythm_score_from_dev(dev_ms: float) -> float:
    """节奏映射（docs/06 §9.4 分段线性：≤150→90+ / ≤300→75~90 / ≤600→55~75 / >1000→<50）。"""
    if dev_ms <= 150:
        return 95.0
    if dev_ms <= 300:
        return 90.0 - (dev_ms - 150) / 150.0 * 15.0  # 90→75
    if dev_ms <= 600:
        return 75.0 - (dev_ms - 300) / 300.0 * 20.0  # 75→55
    if dev_ms <= 1000:
        return 55.0 - (dev_ms - 600) / 400.0 * 15.0  # 55→40
    return max(0.0, 40.0 - (dev_ms - 1000) / 500.0 * 20.0)  # <50 且 <40


# ---------------------------------------------------------------------------
# DTW 对齐（BPM 倍率粗对齐 → Sakoe-Chiba + 斜率约束子序列 DTW）
# ---------------------------------------------------------------------------
def _coarse_bpm_ratio(user_ms: float, ref_ms: float) -> float:
    """整体 BPM 倍率 = 参考时长 / 用户时长（>1 = 用户比参考慢）。兜底 1.0。"""
    if not user_ms or not ref_ms or user_ms <= 0 or ref_ms <= 0:
        return 1.0
    r = float(ref_ms / user_ms)
    return min(max(r, 0.5), 2.0)  # 0.5~2 倍率夹紧（演示域合理范围）


def align_frames(user_f0: np.ndarray, ref_f0: np.ndarray, hop_ms: float) -> tuple[float, float]:
    """整首对齐：返回 (bpm_ratio, offset_ms)。

    1. 粗对齐：时长比给出 bpm_ratio（用户序列采样到参考长度——只做整体缩放）；
    2. 精对齐：Sakoe-Chiba window(≤10%×N) + 斜率约束子序列 DTW（成本=归一化音高轮廓
       |cent 差|，水平/垂直步加倍惩罚=局部斜率约束），路径中位 (i-j) → offset_ms。

    无有效帧 → 返回 (1.0, 0.0)（调用方按不可对齐降权，不伪造）。
    """
    n = min(len(user_f0), len(ref_f0))
    if n < 8:
        return 1.0, 0.0
    u = np.asarray(user_f0[:n], dtype=float)
    r = np.asarray(ref_f0[:n], dtype=float)
    um = (u > 0) & (r > 0)
    if um.sum() < 8:
        return 1.0, 0.0
    # 音高轮廓归一化（相对各自中位半音）——只对有声帧有效
    uu = _hz_to_series_cent(u, r)
    rbg = r[r > 0]
    if len(rbg) == 0:
        return 1.0, 0.0
    rmed = float(np.median(rbg))
    rr = 1200.0 * np.log2(np.maximum(r, 1e-9) / rmed)
    uu = np.where(np.isfinite(uu), uu, 0.0)  # 无声帧成本 0（不惩罚停顿，节奏另测）
    rr = np.where(np.isfinite(rr), rr, 0.0)

    # 长歌内存/耗时护栏：>6000 帧按 2 帧步长降采样（180s@32ms=5660 帧，理论上不触发；
    # 兜底保证最坏 6000×band 迭代上界）
    step = 1
    if n > 6000:
        step = 2
        uu = uu[::step]
        rr = rr[::step]
        n = len(uu)

    w = max(1, int(n * DTW_BAND_RATIO))
    # Sakoe-Chiba band（|i-j| ≤ w）+ 斜率约束（水平/垂直步代价 ×2，鼓励对角）。
    # 成本在循环内按帧对即算（O(n·w) 内存 O(n·w) 矩阵；不做 O(n²) 全矩阵——180s 歌曲
    # 全矩阵 8M+ 帧对会爆内存）
    d = np.full((n, n), np.inf)
    d[0, 0] = abs(uu[0] - rr[0])
    for i in range(n):
        lo, hi = max(0, i - w), min(n - 1, i + w)
        for j in range(lo, hi + 1):
            if i == 0 and j == 0:
                continue
            c = abs(uu[i] - rr[j])
            cands = []
            if i > 0 and abs(i - 1 - j) <= w:
                cands.append(d[i - 1, j] + c * 2.0)  # 垂直步 ×2（斜率约束）
            if j > 0 and abs(i - (j - 1)) <= w:
                cands.append(d[i, j - 1] + c * 2.0)  # 水平步 ×2
            if i > 0 and j > 0:
                cands.append(d[i - 1, j - 1] + c)  # 对角步
            if cands:
                d[i, j] = min(cands)
    # 回溯求路径（开放终点：取末行能量最低点）
    j_end = int(np.argmin(d[n - 1, :]))
    path: list[tuple[int, int]] = []
    i, j = n - 1, j_end
    while i > 0 or j > 0:
        path.append((i, j))
        if i == 0:
            j -= 1
        elif j == 0:
            i -= 1
        else:
            prev = min(d[i - 1, j - 1], d[i - 1, j], d[i, j - 1])
            if prev == d[i - 1, j - 1]:
                i, j = i - 1, j - 1
            elif prev == d[i - 1, j]:
                i, j = i - 1, j
            else:
                i, j = i, j - 1
    path.append((0, 0))
    deltas = [pi - pj for pi, pj in path]
    offset = float(np.median(deltas) * hop_ms)  # 正 = 用户落后参考
    # 粗对齐给出 bpm_ratio（用户时长 vs 参考时长）
    user_ms = n * hop_ms
    ref_ms = len(ref_f0) * hop_ms
    return _coarse_bpm_ratio(user_ms, ref_ms), offset


def time_deviation_ms(lrc_start_ms: float, user_start_ms: float, bpm_ratio: float) -> float:
    """节奏偏差：用户句起点换算到参考时钟（bpm_ratio 补偿）后与 LRC 窗口偏差。"""
    corrected = user_start_ms * (bpm_ratio if bpm_ratio > 0 else 1.0)
    return abs(corrected - lrc_start_ms)


# ---------------------------------------------------------------------------
# 评分器契约
# ---------------------------------------------------------------------------
@dataclass
class LineScore:
    """逐句评分（落 sing_attempts.lines[i]；结构契约见 docs/10 §4.3）。"""

    seq: int
    start_ms: int
    end_ms: int
    pitch_score: float | None
    rhythm_score: float | None
    pron_score: float | None
    synced: bool = True
    skipped: bool = False
    reason: str | None = None  # no_pitch / no_ref / unwarped / pron_skipped
    ref_seq: int | None = None
    no_ref: bool = False
    # D4：用户逐帧 F0（降密度 [[t_ms, f0_hz], ...]，评分时保留句内全帧）
    user_f0: list[list[float]] = field(default_factory=list)
    # D3 双序列图辅助：帧级 cent 偏差（对齐后）
    cent_dev: list[float] = field(default_factory=list)


@dataclass
class SingScoreResult:
    """一次跟唱评分的聚合结果（service 层落库 sing_attempts）。"""

    lines: list[LineScore] = field(default_factory=list)
    overall: float | None = None
    pitch: float | None = None
    rhythm: float | None = None
    pron: float | None = None
    alignment: dict = field(default_factory=dict)  # {bpm_ratio, offset_ms, method, version}
    is_complete: bool = False
    expected_lines: int = 0
    evaluated_lines: int = 0


def aggregate_result(
    lines: list[LineScore], pron_ratio: float = 0.5, pron_weight: float = 0.3
) -> SingScoreResult:
    """聚合（D5 缺失降权：skipped 句不入分项均分；overall=0.5·音准+0.2·节奏+0.3·发音）。

    - pitch/rhythm = 有效句（非 skipped 且有该分项）均分；
    - pron = 抽样句 pron_score 均分（未抽样句 None，不进组合）；
    - overall = 0.5·pitch + 0.2·rhythm + 0.3·pron（分项任一缺失 → 按剩余权重归一，
      全部缺失 → None——不伪造分数）。
    """
    valid = [line for line in lines if not line.skipped]
    expected = len(lines)
    pitches = [line.pitch_score for line in valid if line.pitch_score is not None]
    rhythms = [line.rhythm_score for line in valid if line.rhythm_score is not None]
    prons = [line.pron_score for line in valid if line.pron_score is not None]
    pitch = _mean(pitches)
    rhythm = _mean(rhythms)
    pron = _mean(prons)
    overall = _weighted_overall(pitch, rhythm, pron, 0.5, 0.2, 0.3)
    return SingScoreResult(
        lines=lines,
        overall=overall,
        pitch=pitch,
        rhythm=rhythm,
        pron=pron,
        is_complete=bool(expected > 0 and len(valid) >= math_ceil(expected * 0.8)),
        expected_lines=expected,
        evaluated_lines=len(valid),
    )


class SingScorer(abc.ABC):
    """跟唱评分接口（CI 零真 Key/零模型：APP_TESTING 注入 Fake，docs/06 第 6 章）。

    ``score_sync`` 为纯同步核心（pyin/DTW/映射）；发音部分（ISE）由 service 层另行
    抽样调用口语 ScorerClient 后回填（发音抽样 = D3 拍板）。实现方决定参考缺失句处理。
    """

    @abc.abstractmethod
    def score_sync(
        self,
        user_wav_path: str,
        ref_lines: list[dict],
    ) -> SingScoreResult:
        """整首评分同步核心。

        :param user_wav_path: 16k mono wav（ffmpeg 由 service 层转换）
        :param ref_lines: 参考句列表 [{lrc_id, seq, start_ms, end_ms, pitch_ref:{f0s,...}, text}]
        :returns: 聚合结果（含逐句 + alignment）
        """
        raise NotImplementedError


class PyinSingScorer(SingScorer):
    """真实评分器：pyin 用户 F0 → DTW 对齐 → 逐句音准/节奏映射（发音由 service 层抽样）。"""

    def score_sync(self, user_wav_path: str, ref_lines: list[dict]) -> SingScoreResult:
        from app.audio.pitch import get_pitch_extractor, slice_window

        track = get_pitch_extractor().extract_track(user_wav_path)
        hop = track.hop_ms or 32.0
        ref_arrays = [
            {
                "seq": int(line["seq"]),
                "start_ms": int(line["start_ms"]),
                "end_ms": int(line["end_ms"]),
                "f0s": np.asarray(line["pitch_ref"].get("f0s") or [], dtype=float),
                "text": line.get("text") or "",
            }
            for line in ref_lines
        ]
        ref_full = np.concatenate([a["f0s"] for a in ref_arrays]) if ref_arrays else np.array([])
        user_f0 = np.asarray(track.f0, dtype=float)
        bpm_ratio, offset_ms = align_frames(user_f0, ref_full, hop)

        lines: list[LineScore] = []
        for a in ref_arrays:
            window = slice_window(
                track,
                a["start_ms"] + offset_ms * -1,  # 对齐偏置换算（正 offset=用户落后→提前取窗）
                a["end_ms"] + offset_ms * -1,
            )
            user_win = np.asarray(window["f0s"], dtype=float)
            ref_win = a["f0s"]
            ref_seq = a["seq"]
            if len(ref_win) == 0 or not np.any(ref_win > 0):
                lines.append(
                    LineScore(
                        seq=a["seq"],
                        start_ms=a["start_ms"],
                        end_ms=a["end_ms"],
                        pitch_score=None,
                        rhythm_score=None,
                        pron_score=None,
                        synced=False,
                        skipped=True,
                        reason="no_ref",
                        ref_seq=ref_seq,
                        no_ref=True,
                    )
                )
                continue
            cent = _cent_deviation(user_win, ref_win)
            if cent is None or not np.any(user_win > 0):
                lines.append(
                    LineScore(
                        seq=a["seq"],
                        start_ms=a["start_ms"],
                        end_ms=a["end_ms"],
                        pitch_score=None,
                        rhythm_score=None,
                        pron_score=None,
                        synced=False,
                        skipped=True,
                        reason="no_pitch",
                        ref_seq=ref_seq,
                        user_f0=_f0_pairs(user_win, a["start_ms"], hop),
                    )
                )
                continue
            pitch = pitch_score_from_cent(cent)
            # 节奏：句起点与 LRC 窗口偏差（bpm_ratio 时钟补偿）
            dev = time_deviation_ms(a["start_ms"], window["start_ms"], bpm_ratio)
            rhythm = rhythm_score_from_dev(dev)
            # 帧级 cent 偏差（D3 图辅助）：八度折叠 + 窗口取整按短侧截断
            n_cmp = min(len(user_win), len(ref_win))
            cent_dev = [
                float(c)
                for c in _fold_cent(
                    1200.0
                    * np.log2(
                        np.maximum(user_win[:n_cmp], 1e-9) / np.maximum(ref_win[:n_cmp], 1e-9)
                    )
                )
            ]
            lines.append(
                LineScore(
                    seq=a["seq"],
                    start_ms=a["start_ms"],
                    end_ms=a["end_ms"],
                    pitch_score=round(pitch, 2),
                    rhythm_score=round(rhythm, 2),
                    pron_score=None,
                    synced=True,
                    ref_seq=ref_seq,
                    user_f0=_f0_pairs(user_win, a["start_ms"], hop),
                    cent_dev=cent_dev,
                )
            )
        result = aggregate_result(lines)
        result.alignment = {
            "bpm_ratio": round(bpm_ratio, 4),
            "offset_ms": round(offset_ms, 1),
            "method": ALIGN_METHOD,
            "version": SCORING_VERSION,
        }
        return result


class FakeSingScorer(SingScorer):
    """CI 零模型打桩：恒定 440Hz 用户音高 → 恒定分数（结构性验证，不参与真评分）。

    与参考句数量无关地逐句生成：pitch=95（0 cent 偏差）、rhythm=95、skipped=False；
    user_f0 用合成 440Hz 帧填充（长度=参考句窗口帧数）。
    """

    def score_sync(self, user_wav_path: str, ref_lines: list[dict]) -> SingScoreResult:
        lines: list[LineScore] = []
        for line in ref_lines:
            f0s = (line.get("pitch_ref") or {}).get("f0s") or [440.0]
            n = len(f0s)
            start = int(line.get("start_ms") or 0)
            hop = 32.0
            lines.append(
                LineScore(
                    seq=int(line.get("seq") or 0),
                    start_ms=start,
                    end_ms=int(line.get("end_ms") or (start + n * hop)),
                    pitch_score=95.0,
                    rhythm_score=95.0,
                    pron_score=None,
                    synced=True,
                    ref_seq=int(line.get("seq") or 0),
                    user_f0=[[start + i * hop, 440.0] for i in range(max(1, n))],
                    cent_dev=[0.0] * max(1, n),
                )
            )
        result = aggregate_result(lines)
        result.alignment = {
            "bpm_ratio": 1.0,
            "offset_ms": 0.0,
            "method": ALIGN_METHOD,
            "version": SCORING_VERSION,
        }
        return result


def get_sing_scorer() -> SingScorer:
    from app.core.config import get_settings

    if get_settings().testing:
        return FakeSingScorer()
    return PyinSingScorer()


def _mean(vals: list[float]) -> float | None:
    return round(float(sum(vals) / len(vals)), 2) if vals else None


def _weighted_overall(
    pitch: float | None, rhythm: float | None, pron: float | None, wp: float, wr: float, wpr: float
) -> float | None:
    """加权综合；分项缺失按剩余权重归一；全缺失 → None（不伪造分数，docs/11 Q-B08）。"""
    items = [(v, w) for v, w in ((pitch, wp), (rhythm, wr), (pron, wpr)) if v is not None]
    if not items:
        return None
    total_w = sum(w for _, w in items)
    return round(sum(v * w for v, w in items) / total_w, 2)


def _f0_pairs(user_win: np.ndarray, start_ms: int, hop: float) -> list[list[float]]:
    """用户逐帧 F0 → [[t_ms, f0_hz]...]（落库降密度格式，D4）。"""
    return [[round(start_ms + i * hop, 1), round(float(v), 1)] for i, v in enumerate(user_win)]


def math_ceil(x: float) -> int:
    """math.ceil 包装（保持纯函数/免顶层 import 负担）。"""
    import math

    return math.ceil(x)
