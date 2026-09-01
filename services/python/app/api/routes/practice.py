"""M2 练习域路由：会话/回合(SSE)/收尾/报告/音频回放（docs/14 §6.2）。

拓扑：前端直连 Python（SSE 热路径）；JWT 由 Java 签发、本服务验签。
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.audio.base import get_llm_client
from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.ratelimit import bucket_limits, consume
from app.core.response import BizError, ok
from app.db import get_session_factory
from app.models import Attempt, Report, ScenarioMessage
from app.models import Session as DbSession
from app.practice import events as ev
from app.practice.orchestrator import (
    OrchestratorError,
    get_orchestrator,
)
from app.practice.service import complete_session, create_session
from app.practice.state import get_state_store

router = APIRouter(prefix="/api/v1", tags=["practice"])
logger = logging.getLogger("vocalverse")

_SAFE_NAME = re.compile(r"^[0-9a-f]{32}\.mp3$")


class SessionCreate(BaseModel):
    kind: str
    scenario_id: int | None = None
    profile_id: int | None = None
    difficulty: int | None = None
    turn_limit: int | None = None


@router.get("/scenarios")
async def list_scenarios(user_id: int = Depends(get_current_user_id)):
    """预置场景列表（读侧；写侧归 Java 管理端，Python 只读——docs/10 §3）。"""
    from sqlalchemy import select

    from app.models import Scenario
    from app.models.base import ContentStatus

    db = get_session_factory()()
    try:
        rows = db.execute(
            select(Scenario)
            .where(Scenario.status == ContentStatus.PUBLISHED)
            .order_by(Scenario.scene_type, Scenario.difficulty)
        ).scalars()
        return ok(
            [
                {
                    "id": s.id,
                    "title": s.title,
                    "scene_type": s.scene_type,
                    "difficulty": s.difficulty,
                    "description": s.description,
                    "opening_line": s.opening_line,
                    "target_corpus": s.target_corpus,
                    "estimated_turns": s.estimated_turns,
                }
                for s in rows
            ]
        )
    finally:
        db.close()


@router.post("/sessions")
async def post_session(
    body: SessionCreate,
    user_id: int = Depends(get_current_user_id),
):
    session = await create_session(
        user_id=user_id,
        kind=body.kind,
        scenario_id=body.scenario_id,
        profile_id=body.profile_id,
        difficulty=body.difficulty,
        turn_limit=body.turn_limit,
    )
    return ok(
        {
            "id": session.id,
            "kind": session.kind,
            "scenario_id": session.scenario_id,
            "profile_id": session.profile_id,
            "assigned_turns": session.assigned_turns,
        }
    )


async def _rl_asr(user_id: int = Depends(get_current_user_id)) -> None:
    await consume("asr", bucket_limits()["asr"], user_id)


async def _rl_ise(user_id: int = Depends(get_current_user_id)) -> None:
    await consume("ise", bucket_limits()["ise"], user_id)


async def _rl_llm(user_id: int = Depends(get_current_user_id)) -> None:
    await consume("llm", bucket_limits()["llm"], user_id)


@router.post("/sessions/{session_id}/turns")
async def post_turn(
    session_id: int,
    audio: UploadFile | None = File(default=None),
    action: str = Form("normal"),
    expected_turn: int | None = Form(default=None),
    user_id: int = Depends(get_current_user_id),
    _a: None = Depends(_rl_asr),
    _s: None = Depends(_rl_ise),
    _l: None = Depends(_rl_llm),
):
    """回合主入口：multipart 音频 + action → SSE 事件流（docs/14 §3.3）。

    预检（状态/锁）放流外：失败返回 JSON 409/404；流内错误以 error 事件呈现。
    """
    settings = get_settings()
    data = await audio.read() if audio is not None else None
    if data and len(data) > settings.max_upload_bytes:
        raise BizError(http_status=413, code=41301, message="audio too large")

    store = get_state_store()
    state = await store.get(session_id)
    if state is None:
        raise BizError(http_status=404, code=40401, message="session not found or expired")
    if state.state not in ("awaiting_user", "listening", "opening"):
        raise BizError(http_status=409, code=40902, message=f"session state={state.state}")
    if expected_turn is not None and expected_turn != state.current_turn:
        raise BizError(http_status=409, code=40903, message="stale turn")
    # 单会话内降级路径校验：audio 缺省且 action 非 start/hint/demo → 缺音频
    if audio is None and action not in ("start", "hint", "demo", "abandon"):
        raise BizError(http_status=422, code=42202, message="audio required for this action")

    orchestrator = get_orchestrator()

    async def event_stream():
        try:
            async for event in orchestrator.run(session_id, user_id, data, action, expected_turn):
                yield ev.sse_payload(event)
        except OrchestratorError as exc:
            yield ev.sse_payload(ev.StreamError(code=str(exc.status_code), recoverable=False))
        except Exception as exc:  # 管线异常：流内交给前端，节奏优先
            logger.exception("turn failed: %s", exc)
            yield ev.sse_payload(ev.StreamError(code="internal", recoverable=True))

    headers = {"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@router.post("/sessions/{session_id}/complete")
async def complete(
    session_id: int,
    user_id: int = Depends(get_current_user_id),
):
    llm = get_llm_client()
    summary = await _summary_for(llm, session_id)
    report_id = complete_session(session_id, llm, summary)
    return ok({"report_id": report_id, "summary": summary})


async def _summary_for(llm, session_id: int) -> str:
    try:
        return await llm.chat(
            [
                {
                    "role": "user",
                    "content": "Summarize this speaking practice in one friendly sentence.",
                }
            ],
            temperature=0.4,
            max_tokens=80,
        )
    except Exception:
        return "Well done! Keep practicing."


@router.get("/reports/{report_id}")
async def get_report(
    report_id: int,
    user_id: int = Depends(get_current_user_id),
):
    db = get_session_factory()()
    try:
        report = db.get(Report, report_id)
        if report is None:
            raise BizError(http_status=404, code=40401, message="report not found")
        return ok(
            {
                "id": report.id,
                "report_type": report.report_type,
                "scope": report.scope,
                "scope_id": report.scope_id,
                "metrics": report.metrics,
                "computed_at": report.computed_at.isoformat(),
            }
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 音频回放（docs/14 §6.2：验归属 + 24h 惰性过期 → 410）
# ---------------------------------------------------------------------------
@router.get("/audio/{name}")
async def get_audio(
    name: str,
    user_id: int = Depends(get_current_user_id),
):
    if not _SAFE_NAME.match(name):
        raise BizError(http_status=400, code=40001, message="bad audio name")
    settings = get_settings()
    path = Path(settings.audio_dir) / name
    if not path.exists() or path.stat().st_mtime + settings.audio_ttl_hours * 3600 < time.time():
        if path.exists():
            path.unlink(missing_ok=True)  # 惰性清理
        raise BizError(http_status=410, code=41001, message="audio expired")
    # 归属校验：attempts / scenario_messages 任一引用即可
    url = f"/api/v1/audio/{name}"
    db = get_session_factory()()
    try:
        owned = (
            db.execute(
                select(Attempt.id).where(Attempt.audio_url == url, Attempt.user_id == user_id)
            ).first()
            or db.execute(
                select(ScenarioMessage.id)
                .join(DbSession, DbSession.id == ScenarioMessage.session_id)
                .where(ScenarioMessage.audio_url == url, DbSession.user_id == user_id)
            ).first()
        )
        if owned is None:
            raise BizError(http_status=403, code=40301, message="not your audio")
    finally:
        db.close()

    async def _file_stream():
        with open(path, "rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk

    return StreamingResponse(
        _file_stream(), media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=0"}
    )
