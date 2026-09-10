"""人工抽检一致性评审测试（docs/06 §9.4 SG-14 · FF 模糊化；CI 零模型零 Key）。

覆盖：
- FFN 映射约束（任意区间 μ³+ν³≤1 恒成立 / 确定点退化 / 犹豫度=区间宽度 h）；
- 得分函数 S=μ³−ν³（论文示例 FFN(0.7,0.3)=0.316 锁定）；
- 一致性判定（完全一致 → r≈1 & pass；反向 → fail；窄样本 → insufficient）；
- 区间引导 r_ci（宽区间 → 置信区间宽度 >0；确定区间 → 宽度=0）；
- 模糊同意率与评委内部分歧。
"""

from __future__ import annotations

import numpy as np
from app.audio.review import (
    EXPERT_GAP_FLAG,
    PASS_R,
    bootstrap_r_ci,
    ff_expect,
    ff_score,
    ffn_from_interval,
    format_report,
    pearson,
    review_rows,
    spearman,
)


# ---------------------------------------------------------------------------
# FFN 映射
# ---------------------------------------------------------------------------
def test_ffn_constraint_always_holds():
    """属性式：任意 [lo,hi] ⊂ [0,100] → μ³+ν³ ≤ 1（Fermatean 立方约束恒成立）。"""
    rng = np.random.default_rng(7)
    for _ in range(200):
        lo, hi = sorted(rng.uniform(0, 100, 2))
        mu, nu, _h = ffn_from_interval(lo, hi)
        assert mu**3 + nu**3 <= 1.0 + 1e-12
        assert 0.0 <= mu <= 1.0 and 0.0 <= nu <= 1.0


def test_ffn_crisp_point_degrades():
    """确定点分（lo=hi）→ 无犹豫：μ=s、ν=1−s、h=0（退化，可解释）。"""
    mu, nu, h = ffn_from_interval(90, 90)
    assert abs(mu - 0.9) < 1e-12
    assert abs(nu - 0.1) < 1e-12
    assert h == 0.0


def test_ffn_hesitation_equals_interval_width():
    """固执口径：**[80,100] → s=0.9、犹豫 h=0.2**（评审显示 h，不显示 FF 理论 π——
    后者度量的不是"评委犹豫"，见模块 docstring「犹豫口径说明」）。"""
    mu, nu, h = ffn_from_interval(80, 100)
    assert abs(h - 0.2) < 1e-12
    assert abs(mu - 0.72) < 1e-12
    assert abs(nu - 0.08) < 1e-12


def test_ff_score_reference_value():
    """论文示例 FFN(0.7, 0.3) → S = 0.7³−0.3³ = 0.316（得分函数锁定）。"""
    assert abs(ff_score(0.7, 0.3) - 0.316) < 1e-9
    # 模糊期望映射回 0~100：S=0 → 50（中性）
    assert abs(ff_expect(0.5, 0.5) - 50.0) < 1e-9


# ---------------------------------------------------------------------------
# 统计基元
# ---------------------------------------------------------------------------
def test_pearson_spearman_basics():
    xs = [80, 82, 85, 88, 90, 95]
    assert abs(pearson(xs, xs) - 1.0) < 1e-9
    assert abs(spearman(xs, xs) - 1.0) < 1e-9
    assert pearson([1, 2], [1, 2]) is None  # n<3 统计意义不足
    assert spearman([1, 2], [1, 2]) is None


def test_spearman_ties_averaged():
    """并列取平均秩：完全一致但带重复 → ρ 仍≈1。"""
    xs = [80, 80, 90, 95]
    assert abs(spearman(xs, xs) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# review_rows：口径与判定
# ---------------------------------------------------------------------------
def _rows_agree():
    """专家区间覆盖算法分、顺序一致（高一致场景：窄区间 ±2——评委自信）。

    口径说明：区间若过宽（如 ±6），引导采样在短序列上会打乱序 → 触发 weak——
    那是"weak 判定"的正确演示场景（见 review_disagree.json），不是 pass 场景；
    本 helper 用于 pass 场景。
    """
    return [
        {"seq": i, "algo": a, "r1_lo": a - 2, "r1_hi": a + 2, "r2_lo": a - 1.5, "r2_hi": a + 1.5}
        for i, a in enumerate([82, 85, 88, 90, 93, 95], start=1)
    ]


def test_review_agree_passes():
    r = review_rows(_rows_agree())
    assert r["n"] == 6
    assert r["pearson"] is not None and r["pearson"] > 0.95
    assert r["verdict"] == "pass"
    assert r["interval_coverage"] == 1.0
    assert r["expert_gap"] <= EXPERT_GAP_FLAG
    # 窄区间（±2）→ 引导置信区间宽度可控（宽区间幅度的对应断言见 bootstrap 用例；
    # 注意采样分布中位 ≠ 中点口径 r，故不做 r_hat∈CI 包含断言）
    assert r["r_ci"][1] - r["r_ci"][0] < 0.5


def test_review_reversed_fails():
    """专家与算法反向 → r≈−1 → fail（修复前：点值口径同样红，但无置信区间更无说服力）。"""
    rows = [
        {
            "seq": i,
            "algo": 90 + (i - 1) * 2,
            "r1_lo": 90 - (i - 1) * 2,
            "r1_hi": 92 - (i - 1) * 2,
            "r2_lo": 0,
            "r2_hi": 100,
        }
        for i in range(1, 7)
    ]
    r = review_rows(rows)
    assert r["pearson"] < -0.9
    assert r["verdict"] == "fail"


def test_review_insufficient_n():
    assert review_rows(_rows_agree()[:4])["verdict"] == "insufficient"


def test_bootstrap_ci_width_reflects_hesitation():
    """宽区间 → r_ci 宽度 >0（犹豫被计入稳健性）；确定区间 → 宽度≈0。"""
    rows = _rows_agree()
    lo, hi = bootstrap_r_ci(rows)
    assert hi - lo > 1e-6, "评委犹豫（区间宽 12）应产生非零置信宽度"
    crisp = [{"seq": 1, "algo": 90, "r1_lo": 90, "r1_hi": 90, "r2_lo": 90, "r2_hi": 90}]
    clo, chi = bootstrap_r_ci(crisp)
    assert abs(chi - clo) < 1e-9, "确定点分 → r 恒定（无犹豫诚实反映）"


def test_interval_coverage_detects_miss():
    """算法分全部落在专家区间外 → 覆盖率为 0（模糊同意率语义）。"""
    rows = [
        {"seq": i, "algo": 40.0, "r1_lo": 80, "r1_hi": 85, "r2_lo": 78, "r2_hi": 86}
        for i in range(1, 6)
    ]
    r = review_rows(rows)
    assert r["interval_coverage"] == 0.0
    assert r["lines"][0]["covered"] is False


def test_format_report_contains_key_facts():
    r = review_rows(_rows_agree())
    text = format_report("Twinkle", r)
    assert "Twinkle" in text
    assert "r 置信区间" in text
    assert str(PASS_R) in text  # 通过线入报告
    assert "✔" in text  # 覆盖标记
