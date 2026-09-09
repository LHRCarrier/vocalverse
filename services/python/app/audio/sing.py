"""唱歌评分核心（docs/06 §9.4：DTW 对齐 + 音准/节奏映射 + 发音复用口语引擎）。

**口径版本 v2（2026-09-09 第一层修正，组长拍板 A3/B2/C1）**——映射表与权重不变
（docs/06 §9.4 定稿：音准 ≤50→90+ / ≤100→70~90 / ≤200→50~65 / >300→<40；节奏
≤150ms→90+ / ≤300→75~90 / ≤600→55~75 / >1000→<50；综合 0.5·音准+0.2·节奏+0.3·发音），
只修「喂给映射表的数值怎么算」：

- **音准（B2）**：逐句**局部 DTW**（Sakoe-Chiba 带 + 斜率约束）把用户帧映射到参考帧后
  再比 cent——消除"局部快慢不同被误判跑调"；cent 八度折叠（±600，见 :func:`_fold_cent`）。
- **节奏（A3）**：逐句**起唱时刻检测**（F0 有声段优先，能量 onset 兜底），与
  「LRC 时间戳 + 整首对齐偏移」比较——不再用几何窗口起点（v1 的缺陷：节奏分只是
  全局 offset 的线性函数，与逐句跟拍无关）。
- **可信度（C1）**：有效帧 < max(10, 参考句帧数×30%) → 该句 `skipped=low_frames`
  降权（不入均分），避免"只唱半句却给高分"。
- **对齐方向**：整首 DTW 的 offset 语义 = 用户时间轴 = 参考时间 + offset
  （v1 窗口用 `- offset` 方向反了，一并修正）。

其它（不变）：发音 = 复用口语评分引擎（ISE 抽样句，D3）；缺失降权 D5（skipped 不入均分、
`is_complete = 有效句 ≥ expected×80%`）；用户逐帧 F0 落库（D4）。

实现约定：纯 CPU 同步（numpy/pyin 重活），调用方必须 ``asyncio.to_thread``；
``SingScorer`` 为 ABC + ``FakeSingScorer``（CI 零模型/零 Key，docs/06 第 6 章）。
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger("vocalverse")

# 算法世代（写入 sing_attempts.scoring_version；docs/10 §4.3：升级后旧分可解释、不作废）
SCORING_VERSION = "v2"
ALIGN_METHOD = "dtw-local-sakoe-chiba-v2"

# 整首对齐参数（docs/06 §9.4：Sakoe-Chiba window ≤10% + 斜率约束）
DTW_BAND_RATIO = 0.10
# 逐句局部 DTW（B2 拍板）：句级序列短，带可放宽到 25%（允许句内 ±25% 时间伸缩）
LOCAL_DTW_BAND_RATIO = 0.25

# 起唱时刻检测（A3 拍板：F0 有声段优先 → 能量 onset 兜底）
ONSET_SILENCE_GAP_MS = 150.0  # 视为「新起唱」的最小前置静音间隔
ONSET_MIN_RUN_FRAMES = 3  # 连续有声帧下限（短于此视为噪声/尾音）
ONSET_ENERGY_MIN_RMS = 0.005  # 能量兜底绝对下限（防全静音误判）
ONSET_ENERGY_RELATIVE = 0.35  # 能量兜底相对阈值（max RMS 的 35%）

# 有效帧门槛（C1 重拍板 2026-09-09）：用户有声帧 ≥ max(10, 参考句帧数 × 15%)
# 实测依据：3 段真实演唱的逐句有声帧覆盖率 15%~73%（换气/长音拖音/轻声/唱快漏字都会降），
# 原定 30% 会误杀大量正常句（3 段录音分别跳 0/3/4 句）→ 降到 15% 并保留绝对下限。
# 门槛判「用户窗口内有声帧数」（不是 DTW 路径对数——路径对数会再打一次折）。
MIN_VOICED_FRAMES = 10
MIN_VOICED_RATIO = 0.15
# 统计下限：无论句长，参与中位数的有效帧对不得少于该值（低于此统计不可靠）
MIN_ALIGN_PAIRS = 10
# 清音帧对的 DTW 成本（不设为 0：成本 0 会诱使路径穿过静音段"免费对齐"）
SILENT_FRAME_COST = 100.0


def _fold_cent(cents: np.ndarray | float):
    """频率比 cent → 折叠到 [-600, 600]（八度等价；+1200 与 0 视为同一音高）。

    依据：docs/06 §9.4「音高轮廓先归一化」+ 2026-09-09 真机实测（用户 78~110Hz vs
    参考 341Hz，低约 2 个八度）——绝对频率比较会恒判 0 分；KTV/唱吧类评分同口径。
    """
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


def _folded_cent_series(user_f0: np.ndarray, ref_f0: np.ndarray) -> np.ndarray:
    """帧对帧的折叠 cent 偏差序列（清音帧置 0 = 对齐成本 0，不惩罚停顿）。

    长度 = min(len(user), len(ref))；八度等价（:func:`_fold_cent`）。
    """
    n = min(len(user_f0), len(ref_f0))
    u = np.asarray(user_f0[:n], dtype=float)
    r = np.asarray(ref_f0[:n], dtype=float)
    both = (u > 0) & (r > 0)
    cents = np.zeros(n, dtype=float)
    if both.any():
        ratio = np.maximum(u[both], 1e-9) / np.maximum(r[both], 1e-9)
        cents[both] = _fold_cent(1200.0 * np.log2(ratio))
    return cents


def _cent_deviation(user_f0: np.ndarray, ref_f0: np.ndarray) -> float | None:
    """同索引逐帧 cent 偏差（**v1 口径**，保留供对照/测试；主路径改用对齐后版本）。

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


