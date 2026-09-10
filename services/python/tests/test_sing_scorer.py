"""唱歌评分核心测试（docs/06 §9.4 映射表 + v2 口径修正 A3/B2/C1 + v3 算法增强 item5~8）。

覆盖：
- 映射表边界（音准/节奏分段线性，v2/v3 均保持不变）；
- 八度无关 cent（真机回归）；
- **v2 起唱检测**（F0 有声段 / 前置静音判据 / 能量兜底）；
- **v2 逐句局部 DTW 对齐后比较**（平移序列对齐后偏差≈0，同索引比较会偏——修复前必失败）；
- **v2 有效帧门槛**（C1）；
- 整首对齐方向语义（用户时间轴 = 参考 + offset）；
- 聚合降权（有效句均分 / 80% 完成度 / 0.5·0.2·0.3 复算）；
- **v3 中值滤波**（item6：颤音抑制 / 保静音 / 孤帧保留）；
- **v3 整体移调**（item5：系统性低 3 半音 40→95 修复前必失败 / 整数半音量化 / 音域提示）；
- **v3 真实 BPM**（item7：onset 间隔中位；ononset 比 vs 时长截断比 修复前必失败）；
- **v3 参考完整性动态权重**（item8：三段政策 + 综合复算）。
"""

from __future__ import annotations

