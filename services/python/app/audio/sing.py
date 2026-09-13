"""唱歌评分核心（docs/06 §9.4：DTW 对齐 + 音准/节奏映射 + 发音复用口语引擎）。

**口径版本 v3（2026-09-09 第二层「算法增强」，组长拍板 item5~8 推荐项）**——
映射表与综合权重基线不变（docs/06 §9.4 定稿：音准 ≤50→90+ / ≤100→70~90 / ≤200→50~65 /
>300→<40；节奏 ≤150ms→90+ / ≤300→75~90 / ≤600→55~75 / >1000→<50；
综合 0.5·音准+0.2·节奏+0.3·发音），只增强「喂给映射表的数值怎么来」：

- **音域自适应移调（item5）**：V2 只做八度折叠（±600），丢失「你系统性偏低 3 个半音」——
  现在全曲统计 ``shift = fold(1200·log2(用户F0中位/参考F0中位))`` 量化到**整数半音**，
  作为全局常数注入所有帧级比较（局部 DTW 成本/对齐后 cent/cent_dev）；
  ``alignment.transpose_semitones/range_hint`` 出音域提示（「这首歌对你偏高，
  建议降 N 个半音唱」）；只补偿整体平移，相对偏差（轮廓跑调）仍然被罚。
- **F0 中值滤波（item6）**：评分前用户整轨**保静音**中值滤波（kernel=5 帧=160ms，
  覆盖 5~6Hz 颤音整周期）——参考是合成音无颤音（SG-13 素材物化），滤波后比较才公平；
  0 帧强制保持 0（滤器不跨静音）；只滤用户侧（未来真人原唱参考的颤音是本体的
  演唱特征，不应删除）；``lines[i].user_f0`` 仍存**原始帧**（D4 保真）。
- **真实 BPM（item7）**：**两侧同量纲音符级 onset**——用户侧 ``librosa.onset_detect``
  （TrackF0.onsets_ms）；参考侧提取期入库的 ``pitch_ref.onsets_ms``（pyin-v2，
  slice_window 落盘）→ 各自 IOI 中位→BPM，``bpm_ratio = user_bpm / ref_bpm``；
  替代 v2 的「时长截断比」伪 bpm_ratio（IOI 过滤 [200,3000]ms + ≥3 间隔 + 相邻重复
  onset 去重；任一侧不可用回落时长比并标 ``bpm_source="duration"``）。
  **2026-09-10 修正（BUG-1）**：v1 误用「LRC 逐句 start_ms 间隔」作参考侧（秒级异量纲，
  且被 3000ms 上界全滤掉）→ bpm_source 恒 duration；现改为同源音符级不入 LRC 口径。
  节奏分仍由逐句起唱偏差驱动（不回归 v1「节奏=全局偏移线性函数」缺陷）。
- **动态权重/参考完整性（item8）**：``ref_coverage=(期望句数−no_ref 句数)/期望句数``；
  三段政策：≥80% 全额 0.5；40~80% 线性 0.5→0.2；<40% 音准**不计入综合**（仅展示+标注）；
  ``pitch_reliability=full/reduced/low`` + ``weight_note`` 进 alignment
  （前端「分数仅供参考」标注）——参考缺失多时不再硬算。

**口径 v2 保留（2026-09-09 第一层修正，组长拍板 A3/B2/C1）**：逐句局部 DTW
（Sakoe-Chiba 带 + 斜率约束）、逐句起唱时刻检测（F0 有声段优先 → 能量 onset 兜底）、
有效帧门槛（max(10, 参考帧数×15%) → skipped=low_frames）、对齐方向
「用户时间轴 = 参考 + offset」。缺失降权 D5（skipped 不入均分、is_complete ≥80%）、
发音 = 复用口语评分引擎（ISE 抽样句，D3）、用户逐帧 F0 落库（D4）。

**句窗口速度缩放（BUG-4，2026-09-10）**：句窗口映射 = 整体平移（`offset`）+ **按
`bpm_ratio` 缩放句长**（用户慢 → 窗口更长），且句级局部 DTW **不再按短侧截断**——
此前用户整体速度与参考差异大时（实测慢 18.9%）句尾被窗口/截断丢掉，DTW 只能在残缺
序列上对齐 → 音准被低估（pitch 78 vs 修复后 ≈95），把速度问题错算进了音准维度。

实现约定：纯 CPU 同步（numpy/pyin 重活），调用方必须 ``asyncio.to_thread``；
``SingScorer`` 为 ABC + ``FakeSingScorer``（CI 零模型/零 Key，docs/06 第 6 章）。
"""

from __future__ import annotations

import abc
import logging
import math
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger("vocalverse")

# 算法世代（写入 sing_attempts.scoring_version；docs/10 §4.3：升级后旧分可解释、不作废）
# v5（2026-09-10 · P0 修复 R1 判据）：R1 由「整轨换气结构」下沉为**逐句**新起唱判据
# （见 onset_is_continuation）；分数分布因此变化，故升版本留痕。依据 docs/06 §9.4（口径 v5）。
# v6（2026-09-10 · F1 复测修复）：句窗端点改走**时间弯折**（DTW 路径映射 + 全局仿射兜底），
# 修「偏慢演唱整首无节奏分」（见 align_time_warp）；分数分布变化 → 升版本。
SCORING_VERSION = "v6"
ALIGN_METHOD = "dtw-local-sakoe-chiba-v3"

# 整首对齐参数（docs/06 §9.4：Sakoe-Chiba window ≤10% + 斜率约束）
DTW_BAND_RATIO = 0.10
# 逐句局部 DTW（B2 拍板）：句级序列短，带可放宽到 25%（允许句内 ±25% 时间伸缩）
LOCAL_DTW_BAND_RATIO = 0.25
# 整首粗对齐规模护栏（P1-11）：≤FULL 帧全分辨率；超过则降到 TARGET 帧量级
# （成本矩阵 O(n²) 内存 + 带内纯 Python 双层循环 O(2·w·n) 时间，180s 歌必须降采样。
# TARGET=3000 而非 2000：offset 量化 = hop×step，取 step=2（64ms）远低于节奏分档阈值
# 150ms；若压到 2000 帧会取 step=3（96ms），省下的内存不值得牺牲对齐精度）
GLOBAL_DTW_FULL_FRAMES = 4000
GLOBAL_DTW_TARGET_FRAMES = 3000

# 时间弯折（口径 v6 · F1 修复）：
# - stretch = 用户时间 / 参考时间（>1 = 用户更慢），clamp 与 :func:`window_scale` 同源
#   （八度误判/乱唱极端值沿边界处理）；
# - 句窗端点用 **DTW 路径局部中位**映射（分段弯折，能跟上"换气累积"这类非线性漂移），
#   邻域内无路径点（句首/句尾外推）才回退全局仿射 `offset + stretch × ref`；
# - tol_ms：路径邻域半径（≈8 帧 @32ms），太小会退化成逐点噪声，太大会把整句平均掉。
TIME_WARP_STRETCH_MIN = 1.0 / 1.5
TIME_WARP_STRETCH_MAX = 1.0 / 0.67
# 斜率吸附带：|拟合斜率 − 1| ≤ 3% 视为"无速度差"（低于分档分辨率，纯估计噪声）
TIME_WARP_SNAP_BAND = 0.03
# 两个独立速度来源（onset 仲裁 / DTW 路径拟合）互证容差：超出即认为 onset 比值不可信
TIME_WARP_AGREE_TOL = 0.20
# 起唱**检测窗**向两侧外扩的余量：速度模型不可能吃掉"每句换气累积"（真人 5 句 ×300ms ≈ 1.5s），
# 故检测窗放宽，让"静音→有声"跳变落在窗口内可被找到；评分窗（音准/落库）仍是收窄的句窗。
TIME_WARP_WINDOW_PAD_MS = 400.0

# 起唱时刻检测（A3 拍板：F0 有声段优先 → 能量 onset 兜底）
ONSET_SILENCE_GAP_MS = 150.0  # 视为「新起唱」的最小前置静音间隔
ONSET_MIN_RUN_FRAMES = 3  # 连续有声帧下限（短于此视为噪声/尾音）
ONSET_ENERGY_MIN_RMS = 0.005  # 能量兜底绝对下限（防全静音误判）
ONSET_ENERGY_RELATIVE = 0.35  # 能量兜底相对阈值（max RMS 的 35%）
# 口径 v6：「有声」判定的能量相对阈值（75 分位 RMS 的比例）——真人换气通常比演唱低 15dB 以上，
# 取 0.12 ≈ −18dB（略保守，避免把轻声长音误判成换气）
ONSET_VOICED_ENERGY_RELATIVE = 0.12

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

