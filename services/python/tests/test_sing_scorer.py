"""唱歌评分核心测试（docs/06 §9.4 映射表 + v2 口径修正 A3/B2/C1；CI 零模型零 Key）。

覆盖：
- 映射表边界（音准/节奏分段线性，v2 保持不变）；
- 八度无关 cent（真机回归）；
- **v2 起唱检测**（F0 有声段 / 前置静音判据 / 能量兜底）；
- **v2 逐句局部 DTW 对齐后比较**（平移序列对齐后偏差≈0，同索引比较会偏——修复前必失败）；
- **v2 有效帧门槛**（C1）；
- 整首对齐方向语义（用户时间轴 = 参考 + offset）；
- 聚合降权（有效句均分 / 80% 完成度 / 0.5·0.2·0.3 复算）。
"""

from __future__ import annotations

import numpy as np
from app.audio.sing import (
    MIN_VOICED_FRAMES,
    SCORING_VERSION,
    LineScore,
    _cent_deviation,
    _dtw_path,
    _fold_cent,
    aggregate_result,
    align_frames,
    aligned_cent_deviation,
    detect_onset_ms,
    local_align,
    min_voiced_frames,
    pitch_score_from_cent,
    rhythm_score_from_dev,
)

HOP = 32.0


# ---------------------------------------------------------------------------
# 映射表（docs/06 §9.4，v2 未改动）
# ---------------------------------------------------------------------------
def test_pitch_score_bands():
    # docs/06 §9.4：≤50→90+ / ≤100→70~90 / ≤200→50~65 / >300→<40
    assert pitch_score_from_cent(0) == 95.0
    assert pitch_score_from_cent(50) == 95.0
    assert abs(pitch_score_from_cent(100) - 70.0) < 1e-6
    assert abs(pitch_score_from_cent(200) - 50.0) < 1e-6
    assert 40 <= pitch_score_from_cent(300) <= 50
    assert pitch_score_from_cent(400) < 40
    assert pitch_score_from_cent(400) >= 0


def test_rhythm_score_bands():
    # docs/06 §9.4：≤150ms→90+ / ≤300→75~90 / ≤600→55~75 / >1000→<50
    assert rhythm_score_from_dev(0) == 95.0
    assert rhythm_score_from_dev(150) == 95.0
    assert abs(rhythm_score_from_dev(300) - 75.0) < 1e-6
    assert abs(rhythm_score_from_dev(600) - 55.0) < 1e-6
    assert rhythm_score_from_dev(1000) == 40.0
    assert rhythm_score_from_dev(1500) < 50


def test_scoring_version_is_v2():
    """口径升级留痕（docs/10 §4.3：旧分可解释、不作废）。"""
    assert SCORING_VERSION == "v2"


# ---------------------------------------------------------------------------
# 八度无关 cent（真机回归）
# ---------------------------------------------------------------------------
def test_fold_cent_octave_equivalence():
    assert abs(_fold_cent(1200.0)) < 1e-9
    assert abs(_fold_cent(-2400.0)) < 1e-9
    assert abs(_fold_cent(100.0) - 100.0) < 1e-9
    assert abs(_fold_cent(-100.0) + 100.0) < 1e-9


def test_cent_deviation_is_octave_agnostic():
    ref = np.full(20, 440.0)
    assert _cent_deviation(np.full(20, 440.0), ref) == 0.0
    assert _cent_deviation(np.full(20, 880.0), ref) < 1.0
    assert _cent_deviation(np.full(20, 110.0), ref) < 1.0, "低两个八度仍视为同音高"
    flat = np.full(20, 440.0 * 2 ** (100 / 1200.0))
    assert abs(_cent_deviation(flat, ref) - 100.0) < 1.0
    assert _cent_deviation(np.zeros(20), ref) is None