import numpy as np
from app.audio.sing import (
    MIN_VOICED_FRAMES,
    SCORING_VERSION,
    WIN_RATIO_MAX,
    WIN_RATIO_MIN,
    LineScore,
    _cent_deviation,
    _dtw_path,
    _fold_cent,
    _user_coverage_conf,
    aggregate_result,
    align_frames,
    aligned_cent_deviation,
    bpm_from_onsets,
    bpm_ratio_info,
    combine_bpm,
    detect_onset_ms,
    estimate_transpose_semitones,
    has_breath_structure,
    local_align,
    median_filter_f0,
    min_voiced_frames,
    note_hit_factor,
    note_hit_rate,
    pitch_score_from_cent,
    range_hint_text,
    rhythm_score_from_dev,
    window_scale,
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


def test_scoring_version_is_v6():
    """口径升级留痕（docs/10 §4.3：旧版本分可解释、不作废）。

    v4 = 乱唱鲁棒性（R1 换气结构 / R2 音符命中率乘性衰减 / R3 覆盖率置信度）；
    v5 = 2026-09-10 P0 修复：**R1 判据由整轨下沉为逐句**（`onset_is_continuation`）+
    `reason='no_onset'` + `alignment.breath_structure` 留痕；
    v6 = 2026-09-10 复测修复（F1）：**句窗端点走时间弯折**（DTW 路径局部中位 + 全局仿射兜底，
    `alignment.time_warp_stretch` / `alignment.windows_ms` 留痕）——修「用户偏慢时后续句窗口落到
    上一句句腹 → 整首无节奏分」（分数分布变化 → 升版本）。
    """
    assert SCORING_VERSION == "v6"


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


def test_local_align_not_truncated_to_shorter_side():
    """**BUG-4 修复前必失败**：用户句比参考句长（整体慢 19%）时，局部 DTW 必须覆盖
    **完整参考句**——修复前 `n = min(len(u), len(r))` 会把用户尾部截掉（且参考句
    只能对齐到自身前 len(u) 帧），句尾音高信息参与不到对齐/评分。

    构造：参考 = 30 帧 3 段音；用户 = 同旋律时间拉伸 1.19×（35 帧，每段等长放大）。
    断言路径最后一个参考索引到达参考句末尾（≈18 帧，修复前上限 ≈ n-1 = 29 中的
    用户索引截断处——关键判据是路径长度与覆盖到最后一帧）。
    """
    ref = np.concatenate([np.full(10, 440.0), np.full(10, 550.0), np.full(10, 660.0)])
    user = np.concatenate(
        [np.full(12, 440.0), np.full(12, 550.0), np.full(11, 660.0)]
    )  # 35 帧 ≈ 1.17×
    _off, path = local_align(user, ref)
    assert path, "应产出对齐路径"
    assert max(j for _, j in path) == len(ref) - 1, "参考句末帧必须参与对齐（修复前被短侧截断）"
    cent, n_pairs = aligned_cent_deviation(user, ref, path)
    assert cent is not None
    assert cent < 30.0, f"同旋律仅速度不同 → 对齐后偏差应很小（实际 {cent:.1f} cent）"
    assert n_pairs >= len(ref) * 0.8, f"有效帧对覆盖不足（{n_pairs}）"


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
# 整首粗对齐规模护栏（P1-11：180s 歌 48.3s / 506MB → 降采样）
# ---------------------------------------------------------------------------
def test_global_dtw_step_boundaries():
    """步长边界：≤4000 帧不降采样；180s（5625 帧）→ 2；300s（9375 帧）→ 4（封顶 ~2500 帧量级）。"""
    from app.audio.sing import GLOBAL_DTW_FULL_FRAMES, GLOBAL_DTW_TARGET_FRAMES, global_dtw_step

    assert global_dtw_step(8) == 1
    assert global_dtw_step(GLOBAL_DTW_FULL_FRAMES) == 1, "阈值内必须保持全分辨率（精度优先）"
    assert global_dtw_step(5625) == 2, "180s@32ms = 5625 帧 → step 2（旧实现永不触发护栏）"
    assert global_dtw_step(9375) == 4
    # 降采样后帧数被压到目标量级（内存 O(n²) 有界）
    for n in (4001, 5625, 9375):
        assert -(-n // global_dtw_step(n)) <= GLOBAL_DTW_TARGET_FRAMES * 1.5


def test_align_frames_downsamples_long_song(monkeypatch):
    """**P1-11 核心**：180s 级输入必须降采样后再做整首 DTW。

    修复前必失败：旧护栏 `if n > 6000: step = 2` 对 5625 帧永不触发 → `_dtw_path` 收到全量
    5625 帧 → 成本矩阵 253MB×2 + 带内 630 万次 Python 循环（实测 48.3s / 506MB，
    sing_concurrency=2 时两首并发近 1GB，容器 2GB 有 OOM 风险）。
    """
    import app.audio.sing as sing_mod
    from app.audio.sing import align_frames, global_dtw_step

    seen: dict[str, int] = {}

    def fake_path(uu, rr, band_ratio, *, open_end):
        seen["n"] = len(uu)
        seen["m"] = len(rr)
        return [(i, i) for i in range(10)]  # 恒定偏移 → offset 0（只关心传入规模）

    monkeypatch.setattr(sing_mod, "_dtw_path", fake_path)

    n180 = 5625  # 180s @ hop 32ms（config max_sing_seconds=180）
    user = np.full(n180, 440.0)
    ref = np.full(n180, 440.0)
    _ratio, offset = align_frames(user, ref, HOP)

    step = global_dtw_step(n180)
    assert step == 2
    assert seen["n"] <= n180 // step + 1, f"整首 DTW 收到 {seen['n']} 帧（未降采样）"
    assert seen["n"] < n180, "修复前此处收到全量帧（护栏死代码）"
    assert offset % (HOP * step) == 0, "offset 量化单位 = hop×step"


def test_align_frames_keeps_full_resolution_for_short_song(monkeypatch):
    """反向护栏：100s 以内（≤3000 帧）**不得**降采样——offset 保持 1 帧粒度。"""
    import app.audio.sing as sing_mod
    from app.audio.sing import align_frames

    seen: dict[str, int] = {}

    def fake_path(uu, rr, band_ratio, *, open_end):
        seen["n"] = len(uu)
        return [(i, i) for i in range(10)]

    monkeypatch.setattr(sing_mod, "_dtw_path", fake_path)
    n = 3000  # 96s
    align_frames(np.full(n, 440.0), np.full(n, 440.0), HOP)
    assert seen["n"] == n, "阈值内降采样会无谓损失 offset 精度"


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
    # v4 · R3：2/3 有效 → 覆盖率 0.667 → 置信度 0.6+0.4×(0.667−0.4)/0.4 = 0.8667（线性降权）
    assert r.user_coverage is not None and abs(r.user_coverage - 2 / 3) < 1e-6
    assert r.coverage_conf is not None and abs(r.coverage_conf - 0.8667) < 1e-3
    assert r.coverage_note is not None
    weighted = 0.5 * 75.0 + 0.2 * 65.0 + 0.3 * 70.0
    assert abs(r.overall - round(weighted * r.coverage_conf, 2)) < 0.01
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


# ---------------------------------------------------------------------------
# v3 · F0 中值滤波（item6：抑制颤音抖动，与合成参考对称）
# ---------------------------------------------------------------------------
def test_medfilt_suppresses_vibrato():
    """**修复前必失败**：5.5Hz 颤音（±60 cent）滤波后残余应 <15 cent（原始振动 >40 cent）。"""
    n = 200
    t = np.arange(n) * 0.032  # 31.25 Hz 帧率（hop 32ms）
    vib = 60.0 * np.sin(2 * np.pi * 5.5 * t)
    f0 = 440.0 * 2 ** (vib / 1200.0)
    out = median_filter_f0(f0, 5)
    residual = np.abs(1200.0 * np.log2(out / 440.0))
    assert np.median(np.abs(vib)) > 40.0, "对照：原始颤音幅度应显著"
    assert np.median(residual) < 15.0, f"滤波后残余偏大：{np.median(residual):.1f} cent"


def test_medfilt_keeps_silence_and_isolated_frames():
    """0 帧（清音）必须保持 0（滤器不跨静音）；孤立有声帧保留（不删也不造）。"""
    f0 = np.concatenate([np.zeros(6), np.full(8, 440.0), np.zeros(4), np.full(8, 554.37)])
    out = median_filter_f0(f0, 5)
    assert (out[:6] == 0).all(), "前导静音必须保持 0"
    assert (out[14:18] == 0).all(), "句中静音必须保持 0"
    assert out[6:14].mean() > 400.0, "有声段均值应保持"
    iso = np.array([0.0, 0.0, 0.0, 440.0, 0.0, 0.0, 0.0])
    assert median_filter_f0(iso, 5)[3] == 440.0, "孤立帧应保留原值"


def test_medfilt_short_input_returned_as_is():
    f0 = np.array([440.0, 0.0])
    assert np.array_equal(median_filter_f0(f0, 5), f0)


# ---------------------------------------------------------------------------
# v3 · 音域自适应移调（item5：先整体移调再评）
# ---------------------------------------------------------------------------
def test_transpose_three_semitones_low():
    """**修复前必失败**：用户系统性低 3 半音——v2 恒判 300 cent（≤40 分）；
    v3 移调 −3 半音后残余 <30 cent（≤50 → 95 分）。"""
    ref = np.full(30, 440.0)
    user = np.full(30, 440.0 * 2 ** (-300 / 1200.0))
    assert estimate_transpose_semitones(user, ref) == -3
    shifted = _cent_deviation(user, ref, shift_cent=-300.0)
    raw = _cent_deviation(user, ref)
    assert shifted is not None and raw is not None
    assert shifted < 30.0, f"移调后残余应≈0（实际 {shifted:.1f} cent）"
    assert raw > 250.0, f"v2 口径应判 300 cent 附近（实际 {raw:.1f}）"
    assert pitch_score_from_cent(shifted) == 95.0
    assert pitch_score_from_cent(raw) <= 40.0


def test_transpose_octave_equivalent_is_zero():
    """低 1 个八度 → 折叠后应视为无需移调（八度等价，docs/06 §9.4 口径）。"""
    ref = np.full(30, 440.0)
    user = np.full(30, 220.0)
    assert estimate_transpose_semitones(user, ref) == 0


def test_transpose_insufficient_frames_no_shift():
    """有效帧不足（<MIN_TRANSPOSE_PAIRS=10）→ 统计不可信 → 不移调。"""
    ref = np.full(30, 440.0)
    user = np.concatenate([np.full(5, 370.0), np.zeros(25)])
    assert estimate_transpose_semitones(user, ref) == 0


def test_range_hint_direction():
    assert "降 2 个半音" in range_hint_text(-2) and "偏高" in range_hint_text(-2)
    assert "升 3 个半音" in range_hint_text(3) and "偏低" in range_hint_text(3)
    assert range_hint_text(0) is None


# ---------------------------------------------------------------------------
# v3 · 真实 BPM（item7：onset 间隔中位，替代时长截断比）
# ---------------------------------------------------------------------------
def test_bpm_from_onsets_basic():
    onsets = [200.0 + i * 500.0 for i in range(8)]  # 500ms 一个音
    assert abs(bpm_from_onsets(onsets) - 120.0) < 0.1


def test_bpm_from_onsets_filters_outliers():
    """长休止（>3000ms）不污染 IOI 中位（防倍速/长休止混淆）。"""
    ev = [200.0 + i * 500.0 for i in range(6)] + [3200.0, 7200.0]  # 尾段 4000ms 休止
    assert abs(bpm_from_onsets(ev) - 120.0) < 1.0


def test_bpm_from_onsets_dedupes_adjacent_frames():
    """**BUG-1 附带修复**：librosa 在强起音处给出相邻重复帧（480/480、1152/1152）——
    去重后 IOI 统计不被 0ms 间隔稀释（真实容器实测：63 onset 中含成对重复）。"""
    onsets = [480.0, 480.0, 1152.0, 1152.0, 1792.0, 2464.0, 2464.0, 3104.0, 3104.0, 3712.0]
    assert bpm_from_onsets(onsets) is not None  # 去重后 5 个有效间隔
    deduped_only = [480.0, 1152.0, 1792.0, 2464.0, 3104.0, 3712.0]
    assert abs(bpm_from_onsets(onsets) - bpm_from_onsets(deduped_only)) < 1e-9


def test_bpm_from_onsets_too_few_intervals():
    assert bpm_from_onsets([0.0, 500.0, 1000.0]) is None  # 仅 2 个间隔 <3


# ---------------------------------------------------------------------------
# v3 · 两路 onset 的 BPM 层仲裁（2026-09-10 评估结论 · combine_bpm）
# ---------------------------------------------------------------------------
def test_combine_bpm_prefers_f0_when_agree():
    """两路一致（比值 <1.5）→ 取 F0 路（假起音更少：合成评测 F1 0.73 vs 0.36）。"""
    bpm, how = combine_bpm(b_flux=118.0, b_f0=117.2, approx_bpm=120.0)
    assert how == "onset-f0"
    assert bpm == 117.2


def test_combine_bpm_arbitrates_octave_disagreement():
    """八度分歧（比值 ∈[1.5,2.3]）→ 取与粗估更近者。

    场景：flux 倍速 208.3 / f0 半速 104.2，粗估（时长比）120 → 选 f0 侧 104.2。
    """
    bpm, how = combine_bpm(b_flux=208.3, b_f0=104.2, approx_bpm=120.0)
    assert how == "onset-arbitrated"
    assert abs(bpm - 104.2) < 1e-6


def test_combine_bpm_octave_corrects_single_side():
    """**同音重复场景**（F0 全漏 → None；flux 倍速）：flux + 八度校正回到合理区间。

    修复前：flux 口径直接给出 208.3（真值 120 → 误差 88.3）；
    本函数：208.3 → 104.2（误差 15.8），且**不返回 None**（旧 f0-only 方案会 None）。
    """
    bpm, how = combine_bpm(b_flux=208.3, b_f0=None, approx_bpm=120.0)
    assert how == "onset-flux"
    assert bpm is not None and abs(bpm - 208.3 / 2) < 1e-6


def test_combine_bpm_none_both():
    bpm, how = combine_bpm(b_flux=None, b_f0=None, approx_bpm=120.0)
    assert bpm is None and how == "none"


def test_combine_bpm_without_approx_keeps_raw():
    """无粗估（参考侧不可用）→ 不做八度校正，保留检测原值（不猜）。"""
    bpm, how = combine_bpm(b_flux=208.3, b_f0=None, approx_bpm=None)
    assert bpm == 208.3 and how == "onset-flux"


def test_bpm_ratio_info_f0_channel_and_sources():
    """bpm_ratio_info 接入 F0 通道：``user_f0_onsets_ms`` 提供 → source 来自仲裁；
    不提供（旧调用/旧数据）→ 保持既有 flux 行为（向后兼容）。"""
    user_flux = [100.0 + i * 500.0 for i in range(8)]  # 120 BPM
    ref = [100.0 + i * 500.0 for i in range(8)]  # 120 BPM
    info_legacy = bpm_ratio_info(user_flux, 8000.0, ref, 8000.0)
    assert info_legacy["bpm_source"] == "onset-flux"  # 兼容：仅频谱通道
    info_f0 = bpm_ratio_info(
        user_flux, 8000.0, ref, 8000.0, user_f0_onsets_ms=[100.0 + i * 510.0 for i in range(8)]
    )
    assert info_f0["bpm_source"] in ("onset-f0", "onset-arbitrated")
    assert abs(info_f0["bpm_ratio"] - 1.0) < 0.05


def test_window_scale_clamps_untrusted_ratio():
    """**窗口缩放的八度误判风险控制**：ratio 超可信域 → 按边界值（窗口不被拉爆）。"""
    assert abs(window_scale(None) - 1.0) < 1e-9
    assert abs(window_scale(1.0) - 1.0) < 1e-9
    assert abs(window_scale(0.84) - 1 / 0.84) < 1e-6  # 慢 19% → 窗口更长
    assert abs(window_scale(2.0) - 1 / WIN_RATIO_MAX) < 1e-9  # 倍速误判 → clamp
    assert abs(window_scale(0.4) - 1 / WIN_RATIO_MIN) < 1e-9  # 半速误判 → clamp
    assert abs(window_scale(0.0) - 1.0) < 1e-9  # 非法值 → 不缩放


def test_bpm_ratio_onset_beats_duration():
    """**修复前必失败**：两端时长相同 → 旧「时长截断比」=1.0；
    onset 口径（两侧同量纲音符级）→ 用户 120bpm / 参考 60bpm → ratio=2.0。"""
    user_onsets = [100.0 + i * 500.0 for i in range(8)]
    ref_onsets = [100.0 + i * 1000.0 for i in range(8)]
    info = bpm_ratio_info(user_onsets, 8000.0, ref_onsets, 8000.0)
    assert info["bpm_source"] == "onset-flux"  # 仅频谱通道（未传 F0 通道）
    assert abs(info["bpm_ratio"] - 2.0) < 1e-6
    assert abs(info["bpm_user"] - 120.0) < 0.5
    assert abs(info["bpm_ref"] - 60.0) < 0.5


def test_bpm_ratio_reference_onset_unavailable_falls_back():
    """**BUG-1 回归守卫**：参考侧若仍是旧世代（无 onsets_ms）或只有句起点（秒级间隔）→
    onset 口径不可用 → 必须诚实回落 duration，**不得**用异量纲算出垃圾 ratio
    （旧实现把 4.9s 句间隔与音符级 onset 相比，会得到被 clamp 的伪值）。"""
    user_onsets = [100.0 + i * 500.0 for i in range(8)]  # 音符级
    ref_line_starts = [0.0, 4890.0, 9780.0, 14670.0, 19560.0, 24450.0]  # LRC 句起点（秒级）
    info = bpm_ratio_info(user_onsets, 8000.0, ref_line_starts, 8000.0)
    assert info["bpm_source"] == "duration", "异量纲参考侧必须回落到 duration（不得伪造节拍）"
    assert info["bpm_ref"] is None


def test_bpm_ratio_falls_back_to_duration():
    """任一侧 onset 不可用 → 回退时长截断比并标注（信息性字段不伪造节拍）。"""
    info = bpm_ratio_info([], 8000.0, [100.0, 700.0, 1300.0], 4000.0)
    assert info["bpm_source"] == "duration"
    assert abs(info["bpm_ratio"] - 0.5) < 1e-6  # 4000/8000
    assert info["bpm_user"] is None


# ---------------------------------------------------------------------------
# v4 · 乱唱鲁棒性（R1 起唱句前判据 / R2 音符命中率 / R3 覆盖率置信度）
# ---------------------------------------------------------------------------
def test_note_hit_rate_discriminates_melody_vs_chaos():
    """**修复前必失败（R2）**：真机乱唱命中率 0% 却拿音准 60.5/56.0。

    参考 = 阶梯旋律（440/550/660 各 10 帧）：
    - 唱对 → 命中率 1.0；
    - **整体低 3 半音但旋律正确**（配 shift_cent=−300）→ 仍应 1.0
      （自测抓到：命中率若不做移调补偿，会把"整体偏低"的正常用户误判为没唱旋律）；
    - **乱唱（随机跳变，音高多不在参考音上）** → 应 < 0.5。
    """
    ref = np.concatenate([np.full(10, 440.0), np.full(10, 550.0), np.full(10, 660.0)])
    assert note_hit_rate(ref, ref.copy()) == 1.0
    low3 = ref * 2 ** (-300 / 1200.0)
    assert note_hit_rate(ref, low3, shift_cent=-300.0) == 1.0
    uncompensated = note_hit_rate(ref, low3)
    assert uncompensated is not None and uncompensated < 0.5, (
        "未补偿移调时不该命中（说明比较口径确实依赖 shift_cent）"
    )
    rng = np.random.default_rng(7)
    chaos = np.repeat(rng.uniform(480.0, 620.0, 10), 3)[: len(ref)]
    rate = note_hit_rate(ref, chaos)
    assert rate is not None and rate < 0.5, f"乱唱命中率应低于门槛（实际 {rate}）"


def test_note_hit_rate_slow_glissando_is_known_boundary():
    """**已知边界（诚实记录）**：极慢的匀速滑音会逐个"路过"每个音符 → 命中率不低。

    这类唱法在物理上确实经过了每个音（滑音式演唱），与真唱的区分度有限；
    真机乱唱是"随机跳变"（命中率 0%），本判据能拦住它——见上一条用例与 BUG 实测。
    """
    ref = np.concatenate([np.full(10, 440.0), np.full(10, 550.0), np.full(10, 660.0)])
    slow_glide = np.linspace(400.0, 700.0, len(ref))  # 每帧 10Hz 的慢扫频
    rate = note_hit_rate(ref, slow_glide)
    assert rate is not None and rate >= 0.5, f"慢滑音命中率（边界记录）：{rate}"


def test_note_hit_rate_reference_without_notes():
    assert note_hit_rate(np.zeros(20), np.full(20, 440.0)) is None
    assert note_hit_rate(np.full(20, 440.0), np.zeros(20)) == 0.0  # 用户全清音 → 0


def test_note_hit_factor_curve():
    """R2 乘性衰减系数（组长拍板 C，下限 0.6）：hit=0 → ×0.6；hit=1 → ×1.0；None → ×1.0。

    实测标定：唱得准的素材命中率约 58% → ×0.83（"准唱轻微下调"）；
    乱唱/严重跑调命中率 0~17% → ×0.6~0.69（"显著降分但不清零"）。
    """
    assert note_hit_factor(None) == 1.0
    assert note_hit_factor(1.0) == 1.0
    assert note_hit_factor(0.0) == 0.6
    assert abs(note_hit_factor(0.5) - 0.8) < 1e-9
    assert abs(note_hit_factor(0.2) - 0.68) < 1e-9
    assert note_hit_factor(-1.0) == 0.6  # 越界夹紧
    assert note_hit_factor(2.0) == 1.0


def test_has_breath_structure_discriminates():
    """**修复前必失败（R1）**：整轨没有 ≥150ms 静音段（一口气唱到底）→ 不给节奏分。

    - 连续发声（乱唱）→ False（该次演唱所有句 rhythm=None）；
    - 有换气（句间静音 ≥150ms，正常真唱）→ True；
    - 音符内短断点（<150ms，如 80ms 断奏）→ 不算换气 → False。

    自测教训：初版判据用"句前 320ms 是否有声"，在整体速度差大时窗口会错位到上一句尾音
    → 真唱素材 6/6 被误杀；整轨结构判据不受窗口错位影响。
    """
    assert has_breath_structure(np.full(40, 440.0), HOP) is False
    with_breath = np.concatenate([np.full(20, 440.0), np.zeros(8), np.full(20, 550.0)])
    assert has_breath_structure(with_breath, HOP) is True  # 8 帧 ≈ 256ms ≥150ms
    staccato_short = np.concatenate([np.full(10, 440.0), np.zeros(3), np.full(10, 550.0)])
    assert has_breath_structure(staccato_short, HOP) is False  # 3 帧 ≈ 96ms < 150ms
    assert has_breath_structure(np.asarray([]), HOP) is False


def test_user_coverage_conf_curve():
    """R3 三段线性：≥80% 全额；40~80% 线性 0.6→1.0；<40% → 0（不给综合分）。"""
    assert _user_coverage_conf(None)[0] == 1.0
    assert _user_coverage_conf(1.0)[0] == 1.0
    assert abs(_user_coverage_conf(0.8)[0] - 1.0) < 1e-9
    assert abs(_user_coverage_conf(0.6)[0] - 0.8) < 1e-9  # 0.6+0.4×0.5
    assert abs(_user_coverage_conf(0.4)[0] - 0.6) < 1e-9
    conf, note = _user_coverage_conf(0.33)
    assert conf == 0.0 and note is not None


def test_aggregate_user_coverage_low_no_overall():
    """R3 端到端（聚合层）：6 句仅 2 句有效（33% < 40%）→ 综合分 None（截图场景）。"""
    lines = [
        LineScore(
            seq=i, start_ms=0, end_ms=1000, pitch_score=60.0, rhythm_score=95.0, pron_score=None
        )
        for i in range(1, 3)
    ] + [
        LineScore(
            seq=i,
            start_ms=0,
            end_ms=1000,
            pitch_score=None,
            rhythm_score=None,
            pron_score=None,
            skipped=True,
            reason="no_pitch",
        )
        for i in range(3, 7)
    ]
    r = aggregate_result(lines)
    assert r.evaluated_lines == 2 and r.expected_lines == 6
    assert r.coverage_conf == 0.0
    assert r.overall is None, "有效句 2/6 → 不足以评分"
    assert r.pitch == 60.0 and r.rhythm == 95.0  # 分项仍展示（供诊断）


def test_aggregate_note_hit_rate_summary():
    """R2 报告字段：逐句命中率汇总到整首（均分；全 None → None）。

    口径 v4 拍板 C：命中率**只做音准分的乘性衰减**（不下发 off_melody 判罚），
    但命中率本身仍逐句落库 + 整首汇总，供报告展示与排障复核。
    """
    lines = [
        LineScore(
            seq=1,
            start_ms=0,
            end_ms=1000,
            pitch_score=30.0,
            rhythm_score=95.0,
            pron_score=None,
            note_hit_rate=0.0,
        ),
        LineScore(
            seq=2,
            start_ms=0,
            end_ms=1000,
            pitch_score=45.0,
            rhythm_score=95.0,
            pron_score=None,
            note_hit_rate=0.6,
        ),
    ]
    r = aggregate_result(lines)
    assert r.note_hit_rate == 0.3  # (0.0 + 0.6) / 2
    assert r.pitch == 37.5
    nohits = [
        LineScore(
            seq=i, start_ms=0, end_ms=1000, pitch_score=50.0, rhythm_score=50.0, pron_score=None
        )
        for i in range(1, 3)
    ]
    assert aggregate_result(nohits).note_hit_rate is None


# ---------------------------------------------------------------------------
# v3 · 参考完整性动态权重（item8）
# ---------------------------------------------------------------------------
def test_aggregate_ref_coverage_reduces_pitch_weight():
    """3 句 1 句参考缺失 → coverage=2/3 → wp=0.4 → overall 按 0.4/0.2/0.3 归一复算。"""
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
            reason="no_ref",
            no_ref=True,
        ),
    ]
    r = aggregate_result(lines)
    assert abs(r.ref_coverage - 2 / 3) < 1e-6
    assert abs(r.pitch_weight - 0.4) < 1e-6  # 0.2 + (0.6667−0.4)/0.4×0.3
    assert r.pitch_reliability == "reduced"
    assert r.weight_note is not None
    # 0.4·75 + 0.2·65 + 0.3·70 = 64 → /0.9；v4：再乘覆盖率置信度 0.8667（2/3 有效）
    weighted = (0.4 * 75.0 + 0.2 * 65.0 + 0.3 * 70.0) / 0.9
    assert abs(r.overall - round(weighted * r.coverage_conf, 2)) < 0.01