# ---------------------------------------------------------------------------
# 口径 v3 参数（docs/06 §9.4 登记，2026-09-09 组长拍板 item5~8）
# ---------------------------------------------------------------------------
# item6：中值滤波窗口（帧）。5 帧 = 160ms，覆盖 5~6Hz 颤音整周期（167~200ms）；
# 3 帧（96ms）不足 2/3 周期，禁用。
MEDFILT_KERNEL = 5
# item5：计算整体移调所需最少有效帧对数（低于此统计不可信 → 不移调）
MIN_TRANSPOSE_PAIRS = 10
# item7：IOI（onset 间隔）合法区间与最少间隔数——[200,3000]ms 夹掉半速/倍速混淆与
# 长休止污染；<3 个间隔 → 中位统计不可信。**口径：两侧同为音符级 onset**（BUG-1 修正）
MIN_IOI_MS = 200.0
MAX_IOI_MS = 3000.0
MIN_IOI_COUNT = 3
# onset 去重最小间隔（ms）：librosa.onset_detect 在强起音处会给出相邻重复帧（同刻检出两次）
ONSET_DEDUPE_MS = 50.0
# BPM 合理域与八度分歧判据（combine_bpm）
BPM_FLOOR = 40.0
BPM_CEIL = 240.0
BPM_OCTAVE_LO = 1.5
BPM_OCTAVE_HI = 2.3
# 句窗口缩放的 ratio 可信域（BUG-4 风险控制）：超出视为速度比不可信 → clamp 到边界
WIN_RATIO_MIN = 0.67
WIN_RATIO_MAX = 1.5

# ---------------------------------------------------------------------------
# 口径 v4 参数（2026-09-10 · 乱唱鲁棒性；组长拍板 R1/R2/R3）
# ---------------------------------------------------------------------------
# R2 音符命中率：参考按"连续同音高段"切音符（跳变 ≥NOTE_SPLIT_CENT 视为新音符），
# 用户在该音符的时间段内是否有足够帧落在 ±NOTE_HIT_TOL_CENT 内 → 命中率。
# **用法（组长拍板 C）：音准分乘性衰减**，不做硬阈值判罚——
# factor = NOTE_HIT_FACTOR_FLOOR + (1−FLOOR)×命中率（完全没唱在调上 ×0.5，完全命中 ×1.0）。
# 为什么不做"<阈值不给分"：实测（`local/hit_tol_scan.py`）命中率**无法区分**
# "跑调但认真的真人演唱"（11%~47%）与"乱唱"（14%~50%）——所有容差下两组重叠；
# 轮廓相关性同样不可分（真唱 −0.07~0.29 vs 乱唱 −0.40~0.45）。故连续降分：
# 乱唱 58→~32、跑调真唱同样 ~32（保留低分与改进指引，不清零、不误判为"没唱"）。
NOTE_HIT_TOL_CENT = 100.0
NOTE_SPLIT_CENT = 60.0
#: 音符命中要求的帧占比（该音符时间段内落在 ±容差 的帧比例；自测：任意帧判据会让
#: 线性扫频"恰好路过"每个音符而拿 100%，时间对齐 + 比例门槛才能区分真唱与扫频）
NOTE_HIT_FRAMES_RATIO = 0.3
#: 音准分衰减下限（命中率 0 时的系数）——取 0.6 而非 0.5：实测"唱得准"的素材命中率
#: 约 58%（判据本身的路径/切分误差），0.5 会把准唱从 95 压到 71（仍偏严）；
#: 0.6 → 命中 0 时 ×0.6、命中 58% → ×0.83（准唱 ~79、乱唱 ~35），符合"乱唱显著降分、
#: 准唱轻微下调"的口径意图。
NOTE_HIT_FACTOR_FLOOR = 0.6
# R1 起唱判据（口径 v4）：**整轨换气结构**——存在 ≥ONSET_SILENCE_GAP_MS 的静音段才算
# "有句的概念"；否则（一口气唱到底，如连续乱唱）不给节奏分。
# 实测依据：真机乱唱每句窗口前 10/10 帧有声却判 onset_dev=0ms → 节奏恒 95；
# 而"句前 320ms 有声"这个初版判据在**整体速度差大**时会误杀正常真唱（窗口错位到上一句尾音，
# 自测：真唱素材 6/6 句 rhythm=None）→ 改用整轨结构判据（不受窗口错位影响）。
# R3 用户有效句覆盖率 → 综合分置信度（三段线性；<40% 不给综合分）
USER_COVERAGE_FULL = 0.8
USER_COVERAGE_LOW = 0.4
COVERAGE_CONF_FLOOR = 0.6
# item8：参考完整性三段政策阈值（≥80% 全额 / 40~80% 线性 0.5→0.2 / <40% 不计入）
REF_COVERAGE_FULL = 0.80
REF_COVERAGE_LOW = 0.40
PITCH_WEIGHT_FULL = 0.5
PITCH_WEIGHT_FLOOR = 0.2


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


def _cent_deviation(
    user_f0: np.ndarray, ref_f0: np.ndarray, shift_cent: float = 0.0
) -> float | None:
    """同索引逐帧 cent 偏差（**v1 口径**，保留供对照/测试；主路径改用对齐后版本）。

    ``shift_cent`` 为口径 v3 的整体移调量（item5）：先移调再比——对 v1 口径同样生效，
    便于新旧对照；默认 0（历史测试语义不变）。
    有效帧（双端有声）不足 3 帧 → None（该句按缺失降权处理，D5）。
    """
    n = min(len(user_f0), len(ref_f0))
    u = np.asarray(user_f0[:n], dtype=float)
    r = np.asarray(ref_f0[:n], dtype=float)
    mask = (u > 0) & (r > 0)
    if mask.sum() < 3:
        return None
    d = _fold_cent(
        1200.0 * np.log2(np.maximum(u[mask], 1e-9) / np.maximum(r[mask], 1e-9)) - shift_cent
    )
    return float(np.median(np.abs(d)))


# ---------------------------------------------------------------------------
# 口径 v3 · 纯函数（中值滤波 / 整体移调 / 真实 BPM / 参考完整性政策）
# ---------------------------------------------------------------------------
def median_filter_f0(f0: np.ndarray, kernel: int = MEDFILT_KERNEL) -> np.ndarray:
    """保静音中值滤波（item6，docs/06 §9.4 口径 v3：抑制颤音抖动，与合成参考对称）。

    规则：
    - 窗口内只对 **>0 帧** 取中位（跨静音不"洗澡"——0 帧代表无音高，不是音高 0）；
    - 输出中 0 帧强制保持 0（滤波器不得把静音抹成音高，否则污染起唱检测/门槛统计）；
    - 窗口内有声帧 <2 → 保留原值（孤立帧不引入也不删除，preserve 无语帧总量不变）。
    """
    arr = np.asarray(f0, dtype=float)
    if kernel < 3 or arr.size < kernel:
        return arr.copy()
    half = kernel // 2
    padded = np.pad(arr, (half, half))  # 0 填充（静音语义）
    out = arr.copy()
    for i in range(arr.size):
        window = padded[i : i + kernel]
        voiced = window[window > 0]
        if voiced.size >= 2:
            out[i] = float(np.median(voiced))
    # 强制 0 帧归零：静音段边缘帧可能被"窗口内有 ≥2 个有声邻居"拉成音高——静音必须保持静音
    out[arr == 0] = 0.0
    return out


def estimate_transpose_semitones(user_f0: np.ndarray, ref_f0: np.ndarray) -> int:
    """整首移调量（整数半音；item5，docs/06 §9.4 口径 v3）。

    ``shift = fold(1200·log2(用户F0中位/参考F0中位))`` 四舍五入到半音；
    shift<0 = 用户整体低于参考（歌对用户偏高 → 建议降调）；先 fold 再量化保证
    八度等价（与 _fold_cent 口径一致——用户低一个八度 + 3 半音 ≈ 低 3 半音）。
    有效帧对数 < ``MIN_TRANSPOSE_PAIRS`` → 0（统计不可信，不移调不提示）。
    """
    u = np.asarray(user_f0, dtype=float)
    r = np.asarray(ref_f0, dtype=float)
    uv, rv = u[u > 0], r[r > 0]
    if uv.size < MIN_TRANSPOSE_PAIRS or rv.size < MIN_TRANSPOSE_PAIRS:
        return 0
    um, rm = float(np.median(uv)), float(np.median(rv))
    if um <= 0 or rm <= 0:
        return 0
    cents = 1200.0 * math.log2(um / rm)
    return int(round(_fold_cent(cents) / 100.0))


def range_hint_text(shift_st: int) -> str | None:
    """音域提示文案（item5；shift<0=用户偏低→歌偏高→建议降调；0 → None 不显示）。"""
    if shift_st == 0:
        return None
    n = abs(shift_st)
    if shift_st < 0:
        return f"这首歌对你偏高，建议降 {n} 个半音唱"
    return f"这首歌对你偏低，建议升 {n} 个半音唱"


def bpm_from_onsets(
    onsets_ms,
    *,
    min_ioi_ms: float = MIN_IOI_MS,
    max_ioi_ms: float = MAX_IOI_MS,
) -> float | None:
    """onset 间隔中位 → BPM（item7；<MIN_IOI_COUNT 个有效间隔 → None，统计不可信）。

    **口径修正（2026-09-10，BUG-1）**：两侧必须用**同量纲的音符级 onset**——
    用户侧 = ``librosa.onset_detect``（TrackF0.onsets_ms）；参考侧 = 提取期入库的
    ``pitch_ref.onsets_ms``（pyin-v2，经 slice_window 落盘）。
    v1 误把参考侧写成「LRC 逐句 start_ms 间隔」（秒级）：既是异量纲（用户侧百毫秒级），
    4~5s 的句间隔又会被 ``max_ioi_ms`` 全滤掉 → 参考侧恒 None → ``bpm_source`` 恒
    duration，特性形同虚设（复现/根因/验证见 worklog/BUG实测/）。

    [min_ioi, max_ioi] 过滤：短于 min 视为同一音的两次触发/颤音分裂，长于 max 视为
    长休止/空拍——两者都会把 IOI 中位带偏（半速/倍速混淆）。
    相邻 <``ONSET_DEDUPE_MS`` 的 onset 先合并（librosa 在强起音处会给出相邻重复帧）。
    """
    ev = _dedupe_onsets(onsets_ms)
    if len(ev) < MIN_IOI_COUNT + 1:
        return None
    diffs = np.diff(np.asarray(ev, dtype=float))
    keep = diffs[(diffs >= min_ioi_ms) & (diffs <= max_ioi_ms)]
    if keep.size < MIN_IOI_COUNT:
        return None
    ioi = float(np.median(keep))
    return 60000.0 / ioi


