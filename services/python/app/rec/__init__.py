"""规则推荐引擎模块（Python 写方）：推荐匹配。

- service.recommend_shadow：主窗 [L,L+1] + 扩档 + L4 复习席 + 曝光埋点（2026-09-21 酒馆迁移后
  仅影子跟读；场景推荐 recommend_scenes 随英语场景对话移除）。
- service.invalidate_recommendation_cache：主动失效（水平/掌握度/难度变更后调用）。
"""

from .service import (
    invalidate_recommendation_cache,
    recommend_shadow,
    resolve_level,
)

__all__ = [
    "recommend_shadow",
    "resolve_level",
    "invalidate_recommendation_cache",
]
