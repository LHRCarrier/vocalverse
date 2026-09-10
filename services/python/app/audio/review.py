"""人工抽检一致性评审（Fermatean 模糊化 · docs/06 §9.4 SG-14）。

背景
----
SG-14 拍板「人工抽检：5 首 × 每首 5 句，2 人打 0-100，与算法相关 r≥0.7，出具验证报告进
答辩材料」。本模块把「评委各打一个 0~100 点值」升级为 **区间分 [lo, hi]**＋Fermatean
模糊集（FFS）编码：

- 评委只打区间（宽 0~100 的 `lo~hi`，区间宽度即犹豫度——直接点值无法表达"犹豫"）；
- 区间 → FFN(μ, ν)：``s=(lo+hi)/200``、``h=(hi−lo)/100``、``μ=s(1−h)``、``ν=(1−s)(1−h)``
  —— μ+ν=1−h ≤ 1 ⇒ μ³+ν³ ≤ (μ+ν)³ ≤ 1（Fermatean 立方约束**恒成立**，无参数漂移）；
- 得分函数 ``S=μ³−ν³``（Senapati–Yager 通式；文章 Definition 4 同型）→ 模糊期望
  ``E=(S+1)/2×100``（**对照列**：FF 期望是非线性压缩，评委打 90 区间中点显示 86.4，
  读者易困惑——评审主口径用透明的**区间中点**，FF 期望仅作高阶对照，见下）。

**犹豫口径说明（诚实边界）**：评审输入把「区间宽度 h」定义为犹豫度——它直接可解释
（评委敢打窄区间 = 自信）。Fermatean 理论余量 ``π=(1−μ³−ν³)^(1/3)`` **故意不作为
评审口径**：例如 (0.72, 0.08)（即 [80,100] 的编码）按公式 π≈0.855，远大于 h=0.2——
理论 π 度量的是"隶属/非隶属空间余量"，与"评委犹豫"不是同一语义，展示只会误导。

评审指标（全部可解释、可复现）：
1. r_hat / rho —— 区间中点 vs 算法分的 Pearson / Spearman（主口径，透明）；
2. r_ci —— **区间引导置信区间**（每句在 [lo,hi] 均匀采样 500 次重算 r，取 2.5/97.5%
   分位）：回答"r≥0.7 的结论对评委犹豫是否稳健"（点值做法没有这一问）；
3. interval_coverage —— 算法分落入专家区间内的句子比例（"模糊同意率"）；
4. expert_gap —— 两位评委中点差的均值（评审内部一致性：评委分歧大 → 评审本身弱）；
5. verdict: pass（r_ci 下界 ≥0.7）/ weak（r_hat≥0.7 但置信下界 <0.7）/ fail / insufficient（n<5）。

口径与边界
----------
- **纯演示/评审工具**：线上评分权重公式零影响（docs/06 §9.4 权重是组长拍板口径；
  alignment/API 均不涉及，OpenAPI 契约零 diff）；
- 论文参考：Zhao & Huang, *Sci Rep* (2026) s41598-026-46791-5（FF‑CRITIC‑MAIRCA：FFS 编码
  专家犹豫 + 偏差式可解释排序），本模块只取其「FFS 表达犹豫」思想，不引其 CRITIC/MAIRCA
  （那些面向多候选排序，与单用户单次跟唱的评审场景不匹配——见 docs/06 §9.4 注记）；
- 样本量：n<5 提示 insufficient（r 在两三名采样下无统计意义）。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: 通过线（docs/06 §9.4：与算法相关 r≥0.7）
PASS_R = 0.7
#: 专家内部分歧阈值（中点差 > 此值记为"评委间有分歧"，可解释用）
EXPERT_GAP_FLAG = 30.0
#: 置信区间引导次数（决定 r_ci 稳定度；500 次 × n 句，毫秒级）
BOOTSTRAP_N = 500


def ffn_from_interval(lo: float, hi: float) -> tuple[float, float, float]:
    """区间分 → (FFN(μ, ν), 犹豫度 h)。

    - s = (lo+hi)/200（区间中点归一）；h = (hi−lo)/100（区间宽度 = 评审犹豫度）；
    - μ = s·(1−h)，ν = (1−s)(1−h)；确定点分（lo=hi）退化 μ=s、ν=1−s（h=0 无犹豫）。
    """
    lo, hi = float(lo), float(hi)
    s = (lo + hi) / 200.0
    h = (hi - lo) / 100.0
    mu = s * (1.0 - h)
    nu = (1.0 - s) * (1.0 - h)
    return mu, nu, h


def ff_score(mu: float, nu: float) -> float:
    """FF 得分函数 S = μ³ − ν³（Senapati–Yager 通式；∈[−1,1]）。

    FFN(0.7, 0.3) → 0.343 − 0.027 = 0.316（论文示例值，单测锁定）。
    """
    return mu**3 - nu**3


def ff_expect(mu: float, nu: float) -> float:
    """模糊期望 E = (S+1)/2 × 100（映射回 0~100 分制，**对照列口径**——非线性压缩）。"""
    return (ff_score(mu, nu) + 1.0) / 2.0 * 100.0


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    return float(np.corrcoef(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float))[0, 1])


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    return float(np.corrcoef(_rank(xs), _rank(ys))[0, 1])


def _rank(vals: list[float]) -> list[float]:
    """秩（并列取平均秩；纯 numpy 避免 scipy 依赖——评审工具零新增依赖口径）。"""
    arr = np.asarray(vals, dtype=float)
    order = np.argsort(arr, kind="stable")
    ranks = np.empty(len(arr), dtype=float)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and arr[order[j + 1]] == arr[order[i]]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    return list(ranks)


def bootstrap_r_ci(rows: list[dict], n: int = BOOTSTRAP_N, seed: int = 42) -> tuple[float, float]:
    """区间引导置信区间：每句在 [lo,hi] 均匀采样 → 重算 Pearson → 2.5/97.5 分位。

    确定区间（lo=hi）退化为点采样 → r 恒定（r_ci 宽度 = 0，诚实反映"无犹豫"）。
    """
    algo = [float(r["algo"]) for r in rows]
    gen = np.random.default_rng(seed)
    lo = np.asarray([float(r["r1_lo"]) for r in rows], dtype=float)
    hi = np.asarray([float(r["r1_hi"]) for r in rows], dtype=float)
    rs = np.empty(n, dtype=float)
    for k in range(n):
        sample = gen.uniform(lo, hi)
        rs[k] = pearson(algo, list(sample)) or 0.0
    return float(np.percentile(rs, 2.5)), float(np.percentile(rs, 97.5))


@dataclass
class LineReview:
    """单句评审明细（报告逐句行）。"""

    seq: int
    algo: float
    r1_lo: float
    r1_hi: float
    r2_lo: float
    r2_hi: float
    mid1: float
    mid2: float
    mu1: float
    nu1: float
    h1: float  # 评委1 犹豫度（区间宽归一；口径见模块 docstring「犹豫口径说明」）
    mu2: float
    nu2: float
    h2: float
    expect1: float
    expect2: float
    covered: bool  # 算法分 ∈ 评委1区间（模糊同意）
    expert_gap: float  # 两位评委中点差

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "algo": round(self.algo, 1),
            "r1": f"{self.r1_lo:.0f}~{self.r1_hi:.0f}",
            "r2": f"{self.r2_lo:.0f}~{self.r2_hi:.0f}",
            "mid1": round(self.mid1, 1),
            "mid2": round(self.mid2, 1),
            "ffn1": f"({self.mu1:.2f},{self.nu1:.2f}) h={self.h1:.2f}",
            "ffn2": f"({self.mu2:.2f},{self.nu2:.2f}) h={self.h2:.2f}",
            "expect1": round(self.expect1, 1),
            "expect2": round(self.expect2, 1),
            "covered": self.covered,
            "expert_gap": round(self.expert_gap, 1),
        }


def review_rows(rows: list[dict]) -> dict:
    """一首歌的评审：rows = [{seq, algo, r1_lo, r1_hi, r2_lo, r2_hi}, ...]。

    主口径用**区间中点**（透明：评委打 90 报告显示 90）；FF 期望（`expect1/2`）
    与 FFN（含犹豫 h）为**对照列**（高阶评审与答辩讲解用）。verdict 以 r_ci 下界判定。
    """
    items: list[LineReview] = []
    mids1: list[float] = []
    mids2: list[float] = []
    gaps: list[float] = []
    covered_n = 0
    for r in rows:
        lo1, hi1, lo2, hi2 = (float(r[k]) for k in ("r1_lo", "r1_hi", "r2_lo", "r2_hi"))
        mu1, nu1, h1 = ffn_from_interval(lo1, hi1)
        mu2, nu2, h2 = ffn_from_interval(lo2, hi2)
        mid1 = (lo1 + hi1) / 2.0
        mid2 = (lo2 + hi2) / 2.0
        gap = abs(mid1 - mid2)
        covered = float(r["algo"]) >= lo1 and float(r["algo"]) <= hi1
        items.append(
            LineReview(
                seq=int(r.get("seq", len(items) + 1)),
                algo=float(r["algo"]),
                r1_lo=lo1,
                r1_hi=hi1,
                r2_lo=lo2,
                r2_hi=hi2,
                mid1=mid1,
                mid2=mid2,
                mu1=mu1,
                nu1=nu1,
                h1=h1,
                mu2=mu2,
                nu2=nu2,
                h2=h2,
                expect1=ff_expect(mu1, nu1),
                expect2=ff_expect(mu2, nu2),
                covered=covered,
                expert_gap=gap,
            )
        )
        mids1.append(mid1)
        mids2.append(mid2)
        gaps.append(gap)
        if covered:
            covered_n += 1

    n = len(items)
    algo = [float(r["algo"]) for r in rows]
    r_hat = pearson(algo, mids1)
    rho = spearman(algo, mids1)
    if n >= 5 and r_hat is not None:
        ci_lo, ci_hi = bootstrap_r_ci(rows)
    else:
        ci_lo, ci_hi = (float("nan"), float("nan"))  # n<5：统计意义不足
    if n < 5:
        verdict = "insufficient"
    elif ci_lo >= PASS_R:
        verdict = "pass"
    elif (r_hat or -1.0) >= PASS_R:
        verdict = "weak"
    else:
        verdict = "fail"
    return {
        "n": n,
        "pearson": round(r_hat, 3) if r_hat is not None else None,
        "spearman": round(rho, 3) if rho is not None else None,
        "r_ci": [round(ci_lo, 3), round(ci_hi, 3)],
        "interval_coverage": round(covered_n / n, 3) if n else None,
        "expert_gap": round(float(np.mean(gaps)), 1) if gaps else None,
        "verdict": verdict,
        "lines": [it.to_dict() for it in items],
    }


def format_report(song_title: str, result: dict) -> str:
    """评审结果 → Markdown 小节（CLI 报告用；统计口径全可解释）。"""
    verdict_cn = {
        "pass": "**通过**",
        "weak": "**弱通过（区间化不确定）**",
        "fail": "**未达标**",
        "insufficient": "**样本不足**",
    }
    verdict = result["verdict"]
    lines: list[str] = [
        f"### {song_title}（n={result['n']} 句）",
        "",
        f"- Pearson r = {result['pearson']}（区间中点口径）｜Spearman ρ = {result['spearman']}",
        "- **r 置信区间 [2.5%, 97.5%] = "
        f"[{result['r_ci'][0]}, {result['r_ci'][1]}]**（区间引导 500 次；"
        f"下界 ≥0.7 才算**通过**——评委犹豫下 r≥{PASS_R} 的稳健性）",
        f"- 模糊同意率（算法分 ∈ 评委1区间）= {result['interval_coverage']:.0%}；"
        f"评委内部分歧均值 = {result['expert_gap']} 分（>{EXPERT_GAP_FLAG:.0f} 记评审偏弱）",
        f"- 判定：{verdict_cn.get(verdict, verdict)}",
        "",
        "| # | 算法分 | 评委1 区间 | 评委2 区间 | FFN(评委1) μ,ν,h | FF 期望 | 一致 |",
        "|---:|---:|---|---|---|---|---|",
    ]
    for it in result["lines"]:
        marks = "✔" if it["covered"] else "✘"
        lines.append(
            f"| {it['seq']} | {it['algo']} | {it['r1']} (中 {it['mid1']}) | "
            f"{it['r2']} (中 {it['mid2']}) | {it['ffn1']} | {it['expect1']} | {marks} |"
        )
    return "\n".join(lines)


def render_dataset(songs: list[tuple[str, list[dict]]]) -> str:
    """多首汇总报告（CLI 输出）：各首小节 + 汇总结论表。"""
    parts: list[str] = ["# 人工抽检一致性评审报告（FF 模糊化 · docs/06 §9.4 SG-14）", ""]
    summary: list[str] = []
    for title, rows in songs:
        res = review_rows(rows)
        parts.append(format_report(title, res))
        summary.append(
            f"| {title} | {res['n']} | {res['pearson']} | "
            f"{res['r_ci'][0]}~{res['r_ci'][1]} | {res['verdict']} |"
        )
    parts.extend(
        [
            "## 汇总",
            "",
            "| 歌曲 | 句数 | r | r 置信区间 | 判定 |",
            "|---|---:|---:|---|---|",
            *summary,
            "",
            f"> 口径：主口径 = 区间中点 vs 算法分 Pearson；"
            f"r 置信区间 = 评委区间内均匀采样 ×{BOOTSTRAP_N}；"
            f"通过线 r≥{PASS_R}（docs/06 §9.4 SG-14）；FF 期望为对照列（非线性压缩，非主口径）。",
        ]
    )
    return "\n".join(parts)