def _dedupe_onsets(onsets_ms, min_gap_ms: float = ONSET_DEDUPE_MS) -> list[float]:
    """相邻 <min_gap_ms 的 onset 合并（保留最早）——排序 + 去重（BUG-1 附带修复）。"""
    out: list[float] = []
    for t in sorted(float(v) for v in onsets_ms):
        if not out or t - out[-1] >= min_gap_ms:
            out.append(t)
    return out


def combine_bpm(
    b_flux: float | None,
    b_f0: float | None,
    approx_bpm: float | None,
    *,
    bpm_lo: float = BPM_FLOOR,
    bpm_hi: float = BPM_CEIL,
) -> tuple[float | None, str]:
    """**BPM 层仲裁**（2026-09-10 评估结论，见 scripts/poc/onset_eval.py 实测）：

    两路 onset 检测**互补**，谁都替代不了谁——频谱起音（librosa.onset_detect）精于
    "同音重复"（能量突变）但假点极多（合成评测 F1 0.36，断奏/连奏柔起音会**倍速事故**）；
    F0 起音（音高跳变 + 段起点）精于"连唱/柔起音/噪声"（F1 0.73）但**同音重复全漏**。

    规则（在 BPM 层仲裁——onset 列表层 union 实测更差）：
    1. 两路都不可用 → (None, "none")（调用方回落时长比）；
    2. 只有一路可用 → 该路 + **八度校正**；
    3. 两路可用且比值 ∈ [1.5, 2.3]（八度分歧/半速倍速）→ 取与 ``approx_bpm`` 更近者；
    4. 其余 → **F0 路**（假起音显著更少）。

    八度校正：在 ``bpm × 2^k``（k∈[-2,2] 且落在 [bpm_lo, bpm_hi]）中取与粗估最接近者。
    实测（BPM 误差均值）：频谱 51.8 → F0 4.8（同音重复场景为 None）→ **本函数 6.1 且无 None**；
    最差真实场景"同音重复"由 88.3 → 15.8。
    """
    if b_f0 is None and b_flux is None:
        return None, "none"
    if approx_bpm is not None and approx_bpm <= 0:
        approx_bpm = None

    def oct_correct(bpm: float | None) -> float | None:
        if not bpm or not approx_bpm:
            return bpm
        cands = [bpm * 2**k for k in (-2, -1, 0, 1, 2)]
        cands = [c for c in cands if bpm_lo <= c <= bpm_hi]
        return min(cands, key=lambda c: abs(c - approx_bpm)) if cands else bpm

    if b_f0 is None:
        return oct_correct(b_flux), "onset-flux"
    if b_flux is None:
        return oct_correct(b_f0), "onset-f0"
    hi, lo = max(b_f0, b_flux), min(b_f0, b_flux)
    if approx_bpm and lo > 0 and BPM_OCTAVE_LO <= hi / lo <= BPM_OCTAVE_HI:
        pick = b_flux if abs(b_flux - approx_bpm) < abs(b_f0 - approx_bpm) else b_f0
        return oct_correct(pick), "onset-arbitrated"
    return oct_correct(b_f0), "onset-f0"


def note_hit_rate(
    ref_f0: np.ndarray,
    user_f0: np.ndarray,
    *,
    path: list[tuple[int, int]] | None = None,
    tol_cent: float = NOTE_HIT_TOL_CENT,
    split_cent: float = NOTE_SPLIT_CENT,
    frames_ratio: float = NOTE_HIT_FRAMES_RATIO,
    shift_cent: float = 0.0,
) -> float | None:
    """**音符命中率**（口径 v4 · R2）：用户是否在**该唱这个音的时候**唱到了它。

    - 参考按"连续同音高段"切音符（相邻帧音高跳变 ≥``split_cent`` 视为新音符，清音断句）；
    - **时间映射**：优先用句级 DTW 路径（``path`` = [(user_idx, ref_idx), …]）——
      把参考音符帧映射到真正对齐的用户帧；无路径时回落按长度比例映射。
      （自测抓到：只用比例映射时，"整体慢 19%"的正常演唱句中音符错位 → 命中率假低）
    - 比较用**移调补偿 + 八度折叠后的 cent**（``shift_cent`` = v3 item5 的整体移调量）——
      否则"整体低 3 半音"的正常用户会被误判为没唱旋律（自测抓到）；
    - 命中门槛：该音符区间内 ≥``frames_ratio`` 的帧命中（短音符取绝对下限 2 帧）。
    - 返回 ``命中音符数 / 音符总数``；参考无音符 → None（调用方不判）。

    为什么需要它：逐句 DTW + 移调补偿 + 八度折叠能让**随机音高轨迹**（乱唱）得到
    50~65 的音准分——实测真机乱唱（attempt 16）命中率 0% 却拿 60.5/56.0。
    """
    ref = np.asarray(ref_f0, dtype=float)
    user = np.asarray(user_f0, dtype=float)
    if ref.size == 0 or user.size == 0:
        return None if ref.size == 0 else 0.0
    # 切音符：记录 (起帧, 止帧, 音高)
    notes: list[tuple[int, int, float]] = []
    cur = 0.0
    start = 0
    for i, v in enumerate(ref):
        if v <= 0:
            if cur > 0:
                notes.append((start, i, cur))
                cur = 0.0
            continue
        if cur <= 0:
            cur, start = float(v), i
        elif abs(1200.0 * float(np.log2(v / cur))) > split_cent:
            notes.append((start, i, cur))
            cur, start = float(v), i
    if cur > 0:
        notes.append((start, len(ref), cur))
    if not notes:
        return None
    # ref 帧索引 → user 帧索引列表（DTW 路径优先；无路径则按比例）
    ref_to_user: dict[int, list[int]] = {}
    if path:
        for ui, rj in path:
            if 0 <= rj < ref.size and 0 <= ui < user.size:
                ref_to_user.setdefault(rj, []).append(ui)
    scale = user.size / ref.size
    hit = 0
    for i0, i1, f in notes:
        idxs: list[int] = []
        for ri in range(i0, i1):
            if path:
                idxs.extend(ref_to_user.get(ri, ()))
            else:
                j = min(user.size - 1, int(ri * scale))
                idxs.append(j)
        if not idxs:
            continue
        seg = user[np.asarray(sorted(set(idxs)), dtype=int)]
        seg = seg[seg > 0]
        if seg.size == 0:
            continue
        cents = np.abs(_fold_cent(1200.0 * np.log2(np.maximum(seg, 1e-9) / f) - shift_cent))
        need = max(2, int(np.ceil(frames_ratio * len(seg))))
        if int((cents <= tol_cent).sum()) >= need:
            hit += 1
    return hit / len(notes)


def note_hit_factor(hit: float | None) -> float:
    """命中率 → **音准分衰减系数**（口径 v4 · R2；组长拍板 C：乘性衰减）。

    ``factor = NOTE_HIT_FACTOR_FLOOR + (1−FLOOR)×命中率``：
    - hit=0（完全没唱在调上，如乱唱）→ ×0.5；
    - hit=1（每个音符都唱到）→ ×1.0；
    - hit=None（参考句无音符）→ ×1.0（不判）。

    为什么不是"<阈值判 0/跳过"：命中率无法区分"跑调但认真的演唱"与"乱唱"（实测见
    ``local/hit_tol_scan.py`` 与 ``docs/audit``），硬阈值会把大量真实用户直接判"没唱"；
    连续衰减两边都降分，语义诚实且保留改进指引。
    """
    if hit is None:
        return 1.0
    h = min(max(float(hit), 0.0), 1.0)
    return round(NOTE_HIT_FACTOR_FLOOR + (1.0 - NOTE_HIT_FACTOR_FLOOR) * h, 4)


def onset_voiced_mask(
    f0: np.ndarray,
    rms: np.ndarray | None = None,
    *,
    rel: float = ONSET_VOICED_ENERGY_RELATIVE,
) -> np.ndarray:
    """帧级「有声」掩码（口径 v6）：**能量为主、F0 为辅**；无能量数据时回退 `f0 > 0`。

    为什么要换掉 `f0 > 0`（2026-09-10 复测实测，F1 的**真正主因**）：
    - librosa.pyin 的 voiced_flag 在本配置下对数字静音也大量判浊（37s 换气素材 1119 帧里
      只有 39 帧被判清音——2048 帧窗 =128ms 把 372ms 的换气"抹"掉大半）；
    - 再经 160ms 中值滤波（item6）后，一次 372ms 真实换气只剩 ~150-190ms 可检出，
      恰好卡在 `ONSET_SILENCE_GAP_MS=150ms` 的判据门槛上 → v5 的逐句起唱判据近乎恒判"延续"
      → **节奏维度在真实素材上要么恒 None、要么靠"窗口首帧恰好落在少数 0 帧"撞运气**；
    - 能量包络不受中值滤波影响、对换气（≥15dB 衰减）敏感，且提取期已算好（`track.rms`）。

    掩码 = `rms ≥ max(绝对下限, rel × 75 分位)` **且** `f0 > 0`（避免纯噪声段被判有声）。
    无 rms（Fake 提取器/单测直传 f0）→ 保持旧的 `f0 > 0` 语义，不影响既有断言。
    """
    arr = np.asarray(f0, dtype=float)
    if rms is None or len(rms) == 0 or arr.size == 0:
        return arr > 0
    e = np.asarray(rms, dtype=float)[: arr.size]
    if e.size < arr.size:
        e = np.pad(e, (0, arr.size - e.size))
    pos = e[e > 0]
    if pos.size == 0:
        return arr > 0
    thr = max(ONSET_ENERGY_MIN_RMS, float(rel) * float(np.percentile(pos, 75)))
    return (e >= thr) & (arr > 0)


