"""推荐路由（local/31 §4.3 · local/29 §9）：GET /api/v1/recommendations。

按类型返回推荐位：scene（默认 6）/ shadow（默认 3）；规则引擎内部已做曝光埋点（events）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user_id
from app.core.response import ok
from app.rec.service import recommend_scenes, recommend_shadow

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


@router.get("")
async def recommendations(
    type: str = Query("scene", pattern="^(scene|shadow)$"),
    limit: int | None = Query(default=None, ge=1, le=20),
    user_id: int = Depends(get_current_user_id),
):
    """推荐列表。type=scene 返回场景，type=shadow 返回影子跟读；limit 覆盖默认条数。"""
    if type == "scene":
        items = recommend_scenes(user_id, limit)
    else:
        items = recommend_shadow(user_id, limit)
    return ok({"type": type, "items": items})
