"""推荐路由（local/31 §4.3 · local/29 §9）：GET /api/v1/recommendations。

2026-09-21（酒馆迁移）：`type=scene`（场景推荐）随英语场景对话移除，仅保留
`type=shadow`（影子跟读素材，默认 3 条）；曝光埋点在内部函数落表（events）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user_id
from app.core.response import ok
from app.rec.service import recommend_shadow

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


@router.get("")
async def recommendations(
    type: str = Query("shadow", pattern="^shadow$"),
    limit: int | None = Query(default=None, ge=1, le=20),
    user_id: int = Depends(get_current_user_id),
):
    """推荐列表（type=shadow 影子跟读素材；limit 缺省按配置）。"""
    items = await recommend_shadow(user_id, limit)
    return ok({"type": "shadow", "items": items})
