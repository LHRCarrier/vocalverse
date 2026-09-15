"""控制台 · 内容治理端点（docs/50 §10.3 Python 段：``/api/v1/console/library/**``）。

两块：

1. **书/章节上下架**：``books.status`` / ``book_chapters.status``（后者是迁移 0013 新增列）。
   ⚠️ 新增列**必须让读取路径真的过滤**，否则"下架"是零效果的空操作 ——
   故本 PR 同步修了 ``app/reading/service.py`` 的三处读取（详见该文件注释）；
2. **媒体治理**：``media_assets`` 归 Python 写（docs/10 §3.1），``hidden`` 是迁移 0013
   扩出来的 CHECK 值；隐藏后公共媒体端点（``GET /api/v1/media/{public_id}``）必须读不到
   —— 该端点走 ``media.service.get_ready``（只认 ``ready``），语义天然满足，本文件补齐写侧。

上架校验（docs/50 §6.1）：书置 ``published`` 要求"有章节且章节全部 published"，
否则 46011 + ``data.violations[]``（字段级原因）。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, Path, Query
from sqlalchemy import func, select

from app.console.api.deps import ConsoleAdmin, ConsoleBizError, console_guard
from app.core.response import Envelope, ok
from app.db import get_session_factory

router = APIRouter(prefix="/api/v1/console/library", tags=["console-library"])

#: 上下架合法取值（与 ``ck_books_status`` / ``ck_book_chapters_status`` 完全一致）
CONTENT_STATUSES = ("draft", "published", "archived")


async def _db_call(fn):
    def _run():
        db = get_session_factory()()
        try:
            return fn(db)
        finally:
            db.close()

    return await asyncio.to_thread(_run)


def _validate_status(body: dict[str, Any]) -> str:
    status = (body or {}).get("status")
    if status not in CONTENT_STATUSES:
        raise ConsoleBizError(
            422,
            46007,
            f"status 非法（{'|'.join(CONTENT_STATUSES)}）",
            {"allowed": list(CONTENT_STATUSES)},
        )
    return str(status)


# ---------------------------------------------------------------------------
# 书
# ---------------------------------------------------------------------------
@router.get("/books", response_model=Envelope[dict])
async def list_books(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    level: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: ConsoleAdmin = Depends(console_guard(perm="content:book:read")),
) -> Envelope:
    del admin
    from app.models.reading import Book

    def _run(db):
        conds = []
        if q:
            conds.append(Book.title.ilike(f"%{q}%"))
        if status:
            conds.append(Book.status == status)
        if level:
            conds.append(Book.level == level)
        total = db.execute(select(func.count()).select_from(Book).where(*conds)).scalar()
        rows = list(
            db.execute(
                select(Book)
                .where(*conds)
                .order_by(Book.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars()
        )
        return {
            "items": [_book_view(r) for r in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    return ok(await _db_call(_run))


@router.post("/books/{book_id}/publish", response_model=Envelope[dict])
async def publish_book(
    book_id: int = Path(...),
    body: dict[str, Any] = Body(...),
    admin: ConsoleAdmin = Depends(console_guard(perm="content:book:publish")),
) -> Envelope:
    """上/下架（``{status: draft|published|archived}``）；已经是目标状态 → 幂等返回。"""
    del admin
    target = _validate_status(body)
    from app.models.reading import Book, BookChapter

    def _run(db):
        book = db.get(Book, book_id)
        if book is None:
            raise ConsoleBizError(404, 46009, "book not found")
        if target == "published" and book.status != "published":
            violations = _book_publish_violations(db, book, BookChapter)
            if violations:
                raise ConsoleBizError(422, 46011, "上架校验失败", {"violations": violations})
        book.status = target
        db.commit()
        db.refresh(book)
        return _book_view(book)

    return ok(await _db_call(_run))


def _book_publish_violations(db, book, chapter_model) -> list[dict[str, Any]]:
    """字段级上架校验（docs/50 §6.1/§11 错误码 46011 的 ``data.violations[]``）。"""
    violations: list[dict[str, Any]] = []
    rows = list(
        db.execute(
            select(chapter_model.id, chapter_model.chapter_no, chapter_model.status).where(
                chapter_model.book_id == book.id
            )
        ).all()
    )
    if not rows:
        violations.append({"field": "chapters", "reason": "empty", "message": "书下没有任何章节"})
        return violations
    bad = [r[2] for r in rows if r[2] != "published"]
    if bad:
        violations.append(
            {
                "field": "chapters",
                "reason": "not_published",
                "message": f"仍有 {len(bad)} 章未上架",
                "chapterStatuses": sorted(set(bad)),
            }
        )
    return violations


@router.get("/books/{book_id}/chapters", response_model=Envelope[dict])
async def list_chapters(
    book_id: int = Path(...),
    admin: ConsoleAdmin = Depends(console_guard(perm="content:book:read")),
) -> Envelope:
    del admin
    from app.models.reading import Book, BookChapter

    def _run(db):
        if db.get(Book, book_id) is None:
            raise ConsoleBizError(404, 46009, "book not found")
        rows = list(
            db.execute(
                select(BookChapter)
                .where(BookChapter.book_id == book_id)
                .order_by(BookChapter.chapter_no)
            ).scalars()
        )
        return {"items": [_chapter_view(r) for r in rows]}

    return ok(await _db_call(_run))


# ---------------------------------------------------------------------------
# 章节
# ---------------------------------------------------------------------------
@router.post("/chapters/{chapter_id}/publish", response_model=Envelope[dict])
async def publish_chapter(
    chapter_id: int = Path(...),
    body: dict[str, Any] = Body(...),
    admin: ConsoleAdmin = Depends(console_guard(perm="content:book:publish")),
) -> Envelope:
    """章节上/下架。下架后**必须**在阅读路径真的不可见（见 reading/service.py 的过滤谓词）。"""
    del admin
    target = _validate_status(body)
    from app.models.reading import BookChapter

    def _run(db):
        row = db.get(BookChapter, chapter_id)
        if row is None:
            raise ConsoleBizError(404, 46009, "chapter not found")
        row.status = target
        db.commit()
        db.refresh(row)
        return _chapter_view(row)

    return ok(await _db_call(_run))


# ---------------------------------------------------------------------------
# 媒体治理
# ---------------------------------------------------------------------------
@router.get("/media", response_model=Envelope[dict])
async def list_media(
    kind: str | None = Query(default=None),
    status: str | None = Query(default=None),
    owner_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: ConsoleAdmin = Depends(console_guard(perm="content:media:read")),
) -> Envelope:
    del admin
    from app.models.media import MediaAsset

    def _run(db):
        conds = []
        if kind:
            conds.append(MediaAsset.kind == kind)
        if status:
            conds.append(MediaAsset.status == status)
        if owner_id:
            conds.append(MediaAsset.owner_id == owner_id)
        total = db.execute(select(func.count()).select_from(MediaAsset).where(*conds)).scalar()
        rows = list(
            db.execute(
                select(MediaAsset)
                .where(*conds)
                .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars()
        )
        return {
            "items": [_media_view(r) for r in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    return ok(await _db_call(_run))


@router.post("/media/{public_id}/hide", response_model=Envelope[dict])
async def hide_media(
    public_id: str = Path(..., min_length=8, max_length=64),
    body: dict[str, Any] = Body(...),
    admin: ConsoleAdmin = Depends(console_guard(perm="content:media:write")),
) -> Envelope:
    """隐藏 / 恢复。

    - ``hidden=true``：``ready → hidden``（行保留，可恢复）；已 ``deleted`` 的行不动
      —— 用户自删是用户意志，管理员"恢复"不应让用户已删内容复活；
    - ``hidden=false``：``hidden → ready``；``deleted`` 同样不动。
    """
    del admin
    hidden = (body or {}).get("hidden")
    if not isinstance(hidden, bool):
        raise ConsoleBizError(422, 46007, "hidden 必须为布尔")
    from app.models.media import MediaAsset, MediaStatus

    def _run(db):
        row = db.execute(
            select(MediaAsset).where(MediaAsset.public_id == public_id)
        ).scalar_one_or_none()
        if row is None:
            raise ConsoleBizError(404, 46009, "media not found")
        if row.status == MediaStatus.DELETED:
            raise ConsoleBizError(
                409, 46010, "媒体已被用户删除，管理员不可撤销该动作", {"status": row.status}
            )
        target = MediaStatus.HIDDEN if hidden else MediaStatus.READY
        if row.status != target:
            row.status = target
            row.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(row)
        return _media_view(row)

    return ok(await _db_call(_run))


def _book_view(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "author": row.author,
        "level": row.level,
        "status": row.status,
        "chapter_count": row.chapter_count,
        "word_count": row.word_count,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _chapter_view(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "book_id": row.book_id,
        "chapter_no": row.chapter_no,
        "title": row.title,
        "status": row.status,
        "word_count": row.word_count,
        "char_count": row.char_count,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _media_view(row) -> dict[str, Any]:
    return {
        "id": row.public_id,
        "public_id": row.public_id,
        "owner_id": row.owner_id,
        "kind": row.kind,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "status": row.status,
        "url": f"/api/v1/media/{row.public_id}",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
