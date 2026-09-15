"""素材难度评价模块（Python 写方）：专家规则标定。

- rules.scenario_prior：场景语料专家先验（词汇/句法/发音三维度，CEFR 锚定 + λ 聚合）。
- rules.shadow_prior：影子跟读三维度（语速/停顿/连读）归一化（local/28 §2.2）。
"""

from .rules import (
    COMMON_LEARNER,
    dim_to_100,
    pron_score,
    scenario_prior,
    shadow_prior,
    syntax_score,
    vocab_score,
)

__all__ = [
    "scenario_prior",
    "shadow_prior",
    "vocab_score",
    "syntax_score",
    "pron_score",
    "dim_to_100",
    "COMMON_LEARNER",
]
