"""学习指标路由（docs/53 P2）：四指标看板 + 个人学习报表。

- ``GET /api/v1/stats/overview``：平台四指标（CTR/完成率/互动率/跳出率）+ 趋势 + 维度 TopN
  —— 口径见 ``app/insight/service.py``（docs/06 §9.1 修订）；demo 产品内 `/stats` 报表页消费；
- ``GET /api/v1/stats/me``：个人报表（概览/趋势/五维雷达）——同一页面的「我的学习」区。

两者均要求学习者登录（``get_current_user_id``）；管理端看板走控制台端点
``/api/v1/console/insight/overview``（Python 控制台令牌 + 权限码，见
``console/api/routes/insight.py``）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.core.response import ok
from app.db import get_session_factory
from app.insight import learn as learn_insight
from app.insight import service as insight
from app.rec.level_model import forecast

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


@router.get("/learn")
async def stats_learn(
    user_id: int = Depends(get_current_user_id),
):
    """学习主页画像（docs/53 P4）：一句话画像 + 热力图 + 四模块摘要。"""
    db = _db()
    try:
        data = learn_insight.learn_overview(db, user_id)
        data["forecast"] = forecast(db, user_id)  # 学习主页进步趋势（docs/06 §9.5）
        return ok(data)
    finally:
        db.close()


@router.get("/learn/{module}")
async def stats_learn_module(
    module: str,
    days: int = Query(default=30, ge=1, le=180),
    user_id: int = Depends(get_current_user_id),
):
    """模块详情（words/community/speaking/practice）——未知模块 40001。"""
    if module not in learn_insight.MODULES:
        raise HTTPException(status_code=400, detail="unknown module")
    db = _db()
    try:
        return ok(learn_insight.learn_module(db, user_id, module, days=days))
    finally:
        db.close()


@router.get("/me")
async def stats_me(
    days: int = Query(default=30, ge=1, le=180),
    user_id: int = Depends(get_current_user_id),
):
    db = _db()
    try:
        data = insight.me(db, user_id, days=days)
        data["forecast"] = forecast(db, user_id, days=days)  # docs/06 §9.5 水平预测（进步趋势展示）
        return ok(data)
    finally:
        db.close()
