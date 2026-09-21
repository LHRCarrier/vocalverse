"""控制台 · 学习指标端点（docs/53 P2）：``/api/v1/console/insight/**``。

- 只读聚合（口径 = ``app/insight/service.py``，与用户端 ``/api/v1/stats/*`` 同源，避免双实现漂移）；
- 权限码复用 ``ops:metric:read``（2026-09-21 决策：学习指标看板与「性能指标」同属指标读权限，
  不新增权限码——新增需同步 PermissionCatalog/RbacBootstrap/docs/50 §4.2 目录计数与角色发放，
  在本轮 demo 范围内收益低；若上游要独立码，按 docs/50 §4.2 流程补 ``ops:insight:read``）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.console.api.deps import ConsoleAdmin, console_guard
from app.core.response import ok
from app.db import get_session_factory
from app.insight import service as insight

router = APIRouter(prefix="/api/v1/console/insight", tags=["console-insight"])


@router.get("/overview")
async def insight_overview(
    days: int = Query(default=30, ge=1, le=180),
    admin: ConsoleAdmin = Depends(console_guard(perm="ops:metric:read")),
):
    db = get_session_factory()()
    try:
        data = insight.overview(db, days=days)
        data["requested_by"] = admin.username or str(admin.admin_id)
        return ok(data)
    finally:
        db.close()