# ---------------------------------------------------------------------------
# DTW（整首粗对齐 + 逐句局部精对齐共用内核）
# ---------------------------------------------------------------------------
def _backtrack(d: np.ndarray, *, open_end: bool) -> list[tuple[int, int]]:
    """从 DTW 累积成本矩阵回溯路径（两版 DTW 共用）。"""
    n, m = d.shape
    if n == 0 or m == 0:
        return []
    if open_end:
        i, j = n - 1, int(np.argmin(d[n - 1, :]))
    else:
        i, j = n - 1, m - 1
    path: list[tuple[int, int]] = []
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
    path.reverse()
    return path


def _dtw_cost_matrix(cost: np.ndarray, band_ratio: float, *, open_end: bool) -> np.ndarray:
    """Sakoe-Chiba 带 + 斜率约束的累积成本矩阵（cost 为 n×m 帧对成本）。

    斜率约束 = 水平/垂直步代价 ×2（鼓励对角，抑制"一句压成一点"）。
    """
    n, m = cost.shape
    w = max(1, int(max(n, m) * band_ratio))
    d = np.full((n, m), np.inf)
    d[0, 0] = cost[0, 0]
    for i in range(n):
        lo, hi = max(0, i - w), min(m - 1, i + w)
        for j in range(lo, hi + 1):
            if i == 0 and j == 0:
                continue
            c = cost[i, j]
            cands = []
            if i > 0 and np.isfinite(d[i - 1, j]):
                cands.append(d[i - 1, j] + c * 2.0)
            if j > 0 and np.isfinite(d[i, j - 1]):
                cands.append(d[i, j - 1] + c * 2.0)
            if i > 0 and j > 0 and np.isfinite(d[i - 1, j - 1]):
                cands.append(d[i - 1, j - 1] + c)
            if cands:
                d[i, j] = min(cands)
    return d


def _fold_cent_matrix(user_win: np.ndarray, ref_win: np.ndarray) -> np.ndarray:
    """句级帧对成本矩阵：|折叠 cent 差|（八度等价）。

    清音帧对（任一侧无声）→ 固定成本 ``SILENT_FRAME_COST``：既不让 DTW 把静音当"免费
    对齐点"（成本 0 会诱使路径穿过静音段），也不至于完全无法跨越。
    """
    u = np.asarray(user_win, dtype=float)[:, None]
    r = np.asarray(ref_win, dtype=float)[None, :]
    cents = 1200.0 * np.log2(np.maximum(u, 1e-9) / np.maximum(r, 1e-9))
    cost = np.abs(_fold_cent(cents))
    invalid = (u <= 0) | (r <= 0)
    return np.where(invalid, SILENT_FRAME_COST, cost)


def _dtw_path(
    uu: np.ndarray, rr: np.ndarray, band_ratio: float, *, open_end: bool
) -> list[tuple[int, int]]:
    """序列版 DTW（成本 = |uu[i] − rr[j]|）——整首粗对齐用（O(n²) 成本矩阵对 180s 歌过大）。"""
    n, m = len(uu), len(rr)
    if n == 0 or m == 0:
        return []
    cost = np.abs(np.asarray(uu, dtype=float)[:, None] - np.asarray(rr, dtype=float)[None, :])
    d = _dtw_cost_matrix(cost, band_ratio, open_end=open_end)
    return _backtrack(d, open_end=open_end)