def test_aggregate_ref_coverage_low_excludes_pitch():
    """覆盖 <40% → 音准不计入综合（仅展示）——参考缺失过半时不再硬算。

    **2026-09-10 P1-10（口径 v5.1）语义有意变更**：本用例 5 句里 4 句是**服务端参考缺失**
    （`no_ref`），用户把唯一有参考的句子唱好了 → 用户覆盖率应为 **1.0**。旧断言
    （`coverage_conf==0.0`、`overall is None`）正是"参考缺失二次惩罚用户"的固化：
    用户唱得再全也永远拿不到综合分，且文案写「请完整演唱一遍再评」把服务端问题说成用户漏唱。
    现口径：参考不足**只由 item8 表达**（`pitch_weight=0 / reliability=low / weight_note`），
    综合分由节奏+发音按剩余权重归一得出；覆盖率只表达用户自己的漏唱。
    """
    lines = [
        LineScore(
            seq=1, start_ms=0, end_ms=1000, pitch_score=90.0, rhythm_score=80.0, pron_score=None
        ),
    ]
    for i in range(2, 6):  # 4 句 no_ref → ref_coverage = 1/5 = 0.2（item8 降权依据）
        lines.append(
            LineScore(
                seq=i,
                start_ms=0,
                end_ms=1000,
                pitch_score=None,
                rhythm_score=None,
                pron_score=None,
                skipped=True,
                reason="no_ref",
                no_ref=True,
            )
        )
    r = aggregate_result(lines)
    assert abs(r.ref_coverage - 0.2) < 1e-6
    assert r.pitch_weight == 0.0
    assert r.pitch_reliability == "low"
    assert r.weight_note is not None
    # v5.1：分母只算有参考的句（本用例仅 1 句）→ 用户唱全 = 100%
    assert r.user_coverage == 1.0
    assert r.coverage_conf == 1.0
    assert r.coverage_note is None
    assert r.overall is not None, "参考不足 ≠ 用户没唱：分数仍给（wp=0，带 weight_note 标注）"


