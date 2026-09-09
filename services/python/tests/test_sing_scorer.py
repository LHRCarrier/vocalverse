"""唱歌评分核心测试（docs/06 §9.4：映射/DTW/降权公式；CI 零模型零 Key）。

覆盖：音准/节奏分段线性映射边界；cent 偏差；DTW 对齐（人造序列已知平移）；
aggregate 缺失降权（有效句均分/skipped 不入/is_complete 80% 阈值/0.5·0.2·0.3 复算）；
FakeSingScorer 结构契约（lines/alignment/user_f0）。
"""

from __future__ import annotations

import numpy as np
from app.audio.sing import (
    LineScore,
    _cent_deviation,
    aggregate_result,
    align_frames,
    pitch_score_from_cent,
    rhythm_score_from_dev,
    time_deviation_ms,
)


def test_pitch_score_bands():
    # docs/06 §9.4：≤50→90+ / ≤100→70~90 / ≤200→50~65 / >300→<40
    assert pitch_score_from_cent(0) == 95.0
    assert pitch_score_from_cent(50) == 95.0
    assert 70 <= pitch_score_from_cent(100) <= 90
    assert abs(pitch_score_from_cent(100) - 70.0) < 1e-6
    assert abs(pitch_score_from_cent(200) - 50.0) < 1e-6
    assert 40 <= pitch_score_from_cent(300) <= 50
    assert pitch_score_from_cent(400) < 40
    assert pitch_score_from_cent(400) >= 0


def test_rhythm_score_bands():
    # docs/06 §9.4：≤150→90+ / ≤300→75~90 / ≤600→55~75 / >1000→<50
    assert rhythm_score_from_dev(0) == 95.0
    assert rhythm_score_from_dev(150) == 95.0
    assert abs(rhythm_score_from_dev(300) - 75.0) < 1e-6
    assert abs(rhythm_score_from_dev(600) - 55.0) < 1e-6
    assert rhythm_score_from_dev(1000) == 40.0
    assert rhythm_score_from_dev(1500) < 50
    assert rhythm_score_from_dev(1500) >= 0


def test_cent_deviation_same_and_octave():
    ref = np.full(20, 440.0)
    same = np.full(20, 440.0)
    octave_up = np.full(20, 880.0)
    assert _cent_deviation(same, ref) == 0.0
    assert abs(_cent_deviation(octave_up, ref) - 1200.0) < 1.0
    # 有效帧 <3 → None（缺失降权 D5）
    assert _cent_deviation(np.array([0.0] * 20), ref) is None


def test_align_frames_identical_tracks():
    """相同序列 → offset≈0、bpm_ratio≈1（无伪造偏置）。"""
    f0 = np.concatenate([np.full(10, 200.0), np.full(40, 440.0), np.full(10, 300.0)])
    ratio, offset = align_frames(f0, f0, 32.0)
    assert abs(ratio - 1.0) < 1e-6
    assert abs(offset) <= 32.0


def test_align_frames_recovers_shift():
    """用户序列延迟 shift 帧 → offset ≈ shift × hop（DTW 对齐可解释性）。"""
    base = np.concatenate([np.full(10, 220.0), np.full(40, 440.0), np.full(10, 330.0)])
    shift = 5
    shifted = np.concatenate([np.zeros(shift, dtype=float), base[: -shift]])
    ratio, offset = align_frames(shifted, base, 32.0)
    assert abs(offset - shift * 32.0) <= 32.0


def test_time_deviation_ms_compensates_bpm():
    # bpm_ratio = ref时长/user时长：慢 10% → ratio=1000/1100，补偿后偏差≈0
    assert abs(time_deviation_ms(1000.0, 1100.0, 1000.0 / 1100.0) - 0.0) < 0.01
    assert time_deviation_ms(1000.0, 1200.0, 1.0) == 200.0


def test_aggregate_missing_downgrade():
    """D5：skipped 不入均分；overall=0.5·音准+0.2·节奏+0.3·发音复算。"""
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
            reason="no_pitch",
        ),
    ]
    r = aggregate_result(lines)
    # 有效句均分：pitch=(90+60)/2=75；rhythm=(80+50)/2=65；pron=70
    assert r.pitch == 75.0
    assert r.rhythm == 65.0
    assert r.pron == 70.0
    assert abs(r.overall - (0.5 * 75.0 + 0.2 * 65.0 + 0.3 * 70.0)) < 1e-6
    assert r.evaluated_lines == 2
    # is_complete：3 句有效 2 句 = 66.7% < 80%
    assert r.is_complete is False


def test_aggregate_complete_threshold_and_weight_normalize():
    """80% 阈值：4/5 有效 → True；分项缺失按剩余权重归一。"""
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
    """只有音准/节奏 → overall 按 0.5:0.2 归一（0.7 权重和）。"""
    lines = [
        LineScore(
            seq=1, start_ms=0, end_ms=1000, pitch_score=90.0, rhythm_score=80.0, pron_score=None
        ),
    ]
    r = aggregate_result(lines)
    assert abs(r.overall - (90.0 * 0.5 + 80.0 * 0.2) / 0.7) < 0.01  # 聚合保留 2 位小数
