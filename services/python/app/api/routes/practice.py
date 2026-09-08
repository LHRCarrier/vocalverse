"""M2 练习域路由：会话/回合(SSE)/收尾/报告/音频回放（docs/14 §6.2）。

拓扑：前端直连 Python（SSE 热路径）；JWT 由 Java 签发、本服务验签。
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from app.audio.base import get_llm_client
from app.audio.upload import validate_audio_bytes
from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.ratelimit import bucket_limits, consume
from app.core.response import BizError, ok
from app.db import get_session_factory
from app.models import Attempt, Report, ScenarioMessage
from app.models import Session as DbSession
from app.models.base import SessionStatus
from app.practice import events as ev
from app.practice.orchestrator import (
    OrchestratorError,
    get_orchestrator,
    save_audio_bytes,
)
from app.practice.service import complete_session, create_session
from app.practice.state import get_state_store

router = APIRouter(prefix="/api/v1", tags=["practice"])
logger = logging.getLogger("vocalverse")

_SAFE_NAME = re.compile(r"^[0-9a-f]{32}\.mp3$")

#: R-13 恢复端点回带最近消息条数（UI 重建够用；完整历史以 scenario_messages 为准）
RESTORE_MESSAGES_LIMIT = 12


class SessionCreate(BaseModel):
    kind: str
    scenario_id: int | None = None
    profile_id: int | None = None
    difficulty: int | None = None
    turn_limit: int | None = None
    shadow_material_id: int | None = None  # kind=shadow（DoD ④，2026-09-04）


@router.get("/scenarios")
async def list_scenarios(user_id: int = Depends(get_current_user_id)):
    """预置场景列表（读侧；写侧归 Java 管理端，Python 只读——docs/10 §3）。"""
    # docs/19 P0-2：查询收进 to_thread（短事务，不阻塞事件循环）
    # 注意：路由 docstring 会进入 OpenAPI description（契约快照为文本级对账）——
    # 实现说明一律写代码注释，不动 docstring（2026-09-07 踩坑，见工作日志）
    from sqlalchemy import select

    from app.models import Scenario
    from app.models.base import ContentStatus

    def _q():
        db = get_session_factory()()
        try:
            return (
                db.execute(
                    select(Scenario)
                    .where(Scenario.status == ContentStatus.PUBLISHED)
                    .order_by(Scenario.scene_type, Scenario.difficulty)
                )
                .scalars()
                .all()
            )
        finally:
            db.close()

    rows = await asyncio.to_thread(_q)
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
        shadow_material_id=body.shadow_material_id,
    )
    return ok(
        {
            "id": session.id,
            "kind": session.kind,
            "scenario_id": session.scenario_id,
            "profile_id": session.profile_id,
            "shadow_material_id": session.shadow_material_id,
            "assigned_turns": session.assigned_turns,
        }
    )


@router.get("/sessions/{session_id}")
async def get_session_restore(
    session_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """会话恢复（R-13 / docs/21 §3.1 目标态）：刷新/断线后前端据此重建 UI 与轮次。

    返回运行态（state/current_turn/next_seq）+ 最近消息快照；运行态缺失（StateStore
    TTL 过期/进程重启）时以 scenario_messages 权威历史重建（state.py 注释口径：
    「权威历史永远在 scenario_messages」）。归属校验同 /turns：不拥有 → 40401。
    """

    # docs/19 P0-2：同步 DB 查询收进 to_thread（短事务，不阻塞事件循环）
    def _q():
        db = get_session_factory()()
        try:
            session = db.execute(
                select(DbSession).where(DbSession.id == session_id, DbSession.user_id == user_id)
            ).scalar_one_or_none()
            if session is None:
                return None
            # 重建所需聚合：user 消息数 = current_turn；max(seq)+1 = next_seq
            user_turns = db.execute(
                select(func.count())
                .select_from(ScenarioMessage)
                .where(ScenarioMessage.session_id == session_id, ScenarioMessage.role == "user")
            ).scalar_one()
            max_seq = db.execute(
                select(func.max(ScenarioMessage.seq)).where(
                    ScenarioMessage.session_id == session_id
                )
            ).scalar_one()
            msgs = list(
                reversed(
                    db.execute(
                        select(ScenarioMessage)
                        .where(ScenarioMessage.session_id == session_id)
                        .order_by(ScenarioMessage.seq.desc())
                        .limit(RESTORE_MESSAGES_LIMIT)
                    )
                    .scalars()
                    .all()
                )
            )
            # 已完成会话回带报告 id：前端直接跳转报告页（P0-8 短路语义复用）
            report_id = None
            if session.status == SessionStatus.COMPLETED:
                report_id = db.execute(
                    select(Report.id).where(
                        Report.report_type == "session_report",
                        Report.scope == "session",
                        Report.scope_id == session.id,
                    )
                ).scalar_one_or_none()
            return session, user_turns, max_seq, msgs, report_id
        finally:
            db.close()

    row = await asyncio.to_thread(_q)
    if row is None:
        raise BizError(http_status=404, code=40401, message="session not found or expired")
    session, user_turns, max_seq, msgs, report_id = row

    state = await get_state_store().get(session_id)
    if state is not None:
        # 运行态优先：StateStore 为真源（进行中会话锁/轮次同步语义在编排器内维护）
        live_state, current_turn, next_seq = state.state, state.current_turn, state.next_seq
    else:
        # 重建：只 INSERT 的 scenario_messages 为权威历史（state.py 注释口径）
        current_turn = int(user_turns)
        next_seq = int(max_seq or 0) + 1
        if session.status == SessionStatus.COMPLETED:
            live_state = "completed"
        elif session.status == SessionStatus.ABANDONED:
            live_state = "concluded"
        else:
            live_state = "awaiting_user"

    return ok(
        {
            "id": session.id,
            "kind": session.kind,
            "status": session.status,
            "assigned_turns": session.assigned_turns,
            "state": live_state,
            "current_turn": current_turn,
            "next_seq": next_seq,
            #: 客户端下轮提交 expected_turn 的权威值（与 TurnEnd.expected_turn 同语义）
            "next_expected_turn": current_turn,
            "report_id": report_id,
            "messages": [
                {
                    "seq": m.seq,
                    "role": m.role,
                    "content": m.content,
                    "audio_url": m.audio_url,
                    "origin": m.origin,
                    "action": m.action,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in msgs
            ],
        }
    )


@router.post("/sessions/{session_id}/turns")
async def post_turn(
    session_id: int,
    audio: UploadFile | None = File(default=None),
    action: str = Form("normal"),
    expected_turn: int | None = Form(default=None),
    user_id: int = Depends(get_current_user_id),
):
    """回合主入口：multipart 音频 + action → SSE 事件流（docs/14 §3.3）。

    预检（状态/锁）放流外：失败返回 JSON 409/404；流内错误以 error 事件呈现。
    """
    # P0-3：归属校验最先做——不拥有 → 40401（不泄露存在性），且不读音频/不落盘/不耗配额
    await _require_session_owner(session_id, user_id)
    settings = get_settings()
    data = await audio.read() if audio is not None else None
    if data is not None:
        # 带音频的回合先校验：空/近空录音会推进 current_turn 且不可重来（见 app/audio/upload.py）
        data = validate_audio_bytes(
            data,
            min_bytes=settings.min_upload_bytes,
            max_bytes=settings.max_upload_bytes,
        )
        # vasr-05：录音时长超上限前置拒绝（42203，先校验后落盘/扣额度）——防
        # 「45s 录音进 15s 对话轮」污染 wpm/停顿口径并白烧 ASR/ISE 配额；时长探不出
        # （ffprobe/ffmpeg 缺失、坏容器）不阻断——字节界继续兜底（保守：宁可放过分不拦错）。
        import tempfile
        from pathlib import Path as _Path

        from app.audio.ffmpeg_utils import probe_duration_seconds

        with tempfile.NamedTemporaryFile(suffix=".in", delete=False) as tmp:
            tmp.write(data)
            probe_src = tmp.name
        try:
            dur = await probe_duration_seconds(probe_src)
        finally:
            _Path(probe_src).unlink(missing_ok=True)
        if dur is not None and dur > settings.max_dialog_seconds:
            raise BizError(
                http_status=422,
                code=42204,
                message=f"audio too long: {dur:.0f}s (max {settings.max_dialog_seconds}s)",
            )
    # 用户录音落盘（docs/14 §6.1：attempts.audio_url 引用；24h 惰性过期清理）
    audio_url = save_audio_bytes(data) if data else None

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

    # 分桶限流：预检（归属/状态/输入）通过后再扣额度——修复审计 R-06「先扣后校验」；
    # 按 action 实际消耗扣桶（2026-09-07 评审：此前无差别扣 3 桶——hint/demo/abandon
    # 实际零管线消耗却扣 ASR/ISE/LLM，轻动作会误耗尽用户配额并 429）：
    # - normal/retry（音频回合）：ASR 转写 + ISE 评分 + LLM 回复 → 三桶各 1
    #   （docs/06 §7 按子资源分桶，/turns 不单计）；
    # - start：无转写/评分，仅 LLM 首句 → 仅 LLM 1；
    # - abandon：收尾仅 LLM 摘要 → 仅 LLM 1；
    # - hint/demo（无音频轻分支零消耗；带音频走 LLM 段 → 仅 LLM 1）。
    limits = bucket_limits()
    if action in ("normal", "retry"):
        await consume("asr", limits["asr"], user_id)
        await consume("ise", limits["ise"], user_id)
        await consume("llm", limits["llm"], user_id)
    else:
        if action not in ("hint", "demo") or audio is not None:
            await consume("llm", limits["llm"], user_id)

    orchestrator = get_orchestrator()

    async def event_stream():
        try:
            core = orchestrator.run(session_id, user_id, data, action, expected_turn, audio_url)
            # R-18：心跳包装（静默 ≥15s 推 ': ping' 注释行；不取消内部流，见 events.py）
            async for payload in ev.heartbeat_stream(core, settings.sse_heartbeat_seconds):
                yield payload
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
    # P0-3：归属校验先于 LLM 摘要（越权请求不消耗 LLM 配额；
    # docs/api/error-codes.md 40301 行登记口径：越权按资源不存在处理）
    await _require_session_owner(session_id, user_id)
    llm = get_llm_client()
    summary = await _summary_for(llm, session_id)
    report_id = await asyncio.to_thread(complete_session, session_id, llm, summary)
    return ok({"report_id": report_id, "summary": summary})


async def _require_session_owner(session_id: int, user_id: int) -> None:
    """docs/19 P0-3（审计 R-05 越权）：turn/complete 前校验会话归属。

    权威源 = sessions.user_id（DB，Alembic 真源）；StateStore 按 session_id 键存运行时
    状态、不含归属概念，故每轮预检做一次短 SELECT。
    docs/19 P0-2：同步 DB 查询收进 to_thread（预检不阻塞事件循环）。
    响应语义：越权统一按资源不存在处理（docs/api/error-codes.md 40301 行登记口径：
    不泄露存在性）→ 404/40401。
    """

    def _belongs() -> bool:
        db = get_session_factory()()
        try:
            row = db.execute(
                select(DbSession.id).where(DbSession.id == session_id, DbSession.user_id == user_id)
            ).first()
            return row is not None
        finally:
            db.close()

    if not await asyncio.to_thread(_belongs):
        raise BizError(http_status=404, code=40401, message="session not found or expired")


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
    # P0-3（审计 R-05）：报告归属 = 经 sessions 校验（Report 无 user_id 列，scope/scope_id
    # 多态引用无 FK——docs/10 开放项 D-1）；非 session 报告当前无读取场景 → 一律 40401。
    # 越权按"资源不存在"处理（docs/api/error-codes.md 40301 行登记口径，不泄露存在性）。
    # docs/19 P0-2：查询走 to_thread（短事务，不阻塞事件循环）。
    def _q():
        db2 = get_session_factory()()
        try:
            return db2.execute(
                select(Report)
                .join(
                    DbSession,
                    (Report.scope == "session") & (DbSession.id == Report.scope_id),
                )
                .where(Report.id == report_id, DbSession.user_id == user_id)
            ).scalar_one_or_none()
        finally:
            db2.close()

    report = await asyncio.to_thread(_q)
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


# ---------------------------------------------------------------------------
# 音频回放（docs/14 §6.2：验归属 + 24h 惰性过期 → 410）
# ---------------------------------------------------------------------------
@router.get("/audio/tts/{name}")
async def get_tts_audio(name: str, user_id: int = Depends(get_current_user_id)):
    """AI TTS 输出流（tts/ 前缀，独立路由；双段路径无法与 /audio/{name} 单段参数兼容）。

    2026-09-07（用户实测 403）：流式多句音频只有首句落库（attempt/message 引用），
    其余 chunk 无归属引用 → get_audio 归属校验 403。TTS 为会话内生成物（非隐私录音），
    登录 + 未过期即放行；用户录音仍由 /audio/{name} 严格归属。
    """
    if not _SAFE_NAME.match(name):
        raise BizError(http_status=400, code=40001, message="bad audio name")
    settings = get_settings()
    path = Path(settings.audio_dir) / "tts" / name
    if not path.exists() or path.stat().st_mtime + settings.audio_ttl_hours * 3600 < time.time():
        if path.exists():
            path.unlink(missing_ok=True)  # 惰性清理
        raise BizError(http_status=410, code=41001, message="audio expired")

    async def _tts_stream():
        with open(path, "rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk

    return StreamingResponse(
        _tts_stream(), media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=0"}
    )


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
    # docs/19 P0-2：归属查询走 to_thread（短事务，不阻塞事件循环；文件流不受影响）
    url = f"/api/v1/audio/{name}"

    def _owns() -> bool:
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
            return owned is not None
        finally:
            db.close()

    if not await asyncio.to_thread(_owns):
        raise BizError(http_status=403, code=40301, message="not your audio")

    async def _file_stream():
        with open(path, "rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk

    return StreamingResponse(
        _file_stream(), media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=0"}
    )