def _dtw_path_cost(cost: np.ndarray, band_ratio: float, *, open_end: bool) -> list[tuple[int, int]]:
    """成本矩阵版 DTW（局部对齐用：成本 = 折叠 cent 差，句级规模可承受）。"""
    if cost.size == 0:
        return []
    d = _dtw_cost_matrix(cost, band_ratio, open_end=open_end)
    return _backtrack(d, open_end=open_end)


def _coarse_bpm_ratio(user_ms: float, ref_ms: float) -> float:
    """整首时长比（信息性；v2 起**不参与**节奏计算，节奏改由起唱时刻检测驱动）。"""
    if not user_ms or not ref_ms or user_ms <= 0 or ref_ms <= 0:
        return 1.0
    return min(max(float(ref_ms / user_ms), 0.5), 2.0)


def align_frames(user_f0: np.ndarray, ref_f0: np.ndarray, hop_ms: float) -> tuple[float, float]:
    """整首对齐：返回 (bpm_ratio, offset_ms)。

    语义（v2 修正）：**用户时间轴 = 参考时间轴 + offset_ms**
    （offset>0 = 用户整体落后/晚起唱）。调用方据此把参考句窗映射到用户时间轴取窗口。

    无有效帧 → (1.0, 0.0)（调用方按不可对齐降权，不伪造）。
    """
    n = min(len(user_f0), len(ref_f0))
    if n < 8:
        return 1.0, 0.0
    u = np.asarray(user_f0[:n], dtype=float)
    r = np.asarray(ref_f0[:n], dtype=float)
    if ((u > 0) & (r > 0)).sum() < 8:
        return 1.0, 0.0
    uu = _hz_to_series_cent(u, r)
    rbg = r[r > 0]
    if len(rbg) == 0:
        return 1.0, 0.0
    rmed = float(np.median(rbg))
    rr = 1200.0 * np.log2(np.maximum(r, 1e-9) / rmed)
    uu = np.where(np.isfinite(uu), uu, 0.0)
    rr = np.where(np.isfinite(rr), rr, 0.0)

    # 长歌护栏：>6000 帧按 2 帧步长降采样（180s@32ms=5660 帧，兜底上界）
    step = 1
    if n > 6000:
        step = 2
        uu = uu[::step]
        rr = rr[::step]
        n = len(uu)

    path = _dtw_path(uu, rr, DTW_BAND_RATIO, open_end=True)
    if not path:
        return 1.0, 0.0
    deltas = [pi - pj for pi, pj in path]
    offset = float(np.median(deltas) * hop_ms * step)
    return _coarse_bpm_ratio(n * hop_ms * step, len(ref_f0) * hop_ms), offset


# ---------------------------------------------------------------------------
# 起唱时刻检测（A3：F0 有声段优先 → 能量 onset 兜底）
# ---------------------------------------------------------------------------
def _first_new_run(flag: np.ndarray, gap_frames: int, min_run_frames: int) -> int | None:
    """在布尔序列中找第一个「连续 ≥min_run 为真」且「前 gap_frames 内全为假」的段起点。"""
    n = len(flag)
    i = 0
    while i < n:
        if not flag[i]:
            i += 1
            continue
        start = i
        while i < n and flag[i]:
            i += 1
        if i - start < min_run_frames:
            continue
        if start == 0 or not flag[max(0, start - gap_frames) : start].any():
            return start
    return None


def detect_onset_ms(
    user_f0: np.ndarray,
    rms: np.ndarray | None,
    hop_ms: float,
    *,
    silence_gap_ms: float = ONSET_SILENCE_GAP_MS,
    min_run_frames: int = ONSET_MIN_RUN_FRAMES,
) -> float | None:
    """检测「新起唱」时刻（相对序列起点，ms）；检测不到 → None。

    主路径（A3）：F0 有声段 —— 找第一个「前置静音 ≥silence_gap_ms 且连续 ≥min_run 帧有声」
    的段起点（前置静音判据避免把上一句尾音/句内换气当成新起唱）。
    兜底：窗口内无任何有声帧时，用能量包络（RMS 跃升）定位起唱点。
    """
    voiced = np.asarray(user_f0, dtype=float) > 0
    gap_frames = max(1, int(round(silence_gap_ms / hop_ms)))
    start = _first_new_run(voiced, gap_frames, min_run_frames)
    if start is not None:
        return float(start * hop_ms)
    # 兜底：能量 onset（F0 全清音但确有发声时；如气声/低信噪比）
    if rms is not None and len(rms):
        arr = np.asarray(rms, dtype=float)[: len(user_f0)]
        if arr.size and np.isfinite(arr).any():
            thr = max(ONSET_ENERGY_MIN_RMS, ONSET_ENERGY_RELATIVE * float(np.max(arr)))
            start = _first_new_run(arr >= thr, gap_frames, min_run_frames)
            if start is not None:
                return float(start * hop_ms)
    return None