def test_aggregate_ref_coverage_full_keeps_half():
    """无参考缺失 → 全额 0.5（基线权重不变，docs/06 §9.4）。"""
    lines = [
        LineScore(
            seq=1, start_ms=0, end_ms=1000, pitch_score=90.0, rhythm_score=80.0, pron_score=70.0
        ),
        LineScore(
            seq=2, start_ms=1000, end_ms=2000, pitch_score=60.0, rhythm_score=50.0, pron_score=None
        ),
    ]
    r = aggregate_result(lines)
    assert r.ref_coverage == 1.0
    assert r.pitch_weight == 0.5
    assert r.pitch_reliability == "full"
    assert r.weight_note is None


# ---------------------------------------------------------------------------
# v3 · 真实 pyin 端到端（CI 已装 librosa）：用户整体低 3 半音 → 移调后高分
# ---------------------------------------------------------------------------
def test_pyin_scorer_v4_end_to_end(tmp_path, monkeypatch):
    """**修复前必失败**：真人（合成音替代）整体低 3 半音唱旋律 →
    v2 音准 ≈40；v3 移调 −3 半音后 ≥90（用户时间轴=参考+offset 同口径）。

    APP_TESTING 下 ``get_pitch_extractor`` 默认注入 Fake（恒 440Hz）——本用例
    必须显式切回真 pyin，否则检测的"整体移调"会被假工频污染（结构性走假路径）。
    """
    import soundfile as sf
    from app.audio.pitch import PyinPitchExtractor
    from app.audio.sing import PyinSingScorer

    monkeypatch.setattr("app.audio.pitch.get_pitch_extractor", lambda: PyinPitchExtractor())

    sr = 16000
    seg_s = 0.5
    ref_freqs = [440.0, 523.2511, 659.2551]  # A4 / C5 / E5
    user_freqs = [f * 2 ** (-300 / 1200.0) for f in ref_freqs]
    parts = []
    for f in user_freqs:
        t = np.linspace(0, seg_s, int(sr * seg_s), endpoint=False)
        parts.append(0.6 * np.sin(2 * np.pi * f * t))
    y = np.concatenate(parts).astype(np.float32)
    wav = tmp_path / "low3.wav"
    sf.write(str(wav), y, sr)

    n_frames = int(round(3 * seg_s * 1000 / HOP))  # 46.875 → 47
    ref_f0 = np.array([ref_freqs[min(2, int(i * HOP / (seg_s * 1000.0)))] for i in range(n_frames)])
    ref_lines = [
        {
            "seq": 1,
            "start_ms": 0,
            "end_ms": int(round(3 * seg_s * 1000)),
            "pitch_ref": {"f0s": list(ref_f0), "notes": [], "midi": []},
            "text": "la la la",
        }
    ]
    r = PyinSingScorer().score_sync(str(wav), ref_lines)
    assert r.alignment["version"] == "v6"
    assert r.alignment["time_warp_stretch"] > 0  # v6：时间弯折留痕
    assert r.alignment["windows_ms"], "v6：逐句用户时间轴窗口必须随 alignment 落库"
    assert r.alignment["transpose_semitones"] == -3
    assert r.alignment["range_hint"] and "降 3 个半音" in r.alignment["range_hint"]
    assert r.alignment["medfilt_kernel"] == 5
    assert r.alignment["ref_coverage"] == 1.0
    assert r.alignment["pitch_weight"] == 0.5
    assert "bpm_source" in r.alignment and "bpm_ratio" in r.alignment
    line = r.lines[0]
    assert line.pitch_score is not None
    assert line.pitch_score >= 90.0, f"移调后音准应 ≥90（实际 {line.pitch_score}）"


