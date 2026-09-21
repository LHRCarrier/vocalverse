"""学习指标路由（docs/53 P2）：四指标看板 + 个人学习报表。

- ``GET /api/v1/stats/overview``：平台四指标（CTR/完成率/互动率/跳出率）+ 趋势 + 维度 TopN
  —— 口径见 ``app/insight/service.py``（docs/06 §9.1 修订）；demo 产品内 `/stats` 报表页消费；
- ``GET /api/v1/stats/me``：个人报表（概览/趋势/五维雷达）——同一页面的「我的学习」区。

两者均要求学习者登录（``get_current_user_id``）；管理端看板走控制台端点
``/api/v1/console/insight/overview``（Python 控制台令牌 + 权限码，见 console/api/routes/insight.py）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.core.response import ok
from app.db import get_session_factory
from app.insight import service as insight

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


def _db() -> Session:
    return get_session_factory()()


@router.get("/overview")
async def stats_overview(
    days: int = Query(default=30, ge=1, le=180),
    _user_id: int = Depends(get_current_user_id),
):
    db = _db()
    try:
        return ok(insight.overview(db, days=days))
    finally:
        db.close()


@router.get("/me")
async def stats_me(
    days: int = Query(default=30, ge=1, le=180),
    user_id: int = Depends(get_current_user_id),
):
    db = _db()
    try:
        return ok(insight.me(db, user_id, days=days))
    finally:
        db.close()