# ---------------------------------------------------------------------------
# 逐句局部对齐（B2）+ 对齐后音准
# ---------------------------------------------------------------------------
def local_align(
    user_win_f0: np.ndarray,
    ref_win_f0: np.ndarray,
    band_ratio: float = LOCAL_DTW_BAND_RATIO,
) -> tuple[float, list[tuple[int, int]]]:
    """句级局部 DTW：返回 (offset_frames, path)。

    offset_frames = 路径 (user_idx - ref_idx) 的中位数（>0 = 该句用户落后参考）。

    成本 = **绝对折叠 cent 差**的帧对矩阵（:func:`_fold_cent_matrix`）——八度等价，
    且与最终音准评分同尺度（不做"各自中位归一化"：那会给两条序列引入不同的基准偏移，
    使 DTW 目标与评分目标不一致）。
    """
    n = min(len(user_win_f0), len(ref_win_f0))
    if n < 3:
        return 0.0, []
    u = np.asarray(user_win_f0[:n], dtype=float)
    r = np.asarray(ref_win_f0[:n], dtype=float)
    cost = _fold_cent_matrix(u, r)
    path = _dtw_path_cost(cost, band_ratio, open_end=False)
    if not path:
        return 0.0, []
    deltas = [pi - pj for pi, pj in path]
    return float(np.median(deltas)), path


def aligned_cent_deviation(
    user_win_f0: np.ndarray, ref_win_f0: np.ndarray, path: list[tuple[int, int]]
) -> tuple[float | None, int]:
    """按 DTW 路径对齐后比较 cent：返回 (|cent| 中位数, 有效帧对数)。

    有效帧对 = 路径上双端都有声的帧对；<3 对 → (None, n)（该句按缺失降权，D5）。
    """
    u = np.asarray(user_win_f0, dtype=float)
    r = np.asarray(ref_win_f0, dtype=float)
    cents: list[float] = []
    for i, j in path:
        if i >= len(u) or j >= len(r):
            continue
        if u[i] > 0 and r[j] > 0:
            ratio = max(u[i], 1e-9) / max(r[j], 1e-9)
            cents.append(float(_fold_cent(1200.0 * np.log2(ratio))))
    if len(cents) < 3:
        return None, len(cents)
    return float(np.median(np.abs(cents))), len(cents)


def min_voiced_frames(ref_frames: int) -> int:
    """有效帧门槛（C1 拍板）：max(10, ceil(参考句帧数 × 30%))。"""
    import math

    return max(MIN_VOICED_FRAMES, math.ceil(ref_frames * MIN_VOICED_RATIO))


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
    # no_pitch / no_ref / low_frames / pron_skipped
    reason: str | None = None
    ref_seq: int | None = None
    no_ref: bool = False
    # v2：该句起唱偏差（ms，相对「LRC 时间戳 + 整首对齐偏移」；None = 未检出）
    onset_dev_ms: float | None = None
    # D4：用户逐帧 F0（降密度 [[t_ms, f0_hz], ...]，评分时保留句内全帧）
    user_f0: list[list[float]] = field(default_factory=list)
    # D3 双序列图辅助：帧级折叠 cent 偏差（对齐后）
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