# ---------------------------------------------------------------------------
# v2 · 起唱时刻检测（A3）
# ---------------------------------------------------------------------------
def test_detect_onset_basic():
    """前置静音 ≥150ms 后的第一个连续有声段 → 其起点。"""
    f0 = np.concatenate([np.zeros(10), np.full(20, 440.0)])
    onset = detect_onset_ms(f0, None, HOP)
    assert onset is not None
    assert abs(onset - 10 * HOP) < 1e-6


def test_detect_onset_ignores_short_gap():
    """句内换气（静音 <150ms）不视为新起唱——取整句真正的起点。"""
    f0 = np.concatenate([np.full(10, 440.0), np.zeros(3), np.full(10, 440.0)])
    onset = detect_onset_ms(f0, None, HOP)
    assert onset is not None
    assert abs(onset - 0.0) < 1e-6, "3 帧静音（96ms）应被当作句内换气"


def test_detect_onset_skips_too_short_run():
    """连续有声不足 min_run 帧（噪声/尾音）→ 跳过，取下一段。"""
    f0 = np.concatenate([np.full(2, 440.0), np.zeros(6), np.full(10, 440.0)])
    onset = detect_onset_ms(f0, None, HOP)
    assert onset is not None
    assert abs(onset - 8 * HOP) < 1e-6


def test_detect_onset_energy_fallback():
    """F0 全清音（气声/低信噪比）→ 能量包络兜底定位起唱点。"""
    f0 = np.zeros(30)
    rms = np.concatenate([np.zeros(12), np.full(18, 0.2)])
    onset = detect_onset_ms(f0, rms, HOP)
    assert onset is not None
    assert abs(onset - 12 * HOP) < 1e-6


def test_detect_onset_all_silent_returns_none():
    assert detect_onset_ms(np.zeros(30), np.zeros(30), HOP) is None


# ---------------------------------------------------------------------------
# v2 · 逐句局部 DTW 对齐（B2）
# ---------------------------------------------------------------------------
def test_local_align_recovers_shift():
    """用户句整体平移 3 帧 → 局部 DTW 应吸收该平移（offset≈3 帧）。"""
    ref = np.concatenate([np.full(10, 440.0), np.full(10, 550.0), np.full(10, 660.0)])
    user = np.concatenate([np.zeros(3), ref[:-3]])
    off_frames, path = local_align(user, ref)
    assert path, "应产出对齐路径"
    assert abs(off_frames - 3.0) <= 1.0


def test_aligned_cent_beats_same_index_on_shift():
    """**修复前必失败**：用户句平移 5 帧时，对齐后偏差应远小于同索引比较。

    用连续滑音旋律（每帧升 50 cent）——同索引比较会得到 ≈250 cent 的恒定偏差
    （= 5 帧 × 50 cent），局部 DTW 对齐后应接近 0（v2 修正点）。
    """
    n = 30
    ref = 440.0 * 2 ** (np.arange(n) * 50.0 / 1200.0)
    shift = 5
    user = np.concatenate([np.zeros(shift), ref[:-shift]])
    _, path = local_align(user, ref)
    aligned, n_pairs = aligned_cent_deviation(user, ref, path)
    same_index = _cent_deviation(user, ref)
    assert n_pairs >= 3
    assert aligned is not None and same_index is not None
    assert same_index > 150.0, f"同索引比较应显著偏大（实际 {same_index:.1f}）"
    assert aligned < 30.0, f"对齐后偏差应很小（实际 {aligned:.1f} cent）"
    assert aligned < same_index, "对齐后比较必须优于同索引比较（v2 修正点）"


def test_aligned_cent_detects_real_offkey():
    """真跑调（整句高半音）在对齐后仍被检出 ≈100 cent。"""
    ref = np.full(30, 440.0)
    user = np.full(30, 440.0 * 2 ** (100 / 1200.0))
    _, path = local_align(user, ref)
    aligned, _ = aligned_cent_deviation(user, ref, path)
    assert aligned is not None
    assert abs(aligned - 100.0) < 15.0


