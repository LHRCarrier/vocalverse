"""手动打卡：聚合当日练习 → 委托 Java 物化打卡卡（docs/37 §5 · docs/21 §4）。

口径（2026-09-21 组长反馈改版；2026-09-21 酒馆迁移修订）：
- **不再由练习收尾自动触发**（旧 complete_session 挂钩已移除）；用户在打卡页显式
  ``POST /api/v1/checkin`` 才落卡——「没操作却自动打卡」的根因即旧自动委托；
- **练习量口径**（酒馆迁移后）：``practiceCount`` = 当日酒馆回合数（玩家行动数，
  ``trpg_messages`` role=user 且 kind=text）+ 当日已完成的其他类型会话数
  （影子/答辩/唱歌——dialog 已随英语场景对话移除）；``overall/pron/gram/fluency`` 取
  当日 attempts 的最佳/最新（酒馆无评分，不影响打卡）；
- **幂等**：同一 practice_date 重复打卡只刷新当日聚合快照——``practiceCount`` 显式回传
  当日聚合值，Java 侧按值写入而非自增，重复调用不会重复计数；
- **日期**：默认 UTC 当天（与既有物化数据同口径）；客户端可传本地日期（YYYY-MM-DD）；
- **失败语义**：Java 不可达 → 50002 明确失败。打卡是用户主动操作，必须有反馈；
  旧收尾挂钩的「静默容忍失败」不再适用。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.core.internal_client import post_internal
from app.core.response import BizError
from app.db import get_session_factory
from app.models import Attempt
from app.models import Session as DbSession
from app.models.base import SessionKinds, SessionStatus
from app.models.trpg import TrpgCampaign, TrpgMessage
from sqlalchemy import func, select

logger = logging.getLogger("vocalverse")


def parse_practice_date(raw: str | None) -> date:
    """客户端日期（YYYY-MM-DD）→ date；缺省 UTC 当天；非法 42201。"""
    if not raw:
        return datetime.now(UTC).date()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise BizError(http_status=422, code=42201, message="date 需为 YYYY-MM-DD") from exc


def perform_checkin(user_id: int, day: date) -> dict:
    """聚合当日练习并委托 Java 落卡；返回打卡结果（date/practiceCount/overall）。"""
    db = get_session_factory()()
    try:
        practice_count, session_id, snapshot = _aggregate_day(db, user_id, day)
    finally:
        db.close()

    payload = {
        "userId": user_id,
        "practiceDate": day.isoformat(),
        "sessionId": session_id,
        "snapshot": snapshot,
    }
    try:
        post_internal("/internal/checkin", payload)
    except Exception as exc:
        logger.warning("manual checkin delegate failed user=%s day=%s: %s", user_id, day, exc)
        raise BizError(http_status=500, code=50002, message="打卡失败，请稍后重试") from exc
    return {
        "date": day.isoformat(),
        "practiceCount": practice_count,
        "overall": snapshot["overall"],
    }


def _aggregate_day(db, user_id: int, day: date) -> tuple[int, int | None, dict]:
    """当日练习聚合（UTC 日界）：酒馆回合数 + 已完成会话数 + 评分快照（最佳/最新）。

    口径（2026-09-21 酒馆迁移修订）：
    - 酒馆回合 = 当日 ``trpg_messages``（role=user、kind=text，即玩家行动数）；
    - 其他会话 = 当日完成的非 dialog 会话（影子/答辩/唱歌；dialog 已移除）；
    - 评分 = 当日 attempts（任意 kind）最佳 overall + 最新子分；酒馆不产分不参与。
    无练习时 practice_count=0、分数为空——仍允许打卡（卡面只显示「今日已打卡」）。
    """
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    completed_key = func.coalesce(DbSession.completed_at, DbSession.created_at)
    sessions = list(
        db.execute(
            select(DbSession)
            .where(
                DbSession.user_id == user_id,
                DbSession.kind != SessionKinds.DIALOG,
                DbSession.status == SessionStatus.COMPLETED,
                completed_key >= start,
                completed_key < end,
            )
            .order_by(DbSession.id.desc())
        )
        .scalars()
        .all()
    )
    trpg_turns = int(
        db.execute(
            select(func.count())
            .select_from(TrpgMessage)
            .join(TrpgCampaign, TrpgCampaign.id == TrpgMessage.campaign_id)
            .where(
                TrpgCampaign.user_id == user_id,
                TrpgMessage.role == "user",
                TrpgMessage.kind == "text",
                TrpgMessage.created_at >= start,
                TrpgMessage.created_at < end,
            )
        ).scalar_one()
    )
    attempts = list(
        db.execute(
            select(Attempt)
            .where(
                Attempt.user_id == user_id,
                Attempt.created_at >= start,
                Attempt.created_at < end,
                Attempt.overall_score.is_not(None),
            )
            .order_by(Attempt.id.desc())
        )
        .scalars()
        .all()
    )
    latest = attempts[0] if attempts else None
    overall = max((a.overall_score for a in attempts), default=None)
    practice_count = trpg_turns + len(sessions)
    snapshot = {
        "overall": _f(overall),
        "pron": _f(latest.pron_score) if latest else None,
        "gram": _f(latest.gram_score) if latest else None,
        "fluency": _f(latest.flu_score) if latest else None,
        "turns": trpg_turns + sum(int(s.turn_count or 0) for s in sessions),
        "durationS": sum(int(s.duration_s or 0) for s in sessions),
        "practiceCount": practice_count,
    }
    return practice_count, (sessions[0].id if sessions else None), snapshot


def _f(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None
