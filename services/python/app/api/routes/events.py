"""埋点路由（docs/06 §9.1：10 类事件 + client_event_id 幂等去重）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.core.auth import get_current_user_id
from app.core.response import ok
from app.db import get_session_factory
from app.models import Event
from app.models.base import EventTypes

router = APIRouter(prefix="/api/v1/events", tags=["events"])

ALLOWED_TYPES: set[str] = set(EventTypes.__dict__.values()) - {"__module__", "__doc__"}


class EventIn(BaseModel):
    event_type: str
    client_event_id: str | None = None
    occurred_at: int | None = None  # 客户端 timespec（UTC 秒）
    page: str | None = None
    target_type: str | None = None
    target_id: int | None = None
    scene_id: int | None = None
    payload: dict = {}


@router.post("")
async def post_event(body: EventIn, user_id: int = Depends(get_current_user_id)):
    if body.event_type not in ALLOWED_TYPES:
        return ok({"id": None, "dedup": True})  # 非法类型：静默忽略（埋点非关键路径）
    from datetime import UTC, datetime

    occurred = (
        datetime.fromtimestamp(body.occurred_at, UTC) if body.occurred_at else datetime.now(UTC)
    )
    db = get_session_factory()()
    try:
        event = Event(
            user_id=user_id,
            event_type=body.event_type,
            client_event_id=body.client_event_id,
            occurred_at=occurred,
            page=body.page,
            target_type=body.target_type,
            target_id=body.target_id,
            scene_id=body.scene_id,
            payload=body.payload,
        )
        db.add(event)
        db.commit()
        return ok({"id": event.id, "dedup": False})
    except IntegrityError:  # 幂等键冲突：重传去重（docs/06 §9.1）
        db.rollback()
        return ok({"id": None, "dedup": True})
    finally:
        db.close()
