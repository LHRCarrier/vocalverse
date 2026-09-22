"""素材难度评价模块（Python 写方）：专家规则标定。

- rules.shadow_prior：影子跟读三维度（语速/停顿/连读）归一化（local/28 §2.2）。

2026-09-21（酒馆迁移）：场景语料专家先验（scenario_prior）随英语场景对话移除；
material_difficulty 现仅服务 shadow 推荐候选（level 兜底）。
"""

from .rules import COMMON_LEARNER, dim_to_100, shadow_prior

__all__ = ["shadow_prior", "dim_to_100", "COMMON_LEARNER"]