def test_dtw_path_band_limits_warping():
    """Sakoe-Chiba 带内对齐：路径索引差不应超过带宽容许（防一句压成一点）。"""
    a = np.sin(np.linspace(0, 6.28, 60))
    b = np.sin(np.linspace(0, 6.28, 60))
    path = _dtw_path(a, b, 0.25, open_end=False)
    assert path[0] == (0, 0) and path[-1] == (59, 59)
    max_delta = max(abs(i - j) for i, j in path)
    assert max_delta <= int(60 * 0.25) + 1


# ---------------------------------------------------------------------------
# v2 · 有效帧门槛（C1）
# ---------------------------------------------------------------------------
def test_min_voiced_frames_ratio_and_floor():
    # C1 重拍板（2026-09-09 实测）：比例 15% + 绝对下限 10 帧
    assert min_voiced_frames(155) == 24  # ceil(155×15%) = 24
    assert min_voiced_frames(20) == MIN_VOICED_FRAMES  # 短句走绝对下限
    assert min_voiced_frames(0) == MIN_VOICED_FRAMES


# ---------------------------------------------------------------------------
# 整首对齐方向语义（v2 修正：用户时间轴 = 参考 + offset）
# ---------------------------------------------------------------------------
def test_align_frames_identical_and_shifted():
    base = np.concatenate([np.full(10, 220.0), np.full(40, 440.0), np.full(10, 330.0)])
    ratio, offset = align_frames(base, base, HOP)
    assert abs(ratio - 1.0) < 1e-6
    assert abs(offset) <= HOP
    # 用户整体延迟 5 帧（先静音后唱）→ offset ≈ +5 帧（用户时间轴 = 参考 + offset）
    shift = 5
    delayed = np.concatenate([np.zeros(shift, dtype=float), base[:-shift]])
    _ratio2, offset2 = align_frames(delayed, base, HOP)
    assert offset2 > 0, "用户晚起唱 → offset 应为正（v2 方向语义）"
    assert abs(offset2 - shift * HOP) <= 2 * HOP


# ---------------------------------------------------------------------------
# 聚合降权（D5）
# ---------------------------------------------------------------------------
def test_aggregate_missing_downgrade():
    lines = [
        LineScore(
            seq=1, start_ms=0, end_ms=1000, pitch_score=90.0, rhythm_score=80.0, pron_score=70.0
        ),
        LineScore(
            seq=2, start_ms=1000, end_ms=2000, pitch_score=60.0, rhythm_score=50.0, pron_score=None
        ),
        LineScore(
            seq=3,
            start_ms=2000,
            end_ms=3000,
            pitch_score=None,
            rhythm_score=None,
            pron_score=None,
            skipped=True,
            reason="low_frames",
        ),
    ]
    r = aggregate_result(lines)
    assert r.pitch == 75.0
    assert r.rhythm == 65.0
    assert r.pron == 70.0
    assert abs(r.overall - (0.5 * 75.0 + 0.2 * 65.0 + 0.3 * 70.0)) < 1e-6
    assert r.evaluated_lines == 2
    assert r.is_complete is False  # 2/3 = 66.7% < 80%


def test_aggregate_complete_threshold_and_weight_normalize():
    lines = [
        LineScore(
            seq=i, start_ms=0, end_ms=1000, pitch_score=None, rhythm_score=None, pron_score=None
        )
        for i in range(1, 5)
    ]
    lines.append(
        LineScore(
            seq=5,
            start_ms=0,
            end_ms=1000,
            pitch_score=None,
            rhythm_score=None,
            pron_score=None,
            skipped=True,
            reason="no_ref",
        )
    )
    r = aggregate_result(lines)
    assert r.evaluated_lines == 4
    assert r.is_complete is True  # 4/5 = 80%
    assert r.overall is None  # 无分项 → None（不伪造）


def test_aggregate_partial_weights():
    lines = [
        LineScore(
            seq=1, start_ms=0, end_ms=1000, pitch_score=90.0, rhythm_score=80.0, pron_score=None
        ),
    ]
    r = aggregate_result(lines)
    assert abs(r.overall - (90.0 * 0.5 + 80.0 * 0.2) / 0.7) < 0.01
