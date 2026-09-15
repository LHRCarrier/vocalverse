"""媒体路由（社区 S3 · docs/47 §4.1 · docs/21 §2.1）。

- ``POST /api/v1/media``：multipart 上传（kind=image|video|avatar）→ ``MediaView``；
- ``GET /api/v1/media/{public_id}``：二进制流，**允许匿名**（原生 ``<img>/<video>`` 带不了
  Bearer，docs/06 §11 同款问题），Range/206 由 Starlette ``FileResponse`` 提供（视频拖拽必需）；
- ``DELETE /api/v1/media/{public_id}``：仅 owner，软删。

鉴权：写操作走 ``get_current_user_id``（JWT 由 Java 签发、本服务验签）；
限流：``media`` 桶（``APP_MEDIA_RATE_PER_HOUR``，默认 60/时）。
错误码：41301 / 41501 / 42205 / 40403 / 40302（docs/api/error-codes.md）。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.ratelimit import consume
from app.core.response import BizError, Envelope, ok
from app.db import get_session_factory
from app.media import service

router = APIRouter(prefix="/api/v1/media", tags=["media"])
logger = get_logger("app.media.routes")

READ_CHUNK = 1024 * 1024


class MediaView(BaseModel):
    id: str
    url: str
    kind: str
    mimeType: str
    size: int
    width: int | None = None
    height: int | None = None
    durationS: float | None = None


@asynccontextmanager
async def _db() -> AsyncIterator:
    """短事务会话（创建/关闭在事件循环，查询在 to_thread；与 reading.py 同式）。"""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def _biz(exc: service.MediaError) -> BizError:
    return BizError(exc.http_status, exc.code, exc.message)


@router.post("", response_model=Envelope[MediaView])
async def upload(
    file: UploadFile = File(...),
    kind: str = Form(default="image"),
    width: int | None = Form(default=None),
    height: int | None = Form(default=None),
    duration_s: float | None = Form(default=None),
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    settings = get_settings()
    await consume("media", settings.media_rate_per_hour, user_id)
    started = time.perf_counter()

    def _run():
        """整段落盘流程放 worker 线程（同步文件 API）。

        分块来源是 ``UploadFile.file``（Starlette 已把请求体落到 SpooledTemporaryFile，
        超过 1MB 自动落盘）→ 在 worker 里同步分块读，既不占内存也不需要跨线程泵。
        """
        db = get_session_factory()()
        try:

            def _chunks():
                while True:
                    data = file.file.read(READ_CHUNK)
                    if not data:
                        break
                    yield data

            row, dedup = service.create(
                db,
                user_id=user_id,
                kind=kind,
                chunks=_chunks(),
                width=width,
                height=height,
                duration_s=duration_s,
            )
            db.commit()
            return service.to_view(row), dedup, row.public_id
        finally:
            db.close()

    try:
        view, dedup, media_id = await asyncio.to_thread(_run)
    except service.MediaError as exc:
        logger.warning(
            "媒体上传被拒 user_id=%s kind=%s code=%s reason=%s",
            user_id,
            kind,
            exc.code,
            exc.reason,
        )
        raise _biz(exc) from exc
    except Exception:
        logger.exception("媒体上传失败 user_id=%s kind=%s", user_id, kind)
        raise
    finally:
        await file.close()

    logger.info(
        "媒体上传成功 user_id=%s media_id=%s kind=%s mime=%s size=%s dedup=%s elapsed_ms=%s",
        user_id,
        media_id[:8],
        view["kind"],
        view["mimeType"],
        view["size"],
        dedup,
        int((time.perf_counter() - started) * 1000),
    )
    return ok(view)


@router.get("/{public_id}")
async def download(public_id: str = Path(..., min_length=8, max_length=64)) -> FileResponse:
    """二进制读取（匿名可用；``status='deleted'`` → 40403）。Range 由 FileResponse 处理。"""

    def _q():
        db = get_session_factory()()
        try:
            row = service.get_ready(db, public_id)
            return None if row is None else (row.mime_type, service.abs_path(row))
        finally:
            db.close()

    got = await asyncio.to_thread(_q)
    if got is None:
        logger.info("媒体读取 404 media_id=%s code=40403", public_id[:8])
        raise BizError(404, 40403, "media not found")
    mime, path = got
    if not path.exists():
        # 行在文件不在（卷未挂载/被清）→ 同样 40403，避免 500 暴露路径
        logger.warning("媒体文件缺失 media_id=%s（卷未挂载或已清理）", public_id[:8])
        raise BizError(404, 40403, "media not found")
    return FileResponse(
        path,
        media_type=mime,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.delete("/{public_id}", response_model=Envelope[dict[str, bool]])
async def remove(
    public_id: str = Path(..., min_length=8, max_length=64),
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    def _q():
        db = get_session_factory()()
        try:
            deleted = service.soft_delete(db, user_id=user_id, public_id=public_id)
            db.commit()
            return deleted
        finally:
            db.close()

    try:
        deleted = await asyncio.to_thread(_q)
    except service.MediaError as exc:
        raise _biz(exc) from exc
    if not deleted:
        raise BizError(404, 40403, "media not found")
    logger.info("媒体软删 user_id=%s media_id=%s", user_id, public_id[:8])
    return ok({"deleted": True})


@router.get("", response_model=Envelope[dict[str, Any]])
async def list_mine(
    limit: int = Query(default=20, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    """我的上传列表（配额排查/管理用；只读本人 ready 行）。"""

    def _q():
        from sqlalchemy import select

        from app.models import MediaAsset, MediaStatus

        db = get_session_factory()()
        try:
            rows = (
                db.execute(
                    select(MediaAsset)
                    .where(
                        MediaAsset.owner_id == user_id,
                        MediaAsset.status == MediaStatus.READY,
                    )
                    .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [service.to_view(r) for r in rows]
        finally:
            db.close()

    items = await asyncio.to_thread(_q)
    return ok({"items": items})
