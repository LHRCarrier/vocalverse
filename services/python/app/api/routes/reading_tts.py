"""读书域 · 听书路由（docs/45 §4/§5）：单句音频 / 读词 / 整章预合成（SSE）/ 任务快照与取消。

- ``GET .../tts/segment/{idx}`` 是「播放即取」主线（命中缓存 0ms；未命中才扣 reading_tts
  桶，docs/46 B-4——只扣真实合成）；
- ``POST .../tts/prepare`` 后台整章预合成（VoiceStudio jobs 借鉴 · 自研实现）：
  SSE 事件 ``task_start → sentence_progress* → task_done``（含心跳，复用
  practice.heartbeat_stream）；重连/刷新兜底 = ``GET /tts/tasks/{id}`` 快照（after_seq 登记 P2）；
- 音频端点直接 ``audio/mpeg|audio/wav``（非 Envelope，同 practice _file_stream 例外登记）；
- provider 实际引擎判定：kitten 实例 → "kitten"，其余（edge/Fake）→ "edge"
  （缓存键与目录都按实际引擎，docs/46 B-3 分目录防 wav/mp3 混标）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.audio.base import TTSClient
from app.audio.textproc.normalize import normalize_for_tts
from app.audio.tts import cache_is_fresh
from app.audio.tts_local import KittenTTSClient
from app.core.auth import get_current_user_id
from app.core.config import Settings, get_settings
from app.core.ratelimit import bucket_limits, consume
from app.core.response import Envelope, ok
from app.db import get_session_factory
from app.models import TtsTask
from app.practice.events import heartbeat_stream
from app.reading import orchestrator
from app.reading.events import ReadingStreamEvent, TaskDone, TaskStart, sse_payload
from app.reading.normalize import is_lookupable, normalize_word
from app.reading.service import get_chapter_split
from app.reading.tts_cache import provider_format, reading_tts_cache_path, reading_tts_cached
from app.reading.tts_client import get_reading_tts_client

router = APIRouter(prefix="/api/v1/reading", tags=["reading-tts"])


@asynccontextmanager
async def _db() -> AsyncIterator:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


async def _thread(fn):
    return await asyncio.to_thread(fn)


def _provider_of(tts: TTSClient) -> str:
    return "kitten" if isinstance(tts, KittenTTSClient) else "edge"


def _resolve_tts() -> tuple[TTSClient, str]:
    tts = get_reading_tts_client()
    return tts, _provider_of(tts)


async def _chapter_split(chapter_id: int):
    async with _db() as db:
        return await _thread(lambda: get_chapter_split(db, chapter_id))


# ---------------------------------------------------------------------------
# 单句音频 / 读词（播放即取 · 命中缓存 0 扣）
# ---------------------------------------------------------------------------


@router.get("/chapters/{chapter_id}/tts/segment/{sentence_idx}")
async def tts_segment(
    chapter_id: int,
    sentence_idx: int,
    voice: str = "en-US-JennyNeural",
    rate: str = "+0%",
    user_id: int = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    got = await _chapter_split(chapter_id)
    if got is None:
        raise HTTPException(status_code=404, detail="chapter not found")
    _, split = got
    sentence = split.sentence_by_idx(sentence_idx)
    if sentence is None:
        raise HTTPException(status_code=404, detail="sentence not found")
    text = normalize_for_tts(sentence.text, language="en")
    tts, provider = _resolve_tts()
    data, media, from_cache = await _read_or_synthesize(
        tts, provider, text, voice, rate, settings, user_id
    )
    headers = {"Cache-Control": "private, max-age=0", "X-TTS-Provider": provider}
    if from_cache:
        headers["X-TTS-Cache"] = "hit"
    return StreamingResponse(iter([data]), media_type=media, headers=headers)


@router.get("/tts/word/{word}")
async def tts_word(
    word: str,
    voice: str = "en-US-JennyNeural",
    rate: str = "+0%",
    user_id: int = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    text = normalize_word(word)
    if not is_lookupable(text):
        raise HTTPException(status_code=422, detail="word invalid")
    tts, provider = _resolve_tts()
    data, media, from_cache = await _read_or_synthesize(
        tts, provider, text, voice, rate, settings, user_id
    )
    headers = {"Cache-Control": "private, max-age=0", "X-TTS-Provider": provider}
    if from_cache:
        headers["X-TTS-Cache"] = "hit"
    return StreamingResponse(iter([data]), media_type=media, headers=headers)


async def _read_or_synthesize(
    tts: TTSClient,
    provider: str,
    text: str,
    voice: str,
    rate: str,
    settings: Settings,
    user_id: int,
) -> tuple[bytes, str, bool]:
    """命中缓存直返（0 扣）；未命中：先扣后合成（docs/46 B-4 口径）。"""
    path = reading_tts_cache_path(provider, voice, rate, text)
    if path.exists() and cache_is_fresh(path, settings.tts_cache_ttl_s):
        return path.read_bytes(), provider_format(provider)[1], True
    limits = bucket_limits(settings)
    await consume("reading_tts", limits["reading_tts"], user_id)
    return await reading_tts_cached(tts, text, voice, rate, provider=provider)


# ---------------------------------------------------------------------------
# 整章预合成（SSE · VoiceStudio jobs 模式借鉴）
# ---------------------------------------------------------------------------


@router.post("/chapters/{chapter_id}/tts/prepare")
async def tts_prepare(
    chapter_id: int,
    voice: str = Form("en-US-JennyNeural"),
    rate: str = Form("+0%"),
    user_id: int = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    got = await _chapter_split(chapter_id)
    if got is None:
        raise HTTPException(status_code=404, detail="chapter not found")
    chapter, split = got
    tts, provider = _resolve_tts()

    async with _db() as db:
        existing = await _thread(
            lambda: db.execute(
                select(TtsTask)
                .where(TtsTask.user_id == user_id, TtsTask.chapter_id == chapter_id)
                .order_by(TtsTask.id.desc())
                .limit(1)
            ).scalar_one_or_none()
        )

    if existing is not None and existing.status == "running":
        raise HTTPException(status_code=409, detail="tts task already running")
    if (
        existing is not None
        and existing.status == "done"
        and existing.voice == voice
        and existing.provider == provider
    ):
        # 已完成且参数一致：快照流直返（0 合成；前端按已就绪处理）
        return _sse_snapshot(existing, len(split.sentences))

    limits = bucket_limits(settings)
    await consume("reading_tts", limits["reading_tts"], user_id)

    def _create() -> int:
        task = TtsTask(
            user_id=user_id,
            book_id=chapter.book_id,
            chapter_id=chapter_id,
            voice=voice,
            rate=rate,
            provider=provider,
            status="queued",
            total=len(split.sentences),
            done=0,
            failed_count=0,
        )
        db.add(task)
        db.commit()
        return task.id

    async with _db() as db:
        task_id = await _thread(_create)

    queue = orchestrator.start_task(
        task_id,
        chapter_id=chapter_id,
        voice=voice,
        rate=rate,
        provider=provider,
        split=split,
        tts=tts,
    )
    return StreamingResponse(
        heartbeat_stream(_event_gen(queue), settings.sse_heartbeat_seconds, serialize=sse_payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _event_gen(queue: asyncio.Queue):
    while True:
        try:
            event: ReadingStreamEvent = await queue.get()
        except Exception:  # pragma: no cover - 队列被销毁
            return
        yield event
        if isinstance(event, TaskDone):
            return


def _sse_snapshot(task: TtsTask, total: int) -> StreamingResponse:
    """已完成任务快照流：task_start + task_done（前端按「已就绪」处理）。"""

    async def gen():
        yield sse_payload(
            TaskStart(
                task_id=task.id,
                chapter_id=task.chapter_id,
                total=total,
                voice=task.voice,
                provider=task.provider,
            )
        )
        yield sse_payload(
            TaskDone(
                task_id=task.id,
                status=task.status,
                done=task.done,
                failed=task.failed_count,
                total=total,
            )
        )

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@router.get("/tts/tasks/{task_id}", response_model=Envelope[dict[str, Any]])
async def tts_task_snapshot(
    task_id: int,
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    async with _db() as db:
        row = await _thread(lambda: db.get(TtsTask, task_id))
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="task not found")
    return ok(
        {
            "id": row.id,
            "chapter_id": row.chapter_id,
            "voice": row.voice,
            "provider": row.provider,
            "status": row.status,
            "total": row.total,
            "done": row.done,
            "failed": row.failed_count,
            "error": row.error,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }
    )


@router.delete("/tts/tasks/{task_id}", response_model=Envelope[dict[str, bool]])
async def tts_task_cancel(
    task_id: int,
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    async with _db() as db:
        row = await _thread(lambda: db.get(TtsTask, task_id))
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="task not found")
    if not orchestrator.cancel_task(task_id, reason="user"):
        raise HTTPException(status_code=409, detail="task not cancellable")
    return ok({"cancelled": True})
