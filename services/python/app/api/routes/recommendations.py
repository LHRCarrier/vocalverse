"""推荐路由（local/31 §4.3 · local/29 §9 · docs/53 P3）：GET /api/v1/recommendations。

- ``type=shadow``（默认）：影子跟读素材（2026-09-21 酒馆迁移后仅保留该类型）；
- ``type=items``（2026-09-21 新增）：跨类内容推荐（歌/书/酒馆场景卡）——内容型冷启动基线，
  见 ``app/rec/items.py``；曝光埋点 ``recommend_impression`` 在内部落表（CTR 口径 docs/06 §9.1）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user_id
from app.core.response import ok
from app.db import get_session_factory
from app.rec.items import recommend_items
from app.rec.service import recommend_shadow

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


@router.get("")
async def recommendations(
    type: str = Query("shadow", pattern="^(shadow|items)$"),
    limit: int | None = Query(default=None, ge=1, le=20),
    kind: str | None = Query(default=None, pattern="^(song|book|card)$"),
    user_id: int = Depends(get_current_user_id),
):
    """推荐列表：shadow = 影子跟读素材；items = 跨类内容推荐（歌/书/场景卡）。"""
    if type == "items":
        db = get_session_factory()()
        try:
            data = recommend_items(db, user_id, limit=limit or 3, kind=kind)
            return ok({"type": "items", **data})
        finally:
            db.close()
    items = await recommend_shadow(user_id, limit)
    return ok({"type": "shadow", "items": items})