def has_breath_structure(
    f0: np.ndarray,
    hop_ms: float,
    *,
    min_silence_ms: float = ONSET_SILENCE_GAP_MS,
    rms: np.ndarray | None = None,
) -> bool:
    """整轨是否存在 ≥``min_silence_ms`` 的静音段（换气/句间停顿）——口径 v4 · R1 判据。

    若不存在（有声段之间全是 <150ms 的零散断点）→ 用户**一口气唱到底**，
    "逐句起唱"这一概念不成立 → 该次演唱不给节奏分（rhythm=None，缺失降权）。

    为什么不用"句前 320ms 是否有声"：自测抓到，用户整体速度与参考差异大时
    （实测慢 18.9%），窗口映射会把句前 320ms 落到上一句尾音上 → **正常真唱被误杀**
    （6/6 句 rhythm=None）。整轨换气结构不受窗口错位影响：真唱有换气（✓ 正常评分），
    连续乱唱没有（✓ 不给节奏分）。真机乱唱实测：有声帧占比 80% 且无长静音。
    """
    arr = np.asarray(f0, dtype=float)
    if arr.size == 0:
        return False
    voiced = onset_voiced_mask(arr, rms)
    gap = max(1, int(round(min_silence_ms / (hop_ms or 32.0))))
    run = 0
    for v in voiced:
        if not v:
            run += 1
            if run >= gap:
                return True
        else:
            run = 0
    return False


def _user_coverage_conf(coverage: float | None) -> tuple[float, str | None]:
    """用户有效句覆盖率 → 综合分置信度（口径 v4 · R3；组长拍板"线性降权"）。

    - ≥80% → 1.0（全额）；
    - 40~80% → 线性 0.6 → 1.0（复用 item8 三段政策思路，斜率取缓：漏唱惩罚不压死分项）；
    - <40% → 0.0（**不给综合分**——与 docs/11 Q-B08「不伪造分数」同口径）。

    为什么需要它：真机反馈 2/6 有效句仍给综合 52.9（仅文案提示）；覆盖率低意味着
    "均分只代表少数句"，不能当作整首水平。
    """
    if coverage is None or coverage >= USER_COVERAGE_FULL:
        return 1.0, None
    if coverage >= USER_COVERAGE_LOW:
        conf = COVERAGE_CONF_FLOOR + (1.0 - COVERAGE_CONF_FLOOR) * (
            coverage - USER_COVERAGE_LOW
        ) / (USER_COVERAGE_FULL - USER_COVERAGE_LOW)
        conf = round(conf, 4)
        return conf, f"有效句覆盖 {coverage:.0%}（部分句未评测），综合分按置信度 {conf:.2f} 折算"
    return 0.0, f"有效句仅 {coverage:.0%}（<40%），不足以评分——请完整演唱一遍再评"


def window_scale(bpm_ratio: float | None) -> float:
    """句窗口缩放系数（BUG-4 修复 + 八度误判风险控制）。

    - ratio = user_bpm / ref_bpm（<1 = 用户更慢 → 句更长，scale > 1）；
    - **clamp 到 [WIN_RATIO_MIN, WIN_RATIO_MAX]**：ratio 若被八度误判（半速/倍速）会成倍
      拉长/缩短窗口 → 音准被拉歪，故超出可信域时按边界值处理；
    - 缺失/非法 → 1.0（不缩放，等价于修复前行为）。
    """
    try:
        ratio = float(bpm_ratio) if bpm_ratio else 1.0
    except (TypeError, ValueError):
        ratio = 1.0
    if ratio <= 0:
        ratio = 1.0
    ratio = min(max(ratio, WIN_RATIO_MIN), WIN_RATIO_MAX)
    return 1.0 / ratio


def bpm_ratio_info(
    user_onsets_ms,
    user_duration_ms: float,
    ref_onsets_ms,
    ref_duration_ms: float,
    *,
    user_f0_onsets_ms=None,
) -> dict:
    """真实 ``bpm_ratio``（item7，docs/06 §9.4 口径 v3；两侧同量纲音符级 onset）。

    - 两侧 onset 经 :func:`combine_bpm` 仲裁（F0 优先 + 八度校正；``user_f0_onsets_ms``
      为 None 时退化为"仅频谱起音"的既有行为，保证旧调用/旧数据兼容）；
    - ``ratio = user_bpm / ref_bpm``（与 v2 时长截断比同符号语义：>1 = 用户更快），
      夹到 [0.5, 2.0]（与 _coarse_bpm_ratio 同界）；
    - 任一侧不可用：回退时长截断比并标 ``bpm_source="duration"``——信息性字段的降级
      路径，绝不伪造节拍。

    参数口径（BUG-1 修正）：``ref_onsets_ms`` = 参考 ``pitch_ref.onsets_ms`` 拼接
    （提取期入库，pyin-v2），**不是** LRC 句起点（秒级句间隔与音符级 onset 不可比）。
    ``bpm_source`` 值域：``onset-f0`` / ``onset-flux`` / ``onset-arbitrated`` / ``duration``。
    """
    rb = bpm_from_onsets(list(ref_onsets_ms or []))
    b_flux = bpm_from_onsets(list(user_onsets_ms or []))
    b_f0 = bpm_from_onsets(list(user_f0_onsets_ms or [])) if user_f0_onsets_ms else None
    # 粗估（八度仲裁用）：参考 BPM × 用户/参考 时长比（速度比 ≈ 参考时长/用户时长）
    approx = None
    if rb and user_duration_ms and ref_duration_ms:
        approx = rb * (float(ref_duration_ms) / float(user_duration_ms))
    if user_f0_onsets_ms is None:
        ub, source = (b_flux, "onset-flux") if b_flux is not None else (None, "none")
    else:
        ub, source = combine_bpm(b_flux, b_f0, approx)
    if ub is not None and rb and rb > 0:
        ratio = min(max(ub / rb, 0.5), 2.0)
        return {
            "bpm_user": round(ub, 1),
            "bpm_ref": round(rb, 1),
            "bpm_source": source,
            "bpm_ratio": round(ratio, 4),
        }
    return {
        "bpm_user": None,
        "bpm_ref": None,
        "bpm_source": "duration",
        "bpm_ratio": _coarse_bpm_ratio(user_duration_ms, ref_duration_ms),
    }


def ref_coverage_of_lines(lines: list[LineScore]) -> float | None:
    """参考旋律完整性（item8）：(期望句数 − no_ref 句数) / 期望句数；无句 → None。"""
    if not lines:
        return None
    missing = sum(1 for line in lines if line.no_ref)
    return (len(lines) - missing) / len(lines)


def _pitch_weight_policy(coverage: float | None) -> tuple[float, str, str | None]:
    """三段式动态权重（item8，docs/06 §9.4 口径 v3；组长拍板）：

    - 覆盖 ≥80% → 全额  0.5（与 docs/06 §9.4 综合公式一致）；
    - 40~80%  → 线性 0.5→0.2（参考缺失越多，音准信号越不可信）；
    - <40%    → 0.0（音准**不计入综合**，仅展示——缺失过半时硬算等于伪造置信度）。

    返回 (weight, reliability, note)；note 为前端可展示文案。
    """
    if coverage is None or coverage >= REF_COVERAGE_FULL:
        return PITCH_WEIGHT_FULL, "full", None
    if coverage >= REF_COVERAGE_LOW:
        wp = PITCH_WEIGHT_FLOOR + (coverage - REF_COVERAGE_LOW) / (
            REF_COVERAGE_FULL - REF_COVERAGE_LOW
        ) * (PITCH_WEIGHT_FULL - PITCH_WEIGHT_FLOOR)
        wp = round(wp, 4)
        note = (
            f"参考旋律覆盖 {coverage:.0%}（部分句缺失），音准权重降至 {wp:.2f}，"
            "分数仅供参考——补齐参考（重新提取）后可重唱更准。"
        )
        return wp, "reduced", note
    note = (
        f"参考旋律仅覆盖 {coverage:.0%}，音准不可信、不计入综合分（仅展示）；"
        "请等待参考旋律重新提取后重唱。"
    )
    return 0.0, "low", note


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