# ---------------------------------------------------------------------------
# 口径 v5（2026-09-10 P0）：R1 逐句判据 + 除零护栏
# ---------------------------------------------------------------------------
def test_onset_is_continuation_per_line_v5():
    """v5：句窗首帧落在「窗口前 ≥150ms 已开始的有声段」内 → 判延续（该句不给节奏分）。

    修复前（v4）：整轨只要任意一处 ≥150ms 静音即放行闸门（手机录音起始静音几乎必现），
    且 `_first_new_run` 对"窗口第 0 帧已有声"直接 `return 0` → onset_dev=0 →
    **rhythm 恒 95**（乱唱/完全不跟拍也拿 95）。判别素材：`[0]*31 + 连续有声`。
    """
    from app.audio.sing import (
        detect_onset_ms,
        has_breath_structure,
        onset_is_continuation,
        rhythm_score_from_dev,
    )

    hop = 32.0
    track = np.concatenate([np.zeros(31), np.full(300, 220.0)])  # 31 帧 ≈ 992ms 起始静音
    # v4 的整轨闸门此刻为真 —— 这正是绕过点（v5 不再依赖它做判据）
    assert has_breath_structure(track, hop) is True
    # 句窗起点落在有声段内部（frame_start=50，前 19 帧有声）→ 延续
    assert onset_is_continuation(track, 50, hop) is True
    # 窗口首帧无声 → 不是延续（交给 detect_onset_ms 正常定位新起唱）
    assert onset_is_continuation(track, 20, hop) is False
    # 边界：首帧 0 / 越界 / 空轨 → False（不误判）
    assert onset_is_continuation(track, 0, hop) is False
    assert onset_is_continuation(track, len(track), hop) is False
    assert onset_is_continuation(np.array([]), 1, hop) is False

    # 修复前的高分来源（保留断言以说明差异）：窗口全有声 → 0ms → 95
    all_voiced = np.full(120, 231.7)
    assert detect_onset_ms(all_voiced, None, hop) == 0.0
    assert rhythm_score_from_dev(0.0) == 95.0


