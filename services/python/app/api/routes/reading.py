"""读书域路由（docs/45 §4）：书架 / 书详情 / 章节 / 查词 / 生词本 / 批注 / 进度 / 音色。

拓扑：前端直连 Python（与社区/口语一致）；JWT 由 Java 签发、本服务验签
（``get_current_user_id``）；DB 走短事务 ``get_session_factory()()`` + asyncio.to_thread
（docs/19 P0-2 口径：同步查询收进线程，短事务不阻塞事件循环；practice.py 同式）。
写方矩阵：本域全 Python（docs/10 §3 增补 · Java 零改动）。
错误码段 45xxx 见 docs/api/error-codes.md。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.core.auth import get_current_user_id
from app.core.response import BizError, Envelope, ok
from app.db import get_session_factory
from app.models import BookChapter, DictionaryEntry
from app.reading import service
from app.reading.normalize import is_lookupable, normalize_word

router = APIRouter(prefix="/api/v1/reading", tags=["reading"])


@asynccontextmanager
async def _db() -> AsyncIterator:
    """短事务会话（创建/关闭在事件循环，查询在 to_thread 线程；practice.py 同式）。"""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


async def _thread(fn):
    """把同步 DB 闭包整体丢进线程（含 commit），返回纯数据。"""
    return await asyncio.to_thread(fn)


# ---------------------------------------------------------------------------
# 响应模型（OpenAPI 契约 · 经 gen:api 生成前端类型）
# ---------------------------------------------------------------------------


class ProgressView(BaseModel):
    chapter_id: int
    char_offset: int
    content_version: int
    updated_at: str | None = None


class BookView(BaseModel):
    id: int
    title: str
    author: str
    description: str | None = None
    level: str
    cover_color: str | None = None
    cover_emoji: str | None = None
    word_count: int
    chapter_count: int
    progress: ProgressView | None = None


class ChapterMetaView(BaseModel):
    id: int
    chapter_no: int
    title: str
    word_count: int
    char_count: int
    current: bool = False


class BookDetailView(BookView):
    chapters: list[ChapterMetaView] = []


class SentenceView(BaseModel):
    idx: int
    text: str
    para_idx: int
    start: int
    end: int


class ChapterView(BaseModel):
    id: int
    book_id: int
    chapter_no: int
    title: str
    content_version: int
    content: str
    paragraphs: list[str] = []
    sentences: list[SentenceView] = []
    word_count: int
    char_count: int


class LookupResultView(BaseModel):
    word: str
    matched: str
    phonetic: str | None = None
    translation: str | None = None
    definition: str | None = None
    pos: str | None = None
    exchange: dict[str, Any] | None = None
    frequency: int | None = None
    in_vocab: bool = False
    vocab_id: int | None = None


class VocabView(BaseModel):
    id: int
    word: str
    status: str
    scene: str
    book_id: int | None = None
    chapter_id: int | None = None
    context_snippet: str | None = None
    note: str | None = None
    created_at: str | None = None
    phonetic: str | None = None
    translation: str | None = None
    frequency: int | None = None


class VocabAddView(BaseModel):
    added: bool
    vocab: VocabView


class AnnotationView(BaseModel):
    id: int
    kind: str
    start_offset: int
    end_offset: int
    content_version: int
    sentence_idx: int | None = None
    text_snippet: str | None = None
    note: str | None = None
    color: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class VoiceView(BaseModel):
    id: str
    label: str
    engine: str
    langs: list[str] = []


class PagedItems(BaseModel):
    items: list[Any] = []
    next_cursor: Any = None
    has_more: bool = False


def _progress_dict(row) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "chapter_id": row.chapter_id,
        "char_offset": row.char_offset,
        "content_version": row.content_version,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _entry_dict(entry) -> dict[str, Any]:
    return {
        "word": entry.word,
        "phonetic": entry.phonetic,
        "translation": entry.translation,
        "definition": entry.definition,
        "pos": entry.pos,
        "exchange": entry.exchange,
        "frequency": entry.frequency,
    }


def _vocab_view(row, entry: DictionaryEntry | None) -> dict[str, Any]:
    return {
        "id": row.id,
        "word": row.word,
        "status": row.status,
        "scene": row.scene,
        "book_id": row.book_id,
        "chapter_id": row.chapter_id,
        "context_snippet": row.context_snippet,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "phonetic": entry.phonetic if entry else None,
        "translation": entry.translation if entry else None,
        "frequency": entry.frequency if entry else None,
    }


# ---------------------------------------------------------------------------
# 书籍 / 章节
# ---------------------------------------------------------------------------


@router.get("/books", response_model=Envelope[PagedItems])
async def list_books(
    cursor: int | None = Query(default=None),
    level: str | None = Query(default=None),
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    async with _db() as db:
        rows, next_cursor, has_more = await _thread(
            lambda: service.list_books(db, user_id=user_id, cursor=cursor, level=level)
        )
    return ok({"items": rows, "next_cursor": next_cursor, "has_more": has_more})


@router.get("/books/{book_id}", response_model=Envelope[BookDetailView])
async def book_detail(
    book_id: int,
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    async with _db() as db:
        detail = await _thread(lambda: service.get_book_detail(db, user_id, book_id))
    if detail is None:
        raise BizError(404, 45001, "book not found")
    return ok(detail)


@router.get("/chapters/{chapter_id}", response_model=Envelope[ChapterView])
async def chapter_detail(
    chapter_id: int,
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    del user_id
    async with _db() as db:
        got = await _thread(lambda: service.get_chapter_split(db, chapter_id))
    if got is None:
        raise BizError(404, 45001, "chapter not found")
    chapter, split = got
    return ok(
        {
            "id": chapter.id,
            "book_id": chapter.book_id,
            "chapter_no": chapter.chapter_no,
            "title": chapter.title,
            "content_version": chapter.content_version,
            "content": chapter.content,
            "paragraphs": split.paragraphs,
            "sentences": [
                {
                    "idx": s.idx,
                    "text": s.text,
                    "para_idx": s.para_idx,
                    "start": s.start,
                    "end": s.end,
                }
                for s in split.sentences
            ],
            "word_count": chapter.word_count,
            "char_count": chapter.char_count,
        }
    )


# ---------------------------------------------------------------------------
# 查词 / 生词本
# ---------------------------------------------------------------------------


@router.post("/lookup", response_model=Envelope[LookupResultView])
async def lookup(
    body: dict[str, str] = Body(...),
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    raw = (body.get("word") or "").strip()
    if not is_lookupable(normalize_word(raw)):
        raise BizError(422, 45002, "word invalid")
    async with _db() as db:
        result = await _thread(lambda: service.lookup_word(db, user_id, raw))
    if result is None:
        raise BizError(404, 45003, "word not found in dictionary")
    return ok(
        {
            **_entry_dict(result.entry),
            "matched": result.matched,
            "in_vocab": result.in_vocab,
            "vocab_id": result.vocab_id,
        }
    )


@router.post("/vocab", response_model=Envelope[VocabAddView])
async def add_vocab(
    body: dict[str, Any] = Body(...),
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    word = normalize_word(str(body.get("word") or ""))
    if not is_lookupable(word):
        raise BizError(422, 45002, "word invalid")
    book_id = body.get("book_id")
    chapter_id = body.get("chapter_id")
    context = body.get("context")
    # 生词来源（docs/47 §5.5 社区划词）：reading | community | manual
    scene = str(body.get("scene") or "reading")
    if scene not in ("reading", "community", "manual"):
        raise BizError(422, 45002, "scene invalid")

    def _q():
        row, added = service.add_vocab(
            db,
            user_id,
            word,
            book_id=int(book_id) if book_id else None,
            chapter_id=int(chapter_id) if chapter_id else None,
            context_snippet=str(context) if context else None,
            scene=scene,
        )
        db.commit()
        entry = db.execute(
            select(DictionaryEntry).where(DictionaryEntry.word == row.word)
        ).scalar_one_or_none()
        return _vocab_view(row, entry), added

    async with _db() as db:
        vocab, added = await _thread(_q)
    return ok({"added": added, "vocab": vocab})


@router.get("/vocab", response_model=Envelope[PagedItems])
async def list_vocab(
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None, description="keyset: <created_at>|<id>"),
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    parsed = None
    if cursor and "|" in cursor:
        ts, cid = cursor.rsplit("|", 1)
        parsed = (ts, int(cid))
    async with _db() as db:
        rows, next_cursor, has_more = await _thread(
            lambda: service.list_vocab(db, user_id, status=status, cursor=parsed)
        )
    return ok({"items": rows, "next_cursor": next_cursor, "has_more": has_more})


@router.patch("/vocab/{vocab_id}", response_model=Envelope[VocabView])
async def patch_vocab(
    vocab_id: int,
    body: dict[str, Any] = Body(...),
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    status_v = body.get("status")
    if status_v is not None and status_v not in ("new", "learning", "known"):
        raise BizError(422, 45002, "status invalid")

    def _q():
        row = service.patch_vocab(db, user_id, vocab_id, status=status_v, note=body.get("note"))
        db.commit()
        return _vocab_view(row, None) if row else None

    async with _db() as db:
        vocab = await _thread(_q)
    if vocab is None:
        raise BizError(404, 40401, "vocab entry not found")
    return ok(vocab)


@router.delete("/vocab/{vocab_id}", response_model=Envelope[dict[str, bool]])
async def delete_vocab(
    vocab_id: int,
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    def _q() -> bool:
        deleted = service.delete_vocab(db, user_id, vocab_id)
        db.commit()
        return deleted

    async with _db() as db:
        deleted = await _thread(_q)
    if not deleted:
        raise BizError(404, 40401, "vocab entry not found")
    return ok({"deleted": True})


# ---------------------------------------------------------------------------
# 批注
# ---------------------------------------------------------------------------


@router.get("/annotations", response_model=Envelope[PagedItems])
async def list_annotations(
    chapter_id: int = Query(...),
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    def _q():
        rows = service.list_annotations_sync(db, user_id, chapter_id)
        return [service.annotation_to_dict(r) for r in rows]

    async with _db() as db:
        items = await _thread(_q)
    return ok({"items": items})


@router.post("/annotations", response_model=Envelope[AnnotationView])
async def create_annotation(
    body: dict[str, Any] = Body(...),
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    kind = body.get("kind")
    if kind not in ("highlight", "note"):
        raise BizError(422, 45002, "kind invalid")
    start = int(body.get("start_offset", -1))
    end = int(body.get("end_offset", -1))

    def _q():
        got = service.get_chapter_split(db, int(body.get("chapter_id") or 0))
        if got is None:
            raise BizError(404, 45001, "chapter not found")
        chapter, _ = got
        row = service.create_annotation(
            db,
            user_id=user_id,
            chapter=chapter,
            kind=kind,
            start_offset=start,
            end_offset=end,
            text_snippet=body.get("text"),
            note=body.get("note"),
            color=body.get("color"),
            sentence_idx=body.get("sentence_idx"),
        )
        db.commit()
        return service.annotation_to_dict(row)

    async with _db() as db:
        return ok(await _thread(_q))


@router.patch("/annotations/{annotation_id}", response_model=Envelope[AnnotationView])
async def patch_annotation(
    annotation_id: int,
    body: dict[str, Any] = Body(...),
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    kind = body.get("kind")
    if kind is not None and kind not in ("highlight", "note"):
        raise BizError(422, 45002, "kind invalid")

    def _q():
        row = service.update_annotation(
            db, user_id, annotation_id, note=body.get("note"), color=body.get("color"), kind=kind
        )
        db.commit()
        return service.annotation_to_dict(row) if row else None

    async with _db() as db:
        ann = await _thread(_q)
    if ann is None:
        raise BizError(404, 40401, "annotation not found")
    return ok(ann)


@router.delete("/annotations/{annotation_id}", response_model=Envelope[dict[str, bool]])
async def delete_annotation(
    annotation_id: int,
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    def _q() -> bool:
        deleted = service.delete_annotation(db, user_id, annotation_id)
        db.commit()
        return deleted

    async with _db() as db:
        deleted = await _thread(_q)
    if not deleted:
        raise BizError(404, 40401, "annotation not found")
    return ok({"deleted": True})


# ---------------------------------------------------------------------------
# 进度 / 音色
# ---------------------------------------------------------------------------


@router.get("/progress/{book_id}", response_model=Envelope[ProgressView])
async def get_progress(
    book_id: int,
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    def _q():
        # 在会话内序列化（会话关闭后访问 ORM 属性可能触发过期刷新 → DetachedInstanceError）
        return _progress_dict(service.get_progress(db, user_id, book_id))

    async with _db() as db:
        data = await _thread(_q)
    return ok(data)


@router.put("/progress/{book_id}", response_model=Envelope[ProgressView])
async def put_progress(
    book_id: int,
    body: dict[str, Any] = Body(...),
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    chapter_id = int(body.get("chapter_id", 0))
    char_offset = max(int(body.get("char_offset", 0)), 0)

    def _q():
        chapter = db.get(BookChapter, chapter_id)
        if chapter is None or chapter.book_id != book_id:
            raise BizError(404, 45001, "chapter not found")
        row = service.upsert_progress(
            db,
            user_id,
            book_id,
            chapter_id=chapter_id,
            char_offset=char_offset,
            content_version=chapter.content_version,
        )
        db.commit()
        # 必须在会话内序列化：updated_at 是 onupdate 服务端生成列，commit 后被标记过期，
        # 会话关闭（_db 退出）后再访问即 DetachedInstanceError → 500。
        # 只在**更新**路径过期（INSERT 走 RETURNING 已取值），所以「第 2 次起的进度保存全挂」
        # 而单次 PUT 的单测永远绿（2026-09-09 联调发现，归档 BUG实测/读书进度-二次保存500.md）。
        return _progress_dict(row)

    async with _db() as db:
        data = await _thread(_q)
    return ok(data)


@router.get("/voices", response_model=Envelope[list[VoiceView]])
async def list_voices(
    user_id: int = Depends(get_current_user_id),
) -> Envelope:
    del user_id
    voices = list_edge_voices()
    from app.audio.tts_local import KITTEN_VOICES, KittenTTSClient
    from app.core.config import get_settings

    kitten = KittenTTSClient(get_settings().voice_models_dir)
    available, _ = kitten.is_available()
    if available:
        voices += [
            {"id": v, "label": f"{v} · 本地音色", "engine": "kitten", "langs": ["en"]}
            for v in KITTEN_VOICES
        ]
    return ok(voices)


def list_edge_voices() -> list[dict[str, Any]]:
    return [
        {
            "id": "en-US-JennyNeural",
            "label": "Jenny · 美式女声",
            "engine": "edge",
            "langs": ["en-US"],
        },
        {
            "id": "en-US-AriaNeural",
            "label": "Aria · 美式女声",
            "engine": "edge",
            "langs": ["en-US"],
        },
        {"id": "en-US-GuyNeural", "label": "Guy · 美式男声", "engine": "edge", "langs": ["en-US"]},
        {
            "id": "en-GB-SoniaNeural",
            "label": "Sonia · 英式女声",
            "engine": "edge",
            "langs": ["en-GB"],
        },
        {
            "id": "en-GB-RyanNeural",
            "label": "Ryan · 英式男声",
            "engine": "edge",
            "langs": ["en-GB"],
        },
    ]
