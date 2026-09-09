"""唱歌 C 端路由（M3 唱歌 P0 D7：五端点 + 复用 POST /sessions）。

- ``GET /api/v1/songs``：已发布歌曲列表（唱吧选歌；含 pitch_ref_status 就绪门禁与行数）；
- ``GET /api/v1/songs/{id}``：歌曲详情（逐句 LRC + 每句参考旋律 f0s——D3 双序列图数据源）；
- ``POST /api/v1/sessions/{id}/audio``：整首音频上传（multipart）→ 建评分任务；
- ``GET /api/v1/sing/attempts/{id}/status``：任务状态轮询（queued→processing→done|failed）；
- ``GET /api/v1/sing/attempts/{id}``：评分结果（done 后取；逐句 + 综合 + alignment）。

鉴权/限流（docs/21 §2.1）：Bearer（Security 级依赖，见 core.auth）；
sing 桶 5/h + ise 桶（发音抽样）在 service 层 consume；错误码 40905/41302/40002 先登记后用。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select

from app.core.auth import get_current_user_id
from app.core.response import BizError, ok
from app.db import get_session_factory
from app.models import Lrc, Song, SongPitchRef
from app.models.base import ContentStatus
from app.sing.service import get_attempt_result, get_attempt_status, submit_song_audio

router = APIRouter(prefix="/api/v1", tags=["singing"])


@router.get("/songs")
async def list_songs(user_id: int = Depends(get_current_user_id)):
    """已发布歌曲列表（读侧；写侧归 Java 管理端，Python 只读——docs/10 §3）。"""

    def _q():
        db = get_session_factory()()
        try:
            rows = (
                db.execute(
                    select(Song)
                    .where(Song.status == ContentStatus.PUBLISHED)
                    .order_by(Song.level, Song.id)
                )
                .scalars()
                .all()
            )
            result = []
            for s in rows:
                expected = len(
                    list(db.execute(select(Lrc.id).where(Lrc.song_id == s.id)).scalars())
                )
                result.append(_song_summary(s, expected))
            return result
        finally:
            db.close()

    return ok(await asyncio.to_thread(_q))


@router.get("/songs/{song_id}")
async def get_song_detail(song_id: int, user_id: int = Depends(get_current_user_id)):
    """歌曲详情：逐句 LRC + 参考旋律 f0s（D3 双序列图数据源；就绪门禁由前端提示）。"""

    def _q():
        db = get_session_factory()()
        try:
            song = db.get(Song, song_id)
            if song is None or song.status != ContentStatus.PUBLISHED:
                raise BizError(http_status=404, code=40401, message="song not found")
            lines = list(
                db.execute(select(Lrc).where(Lrc.song_id == song.id).order_by(Lrc.seq)).scalars()
            )
            refs = (
                db.execute(
                    select(SongPitchRef).where(
                        SongPitchRef.lrc_id.in_([int(line.id) for line in lines])
                    )
                )
                .scalars()
                .all()
            )
            ref_by_lrc = {int(r.lrc_id): r for r in refs}
            return {
                **_song_summary(song, len(lines)),
                "lines": [
                    {
                        "seq": int(line.seq),
                        "start_ms": int(line.offset_ms),
                        "end_ms": int(line.end_offset_ms) if line.end_offset_ms else None,
                        "text": line.line_text,
                        "pitch_ref": (
                            ref_by_lrc[int(line.id)].pitch_ref
                            if int(line.id) in ref_by_lrc
                            else {"f0s": [], "notes": [], "midi": []}
                        ),
                    }
                    for line in lines
                ],
            }
        finally:
            db.close()

    return ok(await asyncio.to_thread(_q))


def _song_summary(s: Song, expected_lines: int) -> dict:
    return {
        "id": int(s.id),
        "title": s.title,
        "artist": s.artist,
        "level": s.level,
        "duration_s": s.duration_s,
        "bpm": float(s.bpm) if s.bpm is not None else None,
        "musical_key": s.musical_key,
        "cover_url": s.cover_url,
        # 参考旋律音频（共享卷路径）：前端取 basename 走 /api/v1/audio/{name} 回放——
        # 2026-09-09 真机反馈：无参考音时用户凭记忆清唱，音准普遍偏低
        "audio_url": s.audio_url,
        "pitch_ref_status": s.pitch_ref_status,
        "expected_lines": expected_lines,
    }


@router.post("/sessions/{session_id}/audio")
async def upload_song_audio(
    session_id: int,
    audio: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    """整首跟唱音频上传 → 异步评分任务（20MB/180s；校验后扣桶，失败不扣）。"""
    data = await audio.read()
    result = await submit_song_audio(user_id, session_id, data)
    return ok(result)


@router.get("/sing/attempts/{attempt_id}/status")
async def attempt_status(
    attempt_id: int,
    user_id: int = Depends(get_current_user_id),
):
    return ok(await get_attempt_status(attempt_id, user_id))


@router.get("/sing/attempts/{attempt_id}")
async def attempt_result(
    attempt_id: int,
    user_id: int = Depends(get_current_user_id),
):
    return ok(await get_attempt_result(attempt_id, user_id))