def test_edge_continuous_singing_no_onset_per_line(tmp_path, monkeypatch):
    """v5 端到端判别：**起始静音 + 之后一口气唱到底** 的第二句不得再拿节奏 95。

    修复前（v4）：整轨存在起始 0.5s 静音 → `has_breath_structure=True` 放行；第二句窗口
    全是有声（用户没换气）→ `_first_new_run` 的 `start == 0` 分支 → onset_dev=0 → **rhythm=95**
    （乱唱/不跟拍恒高分的直接来源）。v5：句窗首帧前 150ms 已有声 → 判延续 → rhythm=None +
    reason='no_onset'；第一句（确实新起唱）仍应给节奏分。
    """
    import soundfile as sf
    from app.audio.pitch import PyinPitchExtractor
    from app.audio.sing import PyinSingScorer

    monkeypatch.setattr("app.audio.pitch.get_pitch_extractor", lambda: PyinPitchExtractor())

    sr = 16000
    # 每句 1s：参考第 1 句 [0,1000)、第 2 句 [1000,2000)
    ref_lines = [
        {
            "seq": 1,
            "start_ms": 0,
            "end_ms": 1000,
            "pitch_ref": {"f0s": [220.0] * 31, "notes": ["A3"] * 31, "midi": [57] * 31},
            "text": "la",
        },
        {
            "seq": 2,
            "start_ms": 1000,
            "end_ms": 2000,
            "pitch_ref": {"f0s": [220.0] * 31, "notes": ["A3"] * 31, "midi": [57] * 31},
            "text": "la",
        },
    ]
    # 用户：0.5s 静音 → 之后连续 2.5s 单音（**句间不换气**，正是 v4 的绕过形态）
    y = np.zeros(int(sr * 3.0), dtype=np.float32)
    t = np.arange(int(sr * 2.5)) / sr
    y[int(sr * 0.5) : int(sr * 0.5) + len(t)] = 0.5 * np.sin(2 * np.pi * 220.0 * t)
    wav = tmp_path / "continuous.wav"
    sf.write(str(wav), y, sr)

    r = PyinSingScorer().score_sync(str(wav), ref_lines)
    assert r.alignment["version"] == "v6"
    assert r.alignment["breath_structure"] is True  # 起始静音让"整轨换气结构"为真（旧闸门的破口）
    line2 = next(line for line in r.lines if line.seq == 2)
    assert line2.rhythm_score is None, "第二句无新起唱 → 不得给节奏分（修复前为 95）"
    assert line2.reason == "no_onset"
    # 第一句确有新起唱 → 保留节奏评分能力（不误杀）
    line1 = next(line for line in r.lines if line.seq == 1)
    assert line1.reason != "no_onset"