def _fold_cent_matrix(
    user_win: np.ndarray, ref_win: np.ndarray, shift_cent: float = 0.0
) -> np.ndarray:
    """句级帧对成本矩阵：|折叠(cent 差) − shift_cent|（八度等价 + 口径 v3 整体移调）。

    清音帧对（任一侧无声）→ 固定成本 ``SILENT_FRAME_COST``：既不让 DTW 把静音当"免费
    对齐点"（成本 0 会诱使路径穿过静音段），也不至于完全无法跨越。
    ``shift_cent`` 为整体移调量（item5）：只平移比较基准，绝对折叠差保持为 DTW 目标
    （与 v2 踩坑记录的同一原则——DTO 目标必须与评分目标同尺度同基准）。
    """
    u = np.asarray(user_win, dtype=float)[:, None]
    r = np.asarray(ref_win, dtype=float)[None, :]
    cents = 1200.0 * np.log2(np.maximum(u, 1e-9) / np.maximum(r, 1e-9))
    cost = np.abs(_fold_cent(cents - shift_cent))
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


def global_dtw_step(n: int) -> int:
    """整首粗对齐的降采样步长（P1-11）：≤4000 帧不降采样，否则压到 ~2000 帧量级。

    180s@32ms = 5625 帧 → 2；300s = 9375 帧 → 5。返回值同时是 offset 的量化单位
    （``hop_ms × step``），故测试与调用方都直接依赖它。
    """
    if n <= GLOBAL_DTW_FULL_FRAMES:
        return 1
    return max(1, math.ceil(n / GLOBAL_DTW_TARGET_FRAMES))