def aggregate_result(lines: list[LineScore]) -> SingScoreResult:
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
    """真实评分器：pyin 用户 F0 → 整首对齐 + 逐句局部对齐 → 音准/节奏映射。"""

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
        user_rms = np.asarray(track.rms, dtype=float) if track.rms else None
        # 整首对齐：用户时间轴 = 参考时间轴 + offset（v2 方向修正）
        bpm_ratio, offset_ms = align_frames(user_f0, ref_full, hop)

        lines: list[LineScore] = []
        for a in ref_arrays:
            ref_win = a["f0s"]
            if len(ref_win) == 0 or not np.any(ref_win > 0):
                lines.append(_skipped_line(a, "no_ref", no_ref=True))
                continue
            # 参考句窗映射到用户时间轴（+offset）；局部对齐带外再各留一帧缓冲
            win_start = a["start_ms"] + offset_ms
            win_end = a["end_ms"] + offset_ms
            window = slice_window(track, win_start, win_end)
            user_win = np.asarray(window["f0s"], dtype=float)
            rms_win = (
                user_rms[window["frame_start"] : window["frame_end"]]
                if user_rms is not None and len(user_rms)
                else None
            )
            # 音准（B2）：逐句局部 DTW → 对齐后 cent 中位
            _off_frames, path = local_align(user_win, ref_win)
            cent, n_pairs = aligned_cent_deviation(user_win, ref_win, path)
            # 可信度（C1）：用户有声帧不足 → 降权（避免"只唱半句却给高分"）
            n_voiced = int(np.sum(user_win > 0))
            need = min_voiced_frames(len(ref_win))
            if cent is None or n_voiced < need or n_pairs < MIN_ALIGN_PAIRS:
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
                        reason="low_frames" if n_voiced else "no_pitch",
                        ref_seq=a["seq"],
                        user_f0=_f0_pairs(user_win, win_start, hop),
                    )
                )
                continue
            pitch = pitch_score_from_cent(cent)
            # 节奏（A3）：起唱时刻 vs 「LRC 起点 + 整首偏移」
            onset_rel = detect_onset_ms(user_win, rms_win, hop)
            onset_dev = (
                abs(onset_rel - (a["start_ms"] + offset_ms - win_start))
                if onset_rel is not None
                else None
            )
            rhythm = rhythm_score_from_dev(onset_dev) if onset_dev is not None else None
            # 帧级折叠 cent 偏差（D3 图；按路径映射后落到参考帧索引）
            cent_dev = _path_cent_series(user_win, ref_win, path)
            lines.append(
                LineScore(
                    seq=a["seq"],
                    start_ms=a["start_ms"],
                    end_ms=a["end_ms"],
                    pitch_score=round(pitch, 2),
                    rhythm_score=round(rhythm, 2) if rhythm is not None else None,
                    pron_score=None,
                    synced=True,
                    ref_seq=a["seq"],
                    onset_dev_ms=round(onset_dev, 1) if onset_dev is not None else None,
                    user_f0=_f0_pairs(user_win, win_start, hop),
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


def _skipped_line(ref: dict, reason: str, *, no_ref: bool = False) -> LineScore:
    return LineScore(
        seq=ref["seq"],
        start_ms=ref["start_ms"],
        end_ms=ref["end_ms"],
        pitch_score=None,
        rhythm_score=None,
        pron_score=None,
        synced=False,
        skipped=True,
        reason=reason,
        ref_seq=ref["seq"],
        no_ref=no_ref,
    )


def _path_cent_series(
    user_win: np.ndarray, ref_win: np.ndarray, path: list[tuple[int, int]]
) -> list[float]:
    """按 DTW 路径把用户帧映射到参考帧索引，产出帧级折叠 cent 序列（D3 图用）。"""
    out: list[float | None] = [None] * len(ref_win)
    u = np.asarray(user_win, dtype=float)
    r = np.asarray(ref_win, dtype=float)
    for i, j in path:
        if i >= len(u) or j >= len(r) or u[i] <= 0 or r[j] <= 0:
            continue
        ratio = max(u[i], 1e-9) / max(r[j], 1e-9)
        out[j] = float(_fold_cent(1200.0 * np.log2(ratio)))
    return [0.0 if v is None else v for v in out]


class FakeSingScorer(SingScorer):
    """CI 零模型打桩：恒定 440Hz 用户音高 → 恒定分数（结构性验证，不参与真评分）。"""

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
                    onset_dev_ms=0.0,
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


def _f0_pairs(user_win: np.ndarray, start_ms: float, hop: float) -> list[list[float]]:
    """用户逐帧 F0 → [[t_ms, f0_hz]...]（落库降密度格式，D4）。"""
    return [[round(start_ms + i * hop, 1), round(float(v), 1)] for i, v in enumerate(user_win)]


def math_ceil(x: float) -> int:
    """math.ceil 包装（保持纯函数/免顶层 import 负担）。"""
    import math

    return math.ceil(x)