def test_user_coverage_excludes_no_ref_lines_v5_1():
    """P1-10（v5.1）：R3 覆盖率分母只算"有参考的句"——参考缺失不得二次惩罚用户。

    场景：6 句里 5 句参考缺失（no_ref）、用户把有参考的那句唱全。
    - 修复前：user_coverage = 1/6 = 0.167 → conf=0 → **不给综合分**，且 note 写
      「请完整演唱一遍再评」（把服务端缺参考说成用户漏唱）；
    - 修复后：分母 = 1（有参考句）→ user_coverage = 1.0 → 全额置信度；参考缺失由 item8
      的 weight_note 单独说明（分工不重复）。
    """
    from app.audio.sing import LineScore, aggregate_result

    lines = [
        LineScore(
            seq=1, start_ms=0, end_ms=1000, pitch_score=88.0, rhythm_score=80.0, pron_score=75.0
        )
    ]
    for seq in range(2, 7):
        lines.append(
            LineScore(
                seq=seq,
                start_ms=seq * 1000,
                end_ms=(seq + 1) * 1000,
                pitch_score=None,
                rhythm_score=None,
                pron_score=None,
                skipped=True,
                reason="no_ref",
                no_ref=True,
            )
        )
    r = aggregate_result(lines)
    assert r.user_coverage == 1.0, "分母含 no_ref 会让用户唱全也只有 0.167（修复前行为）"
    assert r.coverage_conf == 1.0 and r.coverage_note is None
    # 参考缺失仍由 item8 表达（wp 降为 0 → 音准不计入；不重复惩罚用户覆盖率）
    assert r.ref_coverage is not None and r.ref_coverage < 0.4
    assert r.pitch_weight == 0.0 and r.weight_note is not None


def test_user_coverage_still_penalises_real_misses_v5_1():
    """反向护栏：分母改为"有参考句"后，用户**真的漏唱**仍要降置信度/不给分。

    构造：4 句都有参考、用户只评了 2 句（另 2 句 no_pitch）→ 覆盖率 50%（40~80% 段）。
    """
    from app.audio.sing import LineScore, aggregate_result

    lines = [
        LineScore(
            seq=i,
            start_ms=i * 1000,
            end_ms=(i + 1) * 1000,
            pitch_score=90.0,
            rhythm_score=80.0,
            pron_score=None,
        )
        for i in range(1, 3)
    ]
    lines += [
        LineScore(
            seq=i,
            start_ms=i * 1000,
            end_ms=(i + 1) * 1000,
            pitch_score=None,
            rhythm_score=None,
            pron_score=None,
            skipped=True,
            reason="no_pitch",
        )
        for i in range(3, 5)
    ]
    r = aggregate_result(lines)
    assert r.user_coverage == 0.5, "4 句有参考、只评了 2 句 → 50%"
    assert r.coverage_conf is not None and 0 < r.coverage_conf < 1
    assert r.overall is not None  # 50% 属 40~80% 段，折算仍给分