def _fit_stretch(js: np.ndarray, iis: np.ndarray) -> float:
    """从 DTW 路径稳健估计全局拉伸（用户帧/参考帧）。

    为什么不做全路径最小二乘：`_dtw_path` 的成本是 |cent 差|，在**恒定音高段**里成本恒 0，
    路径可零代价横向漂移（恒等输入实测拟合出 1.05 → 截距偏 1 帧、旧断言 `|offset| ≤ 1 帧` 立刻红）。
    改为**分段 delta 中位数回归**：按参考轴等分若干段，各段取 (i−j) 中位数，再对段中心回归斜率
    （等价于"分段弯折"的整体斜率，对局部漂移与离群稳健）。
    """
    if js.size < 16:
        return 1.0
    delta = iis - js
    segments = max(4, min(16, js.size // 8))
    edges = np.linspace(float(js.min()), float(js.max()), segments + 1)
    xs: list[float] = []
    ys: list[float] = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (js >= lo) & ((js <= hi) if hi == edges[-1] else (js < hi))
        if int(m.sum()) >= 3:
            xs.append(float(np.median(js[m])))
            ys.append(float(np.median(delta[m])))
    if len(xs) < 3:
        return 1.0
    var_x = float(np.var(np.asarray(xs)))
    if var_x <= 0:
        return 1.0
    slope_of_delta = float(np.cov(np.asarray(xs), np.asarray(ys), bias=True)[0, 1] / var_x)
    return 1.0 + slope_of_delta


@dataclass(frozen=True)
class TimeWarp:
    """整首时间弯折映射（口径 v6 · F1 修复）：``user_ms ≈ offset_ms + stretch × ref_ms``。

    为什么需要它（2026-09-10 复测 F1）：旧实现把参考句窗映射到用户时间轴时**只缩放句长**
    （`win_end = win_start + len × scale`），**起点只加一个全局中位偏移** `ref_start + offset_ms`。
    用户唱得比参考慢（`bpm_ratio < 1`）时 `offset_ms`（DTW 路径 delta 中位数）在曲首偏大、曲尾偏小
    → 后续句窗口落到**上一句句腹**（无前置静音）→ `onset_is_continuation` 只能判"延续" →
    整首 `reason='no_onset'`、节奏维度为 None（`overall` 静默按 0.5/0.3 重算）。
    容器实测：`bpm_ratio=0.826` 的素材即使句间有 372ms 换气也 6/6 句 no_onset；PG 历史 26 条
    attempt 中 `ratio<1` 的**全部**没有节奏分，`ratio>1` 的都有（窗口起点偏早 → 恰好落进静音 →
    误打误撞能检出）。

    v6 的两条配套（缺一不可）：
    1. **本映射**：起点与长度同源（`offset + stretch × ref`），斜率用分段中位回归稳健估计（见
       :func:`_fit_stretch`）+ 吸附 + clamp；
    2. **起唱检测窗外扩**（``TIME_WARP_WINDOW_PAD_MS``）：真人换气让"慢"逐句累积，任何单条直线的
       映射都会在曲尾累积误差——故检测窗放宽，让"静音→有声"跳变仍落在窗内（评分窗保持收窄）。
    """

    stretch: float
    offset_ms: float
    ratio: float

    def to_user_ms(self, ref_ms: float) -> float:
        """参考时刻 → 用户时刻（时间弯折；stretch>1 = 用户更慢）。"""
        return self.offset_ms + self.stretch * ref_ms


def align_time_warp(
    user_f0: np.ndarray,
    ref_f0: np.ndarray,
    hop_ms: float,
    *,
    tempo_ratio: float | None = None,
) -> TimeWarp:
    """整首对齐 + 时间弯折参数（v6）：返回 :class:`TimeWarp`。

    拉伸系数来源（**onset 仲裁为主、路径拟合兜底，且必须互证**）：
    - `tempo_ratio`（item7 的 `bpm_ratio` = 用户/参考 BPM，两路 onset 在 BPM 层仲裁所得）有效
      **且与路径拟合值相差 ≤ ``TIME_WARP_AGREE_TOL``** 时，取 `window_scale(tempo_ratio)`。
      它独立于整首 DTW 的 Sakoe-Chiba 带（带只有 ±10%，而"偏慢 + 每句换气"的累积形变可远超
      带宽：容器实测 1.19× 慢 + 5 次换气 → 拟合斜率被压到 1.10），故更接近真实速度；
      但**单独使用不安全**——纯音/onset 紊乱的素材上它会给到 clamp 边界，把窗口推出曲外。
    - 否则用 DTW 路径稳健拟合斜率（:func:`_fit_stretch`）——受带宽约束（偏保守），但稳定。

    不可对齐（帧数不足/无有效帧）→ 恒等弯折 ``(stretch=1, offset=0)``，调用方按不可对齐降权，
    不伪造（docs/11 Q-B08 同口径）。
    """
    n = min(len(user_f0), len(ref_f0))
    if n < 8:
        return TimeWarp(1.0, 0.0, 1.0)
    u = np.asarray(user_f0[:n], dtype=float)
    r = np.asarray(ref_f0[:n], dtype=float)
    if ((u > 0) & (r > 0)).sum() < 8:
        return TimeWarp(1.0, 0.0, 1.0)
    uu = _hz_to_series_cent(u, r)
    rbg = r[r > 0]
    if len(rbg) == 0:
        return TimeWarp(1.0, 0.0, 1.0)
    rmed = float(np.median(rbg))
    rr = 1200.0 * np.log2(np.maximum(r, 1e-9) / rmed)
    uu = np.where(np.isfinite(uu), uu, 0.0)
    rr = np.where(np.isfinite(rr), rr, 0.0)

    # 长歌护栏（P1-11 修复）：按"目标帧数"自适应降采样。
    # 旧实现 `if n > 6000: step = 2` 是**死代码**——180s@32ms = 5625 帧永远够不着 6000，
    # 即"允许的最长歌"100% 走全分辨率路径：成本矩阵 + 累积矩阵各 n²×8B（5625² ≈ 253MB ×2
    # ≈ 0.5GB），带内又是纯 Python 双层循环（≈2·w·n ≈ 630 万次）→ 实测 **48.7s / 0.5GB**；
    # `sing_concurrency=2` 下两首并发 ≈1GB，容器 2GB 还要装 whisper，有 OOM 风险（拷问报告 P1-11）。
    # 现：n ≤ 4000 不降采样（60~120s 歌不受影响，offset 保持 1 帧粒度）；否则 step = ceil(n/3000)
    # → 180s 取 step=2（2813 帧：矩阵 ≈127MB、带内 ≈158 万次 ≈ 8.7s 实测）；
    # 代价 = 映射量化到 hop×step（32ms×2 = 64ms）——远小于节奏分档阈值（150/300/600ms）。
    step = global_dtw_step(n)
    if step > 1:
        uu = uu[::step]
        rr = rr[::step]
        n = len(uu)

    path = _dtw_path(uu, rr, DTW_BAND_RATIO, open_end=True)
    ratio = _coarse_bpm_ratio(n * hop_ms * step, len(ref_f0) * hop_ms)
    if not path:
        return TimeWarp(1.0, 0.0, ratio)
    ms = hop_ms * step
    pairs = np.asarray(path, dtype=float)
    # 只用**用户侧有声**的路径点估计斜率/截距：静音↔有声的对齐成本高、路径在静音段是任意的
    # （实测：不过滤时"句间换气"会被拟合成虚假的额外拉伸，斜率偏低 → 期望位置整体漂移）
    voiced_pairs = uu[pairs[:, 0].astype(int)] > 0
    if int(voiced_pairs.sum()) >= 16:
        pairs = pairs[voiced_pairs]
    js = pairs[:, 1]  # 参考帧
    iis = pairs[:, 0]  # 用户帧
    # 兜底来源：DTW 路径稳健分段回归（:func:`_fit_stretch`）→ 吸附（±3%）→ clamp
    slope = _fit_stretch(js, iis)
    if abs(slope - 1.0) <= TIME_WARP_SNAP_BAND:
        slope = 1.0
    fitted = min(max(slope, TIME_WARP_STRETCH_MIN), TIME_WARP_STRETCH_MAX)
    # 优先来源：onset 仲裁的真实速度比（item7）——但**必须与路径拟合互证**：合成纯音等
    # "onset 不可靠"的素材上 onset 比值会离谱（实测给到 clamp 边界 1.49，窗口被推出曲外），
    # 两来源相差超过 ``TIME_WARP_AGREE_TOL`` 时取保守的路径拟合值。
    stretch = fitted
    onset_stretch = window_scale(tempo_ratio) if tempo_ratio else None
    if onset_stretch is not None and abs(onset_stretch - fitted) <= TIME_WARP_AGREE_TOL:
        stretch = min(max(onset_stretch, TIME_WARP_STRETCH_MIN), TIME_WARP_STRETCH_MAX)
    # 截距 = 按已定的拉伸取残差中位数（起点偏移，前端曲线平移口径）
    offset_ms = float(np.median(iis - stretch * js) * ms)
    return TimeWarp(
        stretch=round(stretch, 4),
        offset_ms=offset_ms,
        ratio=ratio,
    )


def align_frames(user_f0: np.ndarray, ref_f0: np.ndarray, hop_ms: float) -> tuple[float, float]:
    """整首对齐（兼容旧签名）：返回 (时长比, 起点偏移 ms)。

    语义（v2 修正 → v6 收敛）：**用户时间轴 ≈ 起点偏移 + stretch × 参考时间轴**；
    `offset_ms` = 截距（起点处偏移），与前端「曲线平移量」口径一致。
    需要逐句端点映射时用 :func:`align_time_warp`（本函数是它的标量摘要）。
    """
    warp = align_time_warp(user_f0, ref_f0, hop_ms)
    return warp.ratio, warp.offset_ms


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


def onset_is_continuation(
    track_f0: np.ndarray,
    frame_start: int,
    hop_ms: float,
    track_rms: np.ndarray | None = None,
) -> bool:
    """句窗首帧是否落在「窗口前 ≥``ONSET_SILENCE_GAP_MS`` 已开始的有声段」内（＝**延续**）。

    口径 v5 · R1 的**逐句**判据（2026-09-10 P0 修复）。返回 True 表示该句窗口内**没有新起唱**
    （上一句尾音拖过来 / 一口气唱到底）→ 调用方把该句 `rhythm_score=None`（不计分，也不写
    `onset_dev_ms=0`），reason 记 `no_onset`。

    为什么替换 v4 的整轨判据（:func:`has_breath_structure`）：
    - 整轨判据只要**任意一处** ≥150ms 静音即为真——手机录音起始那 1s 静音几乎必然满足，
      于是闸门形同虚设；
    - 而 :func:`_first_new_run` 对"窗口第 0 帧已有声"直接 `return 0` → `onset_dev=0` →
      `rhythm_score_from_dev(0)=95`：**乱唱/完全不跟拍恒得节奏 95**（v4 想修的真机 52.9 事件
      在常见录音形态下复活，见 `local/唱歌模块全链路拷问报告-2026-09-10.md` §1 Top 3）。
    逐句判据只回答"这句是不是新起唱"，与录音起始静音/前奏无关。
    口径 v6（2026-09-10 复测）："有声"改由 :func:`onset_voiced_mask`（能量为主）判定——
    只看 `f0 > 0` 会让本函数近乎恒真（pyin 对静音大量判浊，见该函数说明）。
    依据：docs/06 §9.4（口径 v5/v6）、docs/21 §3.6。
    """
    arr = np.asarray(track_f0, dtype=float)
    if arr.size == 0 or frame_start <= 0 or frame_start >= arr.size:
        return False
    voiced = onset_voiced_mask(arr, track_rms)
    if not voiced[frame_start]:  # 窗口首帧无声 → 不是"延续"，交给起唱检测正常定位
        return False
    gap = max(1, int(round(ONSET_SILENCE_GAP_MS / (hop_ms or 32.0))))
    return bool(np.any(voiced[max(0, frame_start - gap) : frame_start]))


def line_onset_ms(
    onset_win_f0: np.ndarray,
    onset_win_rms: np.ndarray | None,
    track_f0: np.ndarray,
    frame_start: int,
    hop_ms: float,
    track_rms: np.ndarray | None = None,
) -> float | None:
    """句窗内「新起唱」时刻（相对**检测窗**起点，ms）；None = 该句无新起唱。

    口径 v6（2026-09-10 F1 复测修复）——v5 的判据只看**窗口首帧**，速度模型一旦把窗口起点
    挪进上一句句腹，即使窗口内后半段有明确换气也一律判"延续"（偏慢演唱整首无节奏分的根因）；
    现按两步判：

    1. 检测窗内**向内扫**"跳过开头有声段"后的第一个「前置静音 ≥150ms + 连续有声」段起点
       （`onset > 0`）：说明窗口后半段确实发生了「换气→再起唱」→ 该句有新起唱（v5 漏掉的情形）；
    2. 窗口内没有这种跳变时，只有"窗口第 0 帧有声**且**窗口前 150ms 是静音"才算起唱落在窗口起点
       （`onset_is_continuation` 为假）——否则就是 v5 要拦的形态：窗口第 0 帧已在上一句尾音里
       （一口气唱到底 / 乱唱）→ 返回 None（不给节奏分）。

    注意：起唱时刻相对**检测窗**起点；偏差由调用方对"时间弯折的期望位置"计算，
    不得对窗口起点计算（否则窗口外扩会把偏差人为归零 —— 那是自证式打分）。
    """
    onset = detect_onset_ms(onset_win_f0, onset_win_rms, hop_ms)
    if onset is not None and onset > 0:
        return onset
    # `detect_onset_ms` 对"窗口第 0 帧已有声"直接返回 0（`_first_new_run` 的短路），速度模型把窗口
    # 起点挪进句腹时它便不再看窗口后半段——故这里**再向内扫一遍**（跳过开头有声段）。
    # 有声判定用能量掩码（v6）：只看 `f0 > 0` 时 pyin 对换气大量判浊，扫描同样找不到跳变。
    voiced = onset_voiced_mask(onset_win_f0, onset_win_rms)
    gap = max(1, int(round(ONSET_SILENCE_GAP_MS / (hop_ms or 32.0))))
    n = len(voiced)
    i = 0
    while i < n and voiced[i]:
        i += 1
    while i < n:
        if not voiced[i]:
            i += 1
            continue
        start = i
        while i < n and voiced[i]:
            i += 1
        if i - start >= ONSET_MIN_RUN_FRAMES and not voiced[max(0, start - gap) : start].any():
            return float(start * hop_ms)
    if onset == 0 and not onset_is_continuation(track_f0, frame_start, hop_ms, track_rms):
        return 0.0
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

    **口径 v4（R1）在前置层拦截**：整轨若没有换气结构（:func:`has_breath_structure` 为假，
    如"一口气唱到底"的连续乱唱），调用方**不调用本函数**（该句 rhythm=None）——
    因为此时"窗口第 0 帧就有声"会被误判成"精准起唱"（修复前乱唱恒得 95 分）。
    """
    voiced = onset_voiced_mask(user_f0, rms)
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
    shift_cent: float = 0.0,
) -> tuple[float, list[tuple[int, int]]]:
    """句级局部 DTW：返回 (offset_frames, path)。

    offset_frames = 路径 (user_idx - ref_idx) 的中位数（>0 = 该句用户落后参考）。

    成本 = **绝对折叠 cent 差**（平移 ``shift_cent`` 后）的帧对矩阵
    （:func:`_fold_cent_matrix`）——八度等价 + 口径 v3 整体移调（item5），
    且与最终音准评分同尺度（不做"各自中位归一化"：那会给两条序列引入不同的基准偏移，
    使 DTW 目标与评分目标不一致）。

    **BUG-4 修正（2026-09-10）**：不再 ``n = min(len(u), len(r))`` 按短侧截断——
    用户整体速度与参考不同时（句窗口已按 `bpm_ratio` 缩放，见 PyinSingScorer），
    两侧长度本就不同（实测慢 18.9% → 用户句长 ≈1.19×参考句），截断会把**用户句尾
    整段丢掉**、使 DTW 只能在残缺序列上对齐 → 音准被低估（实测 pitch 78 vs 修复后 ≈95）。
    代价：成本矩阵 O(n·m)（句级 155×185 ≈ 2.9 万格，可承受）。
    """
    u = np.asarray(user_win_f0, dtype=float)
    r = np.asarray(ref_win_f0, dtype=float)
    if len(u) < 3 or len(r) < 3:
        return 0.0, []
    cost = _fold_cent_matrix(u, r, shift_cent)
    path = _dtw_path_cost(cost, band_ratio, open_end=False)
    if not path:
        return 0.0, []
    deltas = [pi - pj for pi, pj in path]
    return float(np.median(deltas)), path


def aligned_cent_deviation(
    user_win_f0: np.ndarray,
    ref_win_f0: np.ndarray,
    path: list[tuple[int, int]],
    shift_cent: float = 0.0,
) -> tuple[float | None, int]:
    """按 DTW 路径对齐后比较 cent（整体移调 shift_cent 后）：返回 (|cent| 中位数, 有效帧对数)。

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
            cents.append(float(_fold_cent(1200.0 * np.log2(ratio) - shift_cent)))
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
    # v4：该句起唱偏差（ms，相对「LRC 时间戳 + 整首对齐偏移」；None = 未检出/句前已在发声）
    onset_dev_ms: float | None = None
    # v4（R2）：音符命中率（用户是否唱到参考句的各音符；None = 参考无音符）
    note_hit_rate: float | None = None
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
    alignment: dict = field(default_factory=dict)  # {bpm_ratio, offset_ms, method, version, ...}
    is_complete: bool = False
    expected_lines: int = 0
    evaluated_lines: int = 0
    # 口径 v3 · item8：参考完整性驱动的动态权重（service 重聚合发音时复用同一权重）
    ref_coverage: float | None = None
    pitch_weight: float | None = None
    pitch_reliability: str | None = None
    weight_note: str | None = None
    # 口径 v4 · R3：用户有效句覆盖率 → 综合分置信度（service 重聚合时复用）
    user_coverage: float | None = None
    coverage_conf: float | None = None
    coverage_note: str | None = None
    # 口径 v4 · R2：整首音符命中率（有效句命中率均分；None = 无可用句）
    note_hit_rate: float | None = None


def aggregate_result(lines: list[LineScore]) -> SingScoreResult:
    """聚合（D5 缺失降权：skipped 句不入分项均分；overall = wp·音准+0.2·节奏+0.3·发音）。

    - pitch/rhythm = 有效句（非 skipped 且有该分项）均分；
    - pron = 抽样句 pron_score 均分（未抽样句 None，不进组合）；
    - **口径 v3 · item8**：音准权重 wp 由参考完整性三段政策决定
      （:func:`_pitch_weight_policy`：≥80% 全额 / 40~80% 线性 0.5→0.2 / <40% 不计入）；
    - **口径 v4 · R3**：综合分再乘"用户有效句覆盖率置信度"（:func:`_user_coverage_conf`：
      ≥80% 全额 / 40~80% 线性 0.6→1.0 / <40% → 0 即**不给综合分**）；**v5.1（P1-10）起
      覆盖率分母只算"有参考的句"**（`no_ref` 句属服务端参考缺失，不进分母，见下）；
    - 分项缺失按剩余权重归一，全部缺失 → None（不伪造分数）。
    """
    valid = [line for line in lines if not line.skipped]
    expected = len(lines)
    pitches = [line.pitch_score for line in valid if line.pitch_score is not None]
    rhythms = [line.rhythm_score for line in valid if line.rhythm_score is not None]
    prons = [line.pron_score for line in valid if line.pron_score is not None]
    hits = [line.note_hit_rate for line in valid if line.note_hit_rate is not None]
    pitch = _mean(pitches)
    rhythm = _mean(rhythms)
    pron = _mean(prons)
    coverage = ref_coverage_of_lines(lines)
    wp, reliability, note = _pitch_weight_policy(coverage)
    # 口径 v5.1（2026-09-10 · P1-10 修复）：R3 的**分母只统计有参考的句**（排除 no_ref）。
    # 理由：no_ref 句是**服务端参考旋律缺失**（用户再努力也拿不到该句分），旧分母把
    # `len(valid)/expected`（expected 含 no_ref）→ 参考缺失被**二次惩罚**（item8 已按
    # ref_coverage 降 wp），且 note 会写「请完整演唱一遍再评」把服务端问题甩给用户
    # （拷问报告 B-F5；实测：6 句里 1 句有参考且用户唱全 → user_coverage=0.167 → 不给综合分）。
    # 现分母 = 有参考句数；全为 no_ref 时 user_cov=None（不惩罚，由 item8 的 weight_note 说明）。
    # 依据：docs/06 §9.4（v4 R3 / item8 分工）、docs/21 §3.6。
    scorable = [line for line in lines if not line.no_ref]
    user_cov = (len(valid) / len(scorable)) if scorable else None
    conf, cov_note = _user_coverage_conf(user_cov)
    weighted = _weighted_overall(pitch, rhythm, pron, wp, 0.2, 0.3)
    overall = None if (weighted is None or conf <= 0) else round(weighted * conf, 2)
    return SingScoreResult(
        lines=lines,
        overall=overall,
        pitch=pitch,
        rhythm=rhythm,
        pron=pron,
        is_complete=bool(expected > 0 and len(valid) >= math_ceil(expected * 0.8)),
        expected_lines=expected,
        evaluated_lines=len(valid),
        ref_coverage=coverage,
        pitch_weight=wp,
        pitch_reliability=reliability,
        weight_note=note,
        user_coverage=user_cov,
        coverage_conf=conf,
        coverage_note=cov_note,
        note_hit_rate=_mean(hits) if hits else None,
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
    """真实评分器：pyin 用户 F0 → 中值滤波 → 整体移调 → 整首对齐 → 逐句局部对齐 → 映射。

    管线（docs/06 §9.4 口径 v3；顺序有依赖：先滤波（item6）→ 再统计移调（item5，
    滤波后中位更干净）→ 逐句比较（注入 shift）→ 聚合（item8 动态权重））。
    """

    def score_sync(self, user_wav_path: str, ref_lines: list[dict]) -> SingScoreResult:
        from dataclasses import replace

        from app.audio.pitch import get_pitch_extractor, slice_window

        track = get_pitch_extractor().extract_track(user_wav_path)
        hop = track.hop_ms or 32.0
        ref_arrays = [
            {
                "seq": int(line["seq"]),
                "start_ms": int(line["start_ms"]),
                "end_ms": int(line["end_ms"]),
                "f0s": np.asarray(line["pitch_ref"].get("f0s") or [], dtype=float),
                # 参考音符级 onset（pyin-v2 入库）——item7 参考侧数据源；
                # 旧世代（pyin-v1）无此键 → 空列表 → bpm_source 诚实回落 duration
                "onsets": [float(v) for v in (line["pitch_ref"].get("onsets_ms") or [])],
                "text": line.get("text") or "",
            }
            for line in ref_lines
        ]
        ref_full = np.concatenate([a["f0s"] for a in ref_arrays]) if ref_arrays else np.array([])
        user_f0_raw = np.asarray(track.f0, dtype=float)
        user_rms = np.asarray(track.rms, dtype=float) if track.rms else None

        # item6（docs/06 §9.4 口径 v3）：中值滤波——仅用户侧（参考为合成音无颤音，
        # SG-13 素材物化）；0 帧保持 0（不跨静音）。评分分支用滤波后，落库仍存原始帧（D4 保真）
        user_f0 = median_filter_f0(user_f0_raw, MEDFILT_KERNEL)
        track_f = replace(track, f0=[float(v) for v in user_f0])

        # item5：整首移调（整数半音，统计全曲中位）→ 注入全部帧级比较 + 音域提示
        shift_st = estimate_transpose_semitones(user_f0, ref_full)
        shift_cent = float(shift_st * 100.0)
        range_hint = range_hint_text(shift_st)

        # item7：真实 BPM（两路 onset 仲裁：用户 F0 起音 + 频谱起音；参考侧入库 onsets_ms）
        ref_onsets_ms = sorted({t for a in ref_arrays for t in a["onsets"]})
        tempo = bpm_ratio_info(
            track.onsets_ms or [],
            float(len(user_f0)) * hop,
            ref_onsets_ms,
            float(len(ref_full)) * hop,
            user_f0_onsets_ms=track.f0_onsets_ms or None,
        )
        # 整首对齐 + 时间弯折（v6 · F1）：用户时间轴 ≈ offset₀ + stretch × 参考时间轴，
        # 且句窗端点由 DTW 路径**逐句**映射（真人换气使"慢"逐句累积，非线性）
        warp = align_time_warp(user_f0, ref_full, hop, tempo_ratio=tempo["bpm_ratio"])
        offset_ms = warp.offset_ms
        # v4 · R1（**v5 起降为留痕诊断，不再作判据**）：整轨是否有换气结构（≥150ms 静音段）。
        # 判据本身已下沉到逐句（onset_is_continuation），此值仅随 alignment 落库供抽检/复盘。
        breath_ok = has_breath_structure(user_f0, hop, rms=user_rms)

        lines: list[LineScore] = []
        window_records: list[list[float]] = []
        for a in ref_arrays:
            ref_win = a["f0s"]
            if len(ref_win) == 0 or not np.any(ref_win > 0):
                lines.append(_skipped_line(a, "no_ref", no_ref=True))
                continue
            # 参考句窗映射到用户时间轴（v6 · 时间弯折：起点与长度同源）
            #
            # BUG-4（2026-09-10）：窗口**按速度比缩放句长**（用户慢 → 句更长），否则用户句尾
            # 被窗口截断、DTW 在残缺窗口内对齐 → 音准被低估（实测慢 18.9% 时 pitch 78 vs ≈95）。
            # F1（2026-09-10 复测修复）：**起点也必须弯折**——旧实现 `ref_start + offset_ms`
            # 只加"全局中位偏移"，用户偏慢时后续句窗口落到上一句句腹 → 起唱判据恒"延续" →
            # 整首无节奏分（容器实测 ratio=0.826 素材 6/6 句 no_onset，即使句间有 372ms 换气）。
            win_start = warp.to_user_ms(a["start_ms"])
            win_end = warp.to_user_ms(a["end_ms"])
            if win_end - win_start < 1.0:  # 路径退化/参考句长≈0 → 按拉伸后的句长兜底
                win_end = win_start + max(1.0, (a["end_ms"] - a["start_ms"]) * warp.stretch)
            window_records.append([a["seq"], round(win_start, 1), round(win_end, 1)])
            window = slice_window(track_f, win_start, win_end)
            user_win = np.asarray(window["f0s"], dtype=float)
            # 音准（B2 + item5）：逐句局部 DTW（成本含整体移调）→ 对齐后 cent 中位
            _off_frames, path = local_align(user_win, ref_win, shift_cent=shift_cent)
            cent, n_pairs = aligned_cent_deviation(user_win, ref_win, path, shift_cent)
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
                        # D4 原始帧（未滤波）落库——评分分支才用滤波后序列
                        user_f0=_f0_pairs(_raw_win(track, window), win_start, hop),
                    )
                )
                continue
            # 口径 v4 · R2：音符命中率 → **音准分乘性衰减**（"有没有唱在参考旋律上"）
            # （乱唱/滑音能被 DTW 贴靠得 50~65 分；真机实测命中率 0~17% vs 音准 58~60）
            # 时间映射用句级 DTW 路径（比例映射在"整体速度差大"时会错位，自测抓到）；
            # 比较口径与音准一致：移调补偿（shift_cent）+ 八度折叠
            hit = note_hit_rate(ref_win, user_win, path=path, shift_cent=shift_cent)
            pitch = pitch_score_from_cent(cent) * note_hit_factor(hit)
            # 节奏（A3 + v4 R1 → v5 逐句判据 → **v6 检测窗外扩**）：
            # 起唱时刻 vs **时间弯折的期望位置**。
            # v5（2026-09-10 P0 修复）：句窗首帧若落在「窗口前 ≥150ms 已开始的有声段」内
            # （＝延续上一句 / 一口气唱到底）→ 该句**无新起唱**：onset_dev=None、rhythm=None，
            # reason 记 no_onset；不再走 `_first_new_run` 的 `start == 0 → 0ms → 95 分` 分支。
            # v6（2026-09-10 复测 F1）：判据改为在**外扩后的检测窗**里找"换气→再起唱"跳变
            # （见 :func:`line_onset_ms`），并把偏差对**期望位置**而非窗口起点计算——
            # 否则速度模型的累积误差会把整个节奏维度吃掉（偏慢整首 None）。
            # 依据：docs/06 §9.4（口径 v5/v6）、docs/21 §3.6。
            # 传入**滤波后**的整轨序列（与评分分支同源）；frame_start 是它在句窗内的起点索引。
            pad = TIME_WARP_WINDOW_PAD_MS
            onset_start_ms = max(0.0, win_start - pad)
            onset_window = slice_window(track_f, onset_start_ms, win_end + pad)
            onset_win = np.asarray(onset_window["f0s"], dtype=float)
            onset_win_rms = (
                user_rms[onset_window["frame_start"] : onset_window["frame_end"]]
                if user_rms is not None and len(user_rms)
                else None
            )
            onset_rel = line_onset_ms(
                onset_win,
                onset_win_rms,
                user_f0,
                int(onset_window["frame_start"]),
                hop,
                user_rms,
            )
            # 期望起唱 = LRC 起点经时间弯折映射的用户时刻；偏差 = 实测起唱 − 期望（v6）
            expected_onset_ms = win_start
            onset_dev = (
                abs((onset_start_ms + onset_rel) - expected_onset_ms)
                if onset_rel is not None
                else None
            )
            rhythm_continuation = onset_rel is None
            rhythm = rhythm_score_from_dev(onset_dev) if onset_dev is not None else None
            # 帧级折叠 cent 偏差（D3 图；按路径映射后落到参考帧索引；含整体移调口径）
            cent_dev = _path_cent_series(user_win, ref_win, path, shift_cent)
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
                    # v5：非 skipped 行的 reason 表示「该句部分维度未计分的原因」
                    # （当前仅 no_onset：句窗内无新起唱 → 节奏不计分；音准/发音照常）
                    reason="no_onset" if rhythm_continuation else None,
                    onset_dev_ms=round(onset_dev, 1) if onset_dev is not None else None,
                    note_hit_rate=round(hit, 3) if hit is not None else None,
                    user_f0=_f0_pairs(_raw_win(track, window), win_start, hop),
                    cent_dev=cent_dev,
                )
            )
        result = aggregate_result(lines)
        result.alignment = {
            # item7：真实 BPM（onset 间隔；bpm_source=duration 时长比回退）
            "bpm_ratio": tempo["bpm_ratio"],
            "bpm_user": tempo["bpm_user"],
            "bpm_ref": tempo["bpm_ref"],
            "bpm_source": tempo["bpm_source"],
            "offset_ms": round(offset_ms, 1),
            # v6 · F1：时间弯折留痕（stretch = 用户时间/参考时间，>1 = 用户更慢）+
            # 逐句用户时间轴窗口（发音抽样/图表/排障共用同一份映射，避免口径分叉）
            "time_warp_stretch": warp.stretch,
            "windows_ms": window_records,
            "method": ALIGN_METHOD,
            "version": SCORING_VERSION,
            # item5/6：移调与滤波留痕（audit：分数版本内可解释）
            "transpose_semitones": shift_st,
            "range_hint": range_hint,
            "medfilt_kernel": MEDFILT_KERNEL,
            # item8：参考完整性 → 动态权重（前端标注"分数仅供参考"）
            "ref_coverage": result.ref_coverage,
            "pitch_weight": result.pitch_weight,
            "pitch_reliability": result.pitch_reliability,
            "weight_note": result.weight_note,
            # v4 · R2/R3：音符命中率 + 有效句覆盖率置信度（前端"不足以评分"标注）
            "note_hit_rate": result.note_hit_rate,
            "user_coverage": result.user_coverage,
            "coverage_conf": result.coverage_conf,
            "coverage_note": result.coverage_note,
            # v5 · R1 留痕：整轨换气结构（诊断用；判据已下沉逐句，见 onset_is_continuation）
            "breath_structure": breath_ok,
        }
        return result


