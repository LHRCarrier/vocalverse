"""埋点路由（docs/06 §9.1 + docs/53 P1：20 类事件 · 维度快照 · 游客 page_view · 幂等去重）。

2026-09-21 修订（docs/53 P1）：
- **事件/目标类型白名单与 DB CHECK 同源**（`EventTypes` / `TargetTypes` 常量派生）——原实现用
  ``set(EventTypes.__dict__.values()) - {"__module__","__doc__"}`` 减的是键名字面量，白名单里
  实际混入模块名/描述符，非法值只能靠 DB CHECK 兜住并被当成「重复上报」静默吞（docs/19 已点名）；
- **维度快照服务端填充**：``level``/``age_group`` 取用户档案（不信任客户端），``channel`` 客户端传
  （运行环境），``server_offset_ms = 服务端接收时间 − 客户端 occurred_at``（docs/11 Q-B22）；
- **游客 page_view 可上报**（可选鉴权；其余事件仍强鉴权）；
- **FK 维度兜底**：session_id/song_id/scene_id 指向不存在的行时，去掉该维度重试一次，
  保证事件本身不丢（埋点非关键路径，但「静默丢」要有边界）；
- **payload 轻量白名单**：仅标量值且序列化 ≤4KB，超限丢弃 payload 保留事件（docs/11 Q-B14 的
  白名单诉求在 demo 规模下的最小实现）。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.auth import get_optional_user_id
from app.core.response import ok
from app.db import get_session_factory
from app.models import Event
from app.models.base import Channels, EventTypes, TargetTypes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/events", tags=["events"])

ALLOWED_TYPES: frozenset[str] = frozenset(
    value
    for key, value in vars(EventTypes).items()
    if key.isupper() and not key.startswith("_") and isinstance(value, str)
)
ALLOWED_TARGET_TYPES: frozenset[str] = frozenset(
    value
    for key, value in vars(TargetTypes).items()
    if key.isupper() and not key.startswith("_") and isinstance(value, str)
)
ALLOWED_CHANNELS: frozenset[str] = frozenset(
    value
    for key, value in vars(Channels).items()
    if key.isupper() and not key.startswith("_") and isinstance(value, str)
)
#: 允许匿名上报的事件（游客埋点，docs/53 P1 决策 4）
ANONYMOUS_TYPES: frozenset[str] = frozenset({EventTypes.PAGE_VIEW})
#: payload 序列化上限（字符）
PAYLOAD_MAX_CHARS = 4096

_UUID_RE = re.compile(r"^[0-9a-zA-Z_-]{8,64}$")


class EventIn(BaseModel):
    event_type: str
    client_event_id: str | None = Field(default=None, max_length=64)
    occurred_at: int | None = None  # 客户端 timespec（UTC 秒）
    page: str | None = Field(default=None, max_length=64)
    target_type: str | None = Field(default=None, max_length=16)
    target_id: int | None = None
    scene_id: int | None = None
    song_id: int | None = None
    session_id: int | None = None
    browse_session_id: str | None = Field(default=None, max_length=36)
    recommend_group_id: str | None = Field(default=None, max_length=36)
    channel: str | None = Field(default=None, max_length=16)
    payload: dict[str, Any] = {}


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """payload 轻量白名单：只留标量（str/int/float/bool/None），序列化超限则整体丢弃。"""
    if not payload:
        return {}
    if any(not isinstance(v, (str, int, float, bool, type(None))) for v in payload.values()):
        logger.warning("event payload 含非标量值，已丢弃：%s", sorted(payload)[:5])
        return {}
    try:
        if len(json.dumps(payload, ensure_ascii=False)) > PAYLOAD_MAX_CHARS:
            logger.warning("event payload 超长（>%d 字符），已丢弃", PAYLOAD_MAX_CHARS)
            return {}
    except (TypeError, ValueError):
        return {}
    return payload


def _profile_snapshot(db, user_id: int | None) -> tuple[str | None, str | None]:
    """维度快照：用户档案的 (age_group, cefr_level)；无档案/游客 → (None, None)。"""
    if user_id is None:
        return None, None
    from app.models.user import UserProfile

    row = db.execute(
        select(UserProfile.age_group, UserProfile.cefr_level).where(UserProfile.user_id == user_id)
    ).first()
    if row is None:
        return None, None
    return row[0], row[1]


@router.post("")
async def post_event(
    body: EventIn,
    user_id: int | None = Depends(get_optional_user_id),
):
    # 匿名仅放行 page_view；其余事件要求登录（埋点非关键路径，但匿名行为不进学习数据）
    if user_id is None and body.event_type not in ANONYMOUS_TYPES:
        raise HTTPException(status_code=401, detail="missing bearer token")
    if body.event_type not in ALLOWED_TYPES:
        logger.warning("非法事件类型已忽略：%s", body.event_type)
        return ok({"id": None, "dedup": True, "dropped": "event_type"})
    if body.target_type is not None and body.target_type not in ALLOWED_TARGET_TYPES:
        logger.warning("非法 target_type 已忽略：%s", body.target_type)
        return ok({"id": None, "dedup": True, "dropped": "target_type"})
    if body.browse_session_id is not None and not _UUID_RE.match(body.browse_session_id):
        body.browse_session_id = None

    now = datetime.now(UTC)
    occurred = datetime.fromtimestamp(body.occurred_at, UTC) if body.occurred_at else now
    offset_ms = int((now - occurred).total_seconds() * 1000)
    channel = body.channel if body.channel in ALLOWED_CHANNELS else Channels.WEB

    db = get_session_factory()()
    try:
        age_group, level = _profile_snapshot(db, user_id)

        def build(include_fk: bool) -> Event:
            return Event(
                user_id=user_id,
                event_type=body.event_type,
                client_event_id=body.client_event_id,
                occurred_at=occurred,
                server_offset_ms=offset_ms,
                page=body.page,
                target_type=body.target_type,
                target_id=body.target_id,
                scene_id=body.scene_id if include_fk else None,
                song_id=body.song_id if include_fk else None,
                session_id=body.session_id if include_fk else None,
                browse_session_id=body.browse_session_id,
                recommend_group_id=body.recommend_group_id,
                age_group=age_group,
                level=level,
                channel=channel,
                payload=_clean_payload(body.payload),
            )

        event = build(include_fk=True)
        db.add(event)
        db.commit()
        return ok({"id": event.id, "dedup": False})
    except IntegrityError as exc:
        db.rollback()
        db.expunge_all()  # 丢弃首个（含 FK 维度的）待写对象，避免重试时被一并 flush
        detail = str(getattr(exc, "orig", exc))
        if "uq_events_client_event_id" in detail:
            return ok({"id": None, "dedup": True})  # 幂等键冲突：重传去重（docs/06 §9.1）
        # 其余约束冲突（典型 = FK 维度指向不存在的行）：去掉 FK 维度重试一次，事件本身不丢
        logger.warning("event 落库约束冲突（去 FK 维度重试）：%s", detail.splitlines()[0][:200])
        try:
            event = build(include_fk=False)
            db.add(event)
            db.commit()
            return ok({"id": event.id, "dedup": False, "dimension_dropped": True})
        except IntegrityError as exc2:
            db.rollback()
            logger.warning("event 二次落库仍失败：%s", str(getattr(exc2, "orig", exc2))[:200])
            return ok({"id": None, "dedup": True, "dropped": "constraint"})
    finally:
        db.close()