def test_weighted_overall_zero_weight_guard_v5():
    """v5 依赖护栏：wp=0 且其余分项缺失 → None（修复前 ZeroDivisionError 使整次评分作废）。

    v5 逐句判据会让更多句子 rhythm=None；若参考覆盖 <40%（item8 → wp=0）且发音缺失，
    旧实现 `sum(...)/total_w` 除零 → `_run_attempt` 捕获 → status=failed、lines 不落库
    （用户看到"评分失败"，额度已扣）。依据：docs/06 §9.4、docs/11 Q-B08。
    """
    from app.audio.sing import _weighted_overall

    assert _weighted_overall(80.0, None, None, 0.0, 0.2, 0.3) is None  # wp=0 → total_w=0
    assert _weighted_overall(None, None, None, 0.5, 0.2, 0.3) is None  # 全缺失
    assert _weighted_overall(80.0, None, None, 0.5, 0.2, 0.3) == 80.0  # 正常路径不变
    # 节奏缺失但音准+发音在 → 按剩余权重归一（v5 常见形态）
    assert _weighted_overall(90.0, None, 70.0, 0.5, 0.2, 0.3) == round(
        (90.0 * 0.5 + 70.0 * 0.3) / 0.8, 2
    )


# ---------------------------------------------------------------------------
# 口径 v6（2026-09-10 F1 复测修复）：句窗端点时间弯折
# ---------------------------------------------------------------------------
def test_time_warp_maps_line_windows_into_user_breaths(tmp_path, monkeypatch):
    """**F1 核心**：用户偏慢 + 句间换气时，句窗起点必须落在换气静音里 → 才有"新起唱"。

    修复前必失败（v5）：`win_start = ref_start + offset_median` 只加全局中位偏移、起点不弯折 →
    偏慢演唱的后续句窗口落到**上一句句腹**（首帧已有声）→ `onset_is_continuation` 判延续 →
    `reason='no_onset'`、整首节奏 None（容器实测 ratio=0.826 素材即使有 372ms 换气也 6/6 句
    no_onset —— 根因是"有声"用 `f0>0` 判定，而 pyin 对静音大量判浊，换气被抹平）。
    判别素材：3 句 × 960ms 参考，用户**放慢 1.25× 并在每句之间插 384ms 静音**（真人换气形态）。
    """
    import soundfile as sf
    from app.audio.pitch import PyinPitchExtractor
    from app.audio.sing import PyinSingScorer

    monkeypatch.setattr("app.audio.pitch.get_pitch_extractor", lambda: PyinPitchExtractor())

    sr = 16000
    hop = HOP  # 32ms
    frame_ms = int(round(hop))
    line_frames = 30  # 960ms/句
    freqs = [220.0, 262.0, 330.0]
    ref_lines = [
        {
            "seq": i + 1,
            "start_ms": i * 960,
            "end_ms": (i + 1) * 960,
            "pitch_ref": {
                "f0s": [freqs[i]] * line_frames,
                "notes": ["A3"] * line_frames,
                "midi": [57] * line_frames,
            },
            "text": "la",
        }
        for i in range(3)
    ]
    # 用户：每句拉长 1.25×（1200ms）+ 句前 200ms 静音（换气）→ 总长 ≈ 200+1200+250+1200+250+1200
    stretch = 1.25
    seg_frames = int(round(line_frames * stretch))
    gap_frames = 12  # 384ms 静音（≈容器复测素材的 372ms 换气）
    gap_samples = int(
        round(gap_frames * hop / 1000 * sr)
    )  # 帧数 → 采样点（勿写成 gap_frames 个采样点）
    parts: list[np.ndarray] = [
        np.zeros(gap_samples, dtype=np.float32)
    ]  # 起唱前换气（首句也要有新起唱）
    for f in freqs:
        t = np.arange(int(seg_frames * hop / 1000 * sr)) / sr
        parts.append((0.5 * np.sin(2 * np.pi * f * t)).astype(np.float32))
        parts.append(np.zeros(gap_samples, dtype=np.float32))
    y = np.concatenate(parts)
    wav = tmp_path / "slow_gapped.wav"
    sf.write(str(wav), y, sr)

    r = PyinSingScorer().score_sync(str(wav), ref_lines)
    assert r.alignment["version"] == "v6"
    assert r.alignment["time_warp_stretch"] > 0  # 时间弯折参数留痕（具体值受 ±10% 带约束，不断言）
    windows = {int(w[0]): (w[1], w[2]) for w in r.alignment["windows_ms"]}
    assert set(windows) == {1, 2, 3}
    starts = [windows[k][0] for k in (1, 2, 3)]
    assert starts == sorted(starts), f"句窗必须单调（{starts}）"
    take_ms = len(y) / sr * 1000
    assert all(-1000 <= s <= take_ms for s in starts), f"句窗起点越界：{starts}"
    scored = [line for line in r.lines if line.rhythm_score is not None]
    assert len(scored) >= 2, (
        "偏慢 + 换气的演唱必须有节奏分（修复前 0 句：能量掩码缺失导致起唱判据恒判'延续'）；"
        f"实际 {len(scored)} 句，reasons={[line.reason for line in r.lines]}"
    )
    assert r.rhythm is not None
    assert frame_ms == 32  # 素材按 32ms 帧构造（文档化）


def test_time_warp_identity_for_aligned_take():
    """反向护栏：同步演唱（无拉伸/无静音）→ 恒等弯折（stretch≈1、offset≈0），不引入漂移。"""
    from app.audio.sing import align_time_warp

    rng = np.random.default_rng(7)
    base = np.concatenate([220.0 + 0.0 * np.arange(40), 330.0 + 0.0 * np.arange(40)])
    jitter = rng.normal(0, 0.5, size=base.shape)
    w = align_time_warp(base + jitter, base, HOP)
    assert abs(w.stretch - 1.0) <= 0.05, w.stretch
    assert abs(w.offset_ms) <= 2 * HOP, w.offset_ms