def _raw_win(track, window: dict) -> np.ndarray:
    """与评分窗口同帧索引的**原始帧**（未中值滤波；D4 落库保真，docs/06 §9.4 口径 v3 item6）。"""
    raw = np.asarray(track.f0, dtype=float)
    i0, i1 = window.get("frame_start", 0), window.get("frame_end", 0)
    return np.asarray(raw[i0:i1], dtype=float)


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
    user_win: np.ndarray, ref_win: np.ndarray, path: list[tuple[int, int]], shift_cent: float = 0.0
) -> list[float]:
    """按 DTW 路径把用户帧映射到参考帧索引，产出帧级折叠 cent 序列（D3 图用）。

    ``shift_cent`` 为口径 v3 整体移调（item5）——图上曲线与评分同口径（移调后残余偏差）。
    """
    out: list[float | None] = [None] * len(ref_win)
    u = np.asarray(user_win, dtype=float)
    r = np.asarray(ref_win, dtype=float)
    for i, j in path:
        if i >= len(u) or j >= len(r) or u[i] <= 0 or r[j] <= 0:
            continue
        ratio = max(u[i], 1e-9) / max(r[j], 1e-9)
        out[j] = float(_fold_cent(1200.0 * np.log2(ratio) - shift_cent))
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
            "bpm_user": None,
            "bpm_ref": None,
            "bpm_source": "duration",
            "offset_ms": 0.0,
            # v6：Fake 评分器不分句窗（直接给分），弯折参数按恒等留痕（真实路径见 PyinSingScorer）
            "time_warp_stretch": 1.0,
            "windows_ms": [[int(line.seq), int(line.start_ms), int(line.end_ms)] for line in lines],
            "method": ALIGN_METHOD,
            "version": SCORING_VERSION,
            "transpose_semitones": 0,
            "range_hint": None,
            "medfilt_kernel": MEDFILT_KERNEL,
            "ref_coverage": result.ref_coverage,
            "pitch_weight": result.pitch_weight,
            "pitch_reliability": result.pitch_reliability,
            "weight_note": result.weight_note,
            "note_hit_rate": result.note_hit_rate,
            "user_coverage": result.user_coverage,
            "coverage_conf": result.coverage_conf,
            "coverage_note": result.coverage_note,
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
    """加权综合；分项缺失按剩余权重归一；全缺失 → None（不伪造分数，docs/11 Q-B08）。

    2026-09-10 护栏（P0-3 依赖项）：`total_w <= 0` 时直接 None——v5 逐句判据会让更多句子
    `rhythm=None`，若同时 `wp=0`（参考覆盖 <40% 的 item8 三段政策）且发音缺失，旧实现会
    `ZeroDivisionError` 使**整次评分作废**（lines 不落库 → 用户看到"评分失败"且白扣额度）。
    依据：docs/06 §9.4（item8 动态权重 + v5 R1）、docs/11 Q-B08（不伪造分数）。
    """
    items = [(v, w) for v, w in ((pitch, wp), (rhythm, wr), (pron, wpr)) if v is not None]
    if not items:
        return None
    total_w = sum(w for _, w in items)
    if total_w <= 0:
        return None
    return round(sum(v * w for v, w in items) / total_w, 2)


def _f0_pairs(user_win: np.ndarray, start_ms: float, hop: float) -> list[list[float]]:
    """用户逐帧 F0 → [[t_ms, f0_hz]...]（落库降密度格式，D4）。"""
    return [[round(start_ms + i * hop, 1), round(float(v), 1)] for i, v in enumerate(user_win)]


def math_ceil(x: float) -> int:
    """math.ceil 包装（保持纯函数/免顶层 import 负担）。"""
    import math

    return math.ceil(x)
