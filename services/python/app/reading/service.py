"""读书域 DB 服务函数（薄函数组 · 非大 service 类，拷问 M-1）。

调用约定（docs/19 P0-2 短事务口径）：路由 ``await asyncio.to_thread(fn, session, ...)``，
session 由 ``get_session_factory()()`` 创建、调用方 try/finally close + commit。
本模块**不 import asyncio / 路由**，全部为同步 SQLAlchemy 函数，便于直接单测。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.response import BizError
from app.models import (
    Book,
    BookChapter,
    DictionaryEntry,
    DictionaryForm,
    ReadingAnnotation,
    UserReadingProgress,
    UserVocabulary,
)
from app.reading.normalize import normalize_word
from app.reading.split import ChapterSplit, split_chapter

#: 生词本单页大小与游标阈值（keyset：按 created_at 降序 + id 决胜，社区 S1 同式，docs/37）
VOCAB_PAGE_SIZE = 50
BOOK_PAGE_SIZE = 50

PAGE_CURSOR = 2**53  # id 决胜上限（created_at 退化防重，同社区 keyset 口径）


@dataclass
class LookupResult:
    """查词结果：entry 为词典头词条目；matched 为命中的词形（点词原文）。"""

    entry: DictionaryEntry
    matched: str
    in_vocab: bool
    vocab_id: int | None = None


# ---------------------------------------------------------------------------
# 书 / 章节
# ---------------------------------------------------------------------------


def get_book(session: Session, book_id: int) -> Book | None:
    return session.get(Book, book_id)


def list_books(
    session: Session,
    *,
    user_id: int,
    cursor: int | None = None,
    level: str | None = None,
    limit: int = BOOK_PAGE_SIZE,
) -> tuple[list[dict[str, Any]], int | None, bool]:
    """书架：书列表 + 每位用户的阅读进度（未读无进度行）。

    keyset 游标按 id 升序（书静态少，稳定）；返回 (rows, next_cursor, has_more)。
    """
    stmt = select(Book).where(Book.status == "published")
    if level:
        stmt = stmt.where(Book.level == level)
    if cursor:
        stmt = stmt.where(Book.id > cursor)
    rows = list(session.execute(stmt.order_by(Book.id).limit(limit + 1)).scalars())
    has_more = len(rows) > limit
    rows = rows[:limit]
    progress_by_book = {
        p.book_id: p
        for p in session.execute(
            select(UserReadingProgress).where(
                UserReadingProgress.user_id == user_id,
                UserReadingProgress.book_id.in_([b.id for b in rows]),
            )
        ).scalars()
    }
    out = []
    for b in rows:
        p = progress_by_book.get(b.id)
        out.append(
            {
                "id": b.id,
                "title": b.title,
                "author": b.author,
                "description": b.description,
                "level": b.level,
                "cover_color": b.cover_color,
                "cover_emoji": b.cover_emoji,
                "word_count": b.word_count,
                "chapter_count": b.chapter_count,
                "progress": (
                    {
                        "chapter_id": p.chapter_id,
                        "char_offset": p.char_offset,
                        "content_version": p.content_version,
                        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                    }
                    if p
                    else None
                ),
            }
        )
    next_cursor = rows[-1].id if (rows and has_more) else None
    return out, next_cursor, has_more


def get_book_detail(session: Session, user_id: int, book_id: int) -> dict[str, Any] | None:
    """书详情 + 章节列表（已读标记 = 进度所在章）。"""
    book = session.get(Book, book_id)
    if book is None:
        return None
    chapters = list(
        session.execute(
            select(BookChapter)
            .where(BookChapter.book_id == book_id)
            .order_by(BookChapter.chapter_no)
        ).scalars()
    )
    progress = session.execute(
        select(UserReadingProgress).where(
            UserReadingProgress.user_id == user_id,
            UserReadingProgress.book_id == book_id,
        )
    ).scalar_one_or_none()
    current_chapter_id = progress.chapter_id if progress else None
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "description": book.description,
        "level": book.level,
        "cover_color": book.cover_color,
        "cover_emoji": book.cover_emoji,
        "word_count": book.word_count,
        "chapter_count": book.chapter_count,
        "progress": (
            {
                "chapter_id": progress.chapter_id,
                "char_offset": progress.char_offset,
                "content_version": progress.content_version,
            }
            if progress
            else None
        ),
        "chapters": [
            {
                "id": c.id,
                "chapter_no": c.chapter_no,
                "title": c.title,
                "word_count": c.word_count,
                "char_count": c.char_count,
                "current": c.id == current_chapter_id,
            }
            for c in chapters
        ],
    }


def get_chapter_split(session: Session, chapter_id: int) -> tuple[BookChapter, ChapterSplit] | None:
    """章节正文 + 服务端权威切分（段落/句子/章内 offset 坐标系）。"""
    chapter = session.get(BookChapter, chapter_id)
    if chapter is None:
        return None
    return chapter, split_chapter(chapter.content)


# ---------------------------------------------------------------------------
# 查词 / 生词本
# ---------------------------------------------------------------------------


def lookup_word(session: Session, user_id: int, raw: str) -> LookupResult | None:
    """查词：normalize → 头词精确 → 词形反向（dictionary_forms）→ 未命中 None。

    命中链（docs/45 §4）：被点词形（如 "inventions"）→ 头词条目（"invention"）。
    """
    word = normalize_word(raw)
    if not word:
        return None
    entry = session.execute(
        select(DictionaryEntry).where(DictionaryEntry.word == word)
    ).scalar_one_or_none()
    matched = word
    if entry is None:
        form = session.execute(
            select(DictionaryForm).where(DictionaryForm.form == word)
        ).scalar_one_or_none()
        if form is None:
            return None
        entry = session.get(DictionaryEntry, form.entry_id)
        if entry is None:
            return None
        matched = word
    vocab = session.execute(
        select(UserVocabulary).where(
            UserVocabulary.user_id == user_id, UserVocabulary.word == entry.word
        )
    ).scalar_one_or_none()
    return LookupResult(
        entry=entry,
        matched=matched,
        in_vocab=vocab is not None,
        vocab_id=vocab.id if vocab else None,
    )


def add_vocab(
    session: Session,
    user_id: int,
    word: str,
    *,
    book_id: int | None,
    chapter_id: int | None,
    context_snippet: str | None,
    scene: str = "reading",
) -> tuple[UserVocabulary, bool]:
    """加生词本：唯一键幂等（已存在 → 现有行 + added=False；first-write-wins，拷问 V-10）。

    词形解析与 lookup 同链：被点词形（inventions）→ 头词（invention）入库，
    context_snippet 保留原文句（含被点词形）。

    ``scene``：reading（阅读器）/ community（社区划词，docs/47 §5.5）/ manual。
    并发：check-then-act 在唯一键上会撞 IntegrityError（两次并发首次添加）→ 回读既有行，
    与社区点赞同款「DB 原子性兜底」（2026-09-09 修复，docs/48 B15 附带项）。
    """
    word = normalize_word(word)
    headword = _resolve_headword(session, word)
    existing = session.execute(
        select(UserVocabulary).where(
            UserVocabulary.user_id == user_id, UserVocabulary.word == headword
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    row = UserVocabulary(
        user_id=user_id,
        word=headword,
        scene=scene,
        book_id=book_id,
        chapter_id=chapter_id,
        context_snippet=(context_snippet or "")[:500] or None,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        again = session.execute(
            select(UserVocabulary).where(
                UserVocabulary.user_id == user_id, UserVocabulary.word == headword
            )
        ).scalar_one_or_none()
        if again is None:
            raise
        return again, False
    return row, True


def _resolve_headword(session: Session, word: str) -> str:
    """精确 → 词形反向（无则原样返回；与 lookup_word 共用同一条解析链）。"""
    entry = session.execute(
        select(DictionaryEntry).where(DictionaryEntry.word == word)
    ).scalar_one_or_none()
    if entry is not None:
        return entry.word
    form = session.execute(
        select(DictionaryForm).where(DictionaryForm.form == word)
    ).scalar_one_or_none()
    if form is not None and (entry := session.get(DictionaryEntry, form.entry_id)) is not None:
        return entry.word
    return word


def list_vocab(
    session: Session,
    user_id: int,
    *,
    status: str | None = None,
    cursor: tuple[str, int] | None = None,
    limit: int = VOCAB_PAGE_SIZE,
) -> tuple[list[dict[str, Any]], tuple[str, int] | None, bool]:
    """我的单词：keyset（created_at 降序 + id 决胜，docs/37 游标契约）。

    返回行已 join 词典（音标/释义/词频）——字典子集未收录的词也展示（translation 回退
    context 句），保证生词本自洽。
    """
    stmt = select(UserVocabulary).where(UserVocabulary.user_id == user_id)
    if status:
        stmt = stmt.where(UserVocabulary.status == status)
    if cursor:
        created_at, cid = cursor
        stmt = stmt.where(
            (UserVocabulary.created_at < created_at)
            | ((UserVocabulary.created_at == created_at) & (UserVocabulary.id < cid))
        )
    rows = list(
        session.execute(
            stmt.order_by(UserVocabulary.created_at.desc(), UserVocabulary.id.desc()).limit(
                limit + 1
            )
        ).scalars()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    entries = {
        e.word: e
        for e in session.execute(
            select(DictionaryEntry).where(DictionaryEntry.word.in_([r.word for r in rows]))
        ).scalars()
    }
    out = [
        {
            "id": r.id,
            "word": r.word,
            "status": r.status,
            "scene": r.scene,
            "book_id": r.book_id,
            "chapter_id": r.chapter_id,
            "context_snippet": r.context_snippet,
            "note": r.note,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "phonetic": (entries.get(r.word).phonetic if r.word in entries else None),
            "translation": (entries.get(r.word).translation if r.word in entries else None),
            "frequency": (entries.get(r.word).frequency if r.word in entries else None),
        }
        for r in rows
    ]
    next_cursor = None
    if rows and has_more:
        last = rows[-1]
        next_cursor = (last.created_at.isoformat(), last.id)
    return out, next_cursor, has_more


def patch_vocab(
    session: Session, user_id: int, vocab_id: int, *, status: str | None, note: str | None
) -> UserVocabulary | None:
    row = session.get(UserVocabulary, vocab_id)
    if row is None or row.user_id != user_id:
        return None
    if status is not None:
        row.status = status
    if note is not None:
        row.note = note or None
    session.flush()
    return row


def delete_vocab(session: Session, user_id: int, vocab_id: int) -> bool:
    row = session.get(UserVocabulary, vocab_id)
    if row is None or row.user_id != user_id:
        return False
    session.execute(delete(UserVocabulary).where(UserVocabulary.id == vocab_id))
    return True


# ---------------------------------------------------------------------------
# 批注
# ---------------------------------------------------------------------------


def validate_annotation_range(chapter: BookChapter, start_offset: int, end_offset: int) -> None:
    """偏移越界守卫（45004）：start<=end 且 end<=content 长度（内容静态锚，拷问 V-6）。"""
    if start_offset < 0 or end_offset <= start_offset or end_offset > len(chapter.content):
        raise BizError(400, 45004, "annotation offsets out of range")


def list_annotations_sync(
    session: Session, user_id: int, chapter_id: int
) -> list[ReadingAnnotation]:
    return list(
        session.execute(
            select(ReadingAnnotation)
            .where(
                ReadingAnnotation.chapter_id == chapter_id,
                ReadingAnnotation.user_id == user_id,
            )
            .order_by(ReadingAnnotation.start_offset)
        ).scalars()
    )


def create_annotation(
    session: Session,
    *,
    user_id: int,
    chapter: BookChapter,
    kind: str,
    start_offset: int,
    end_offset: int,
    text_snippet: str | None,
    note: str | None,
    color: str | None,
    sentence_idx: int | None,
) -> ReadingAnnotation:
    validate_annotation_range(chapter, start_offset, end_offset)
    row = ReadingAnnotation(
        user_id=user_id,
        book_id=chapter.book_id,
        chapter_id=chapter.id,
        kind=kind,
        start_offset=start_offset,
        end_offset=end_offset,
        content_version=chapter.content_version,
        sentence_idx=sentence_idx,
        text_snippet=(text_snippet or "")[:2000] or None,
        note=(note or "")[:2000] or None,
        color=color,
    )
    session.add(row)
    session.flush()
    return row


def update_annotation(
    session: Session,
    user_id: int,
    annotation_id: int,
    *,
    note: str | None,
    color: str | None,
    kind: str | None,
) -> ReadingAnnotation | None:
    row = session.get(ReadingAnnotation, annotation_id)
    if row is None or row.user_id != user_id:
        return None
    if note is not None:
        row.note = note or None
    if color is not None:
        row.color = color
    if kind is not None:
        row.kind = kind
    session.flush()
    return row


def delete_annotation(session: Session, user_id: int, annotation_id: int) -> bool:
    row = session.get(ReadingAnnotation, annotation_id)
    if row is None or row.user_id != user_id:
        return False
    session.execute(delete(ReadingAnnotation).where(ReadingAnnotation.id == annotation_id))
    return True


def annotation_to_dict(row: ReadingAnnotation) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "start_offset": row.start_offset,
        "end_offset": row.end_offset,
        "content_version": row.content_version,
        "sentence_idx": row.sentence_idx,
        "text_snippet": row.text_snippet,
        "note": row.note,
        "color": row.color,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# ---------------------------------------------------------------------------
# 进度
# ---------------------------------------------------------------------------


def get_progress(session: Session, user_id: int, book_id: int) -> UserReadingProgress | None:
    return session.execute(
        select(UserReadingProgress).where(
            UserReadingProgress.user_id == user_id,
            UserReadingProgress.book_id == book_id,
        )
    ).scalar_one_or_none()


def upsert_progress(
    session: Session,
    user_id: int,
    book_id: int,
    *,
    chapter_id: int,
    char_offset: int,
    content_version: int,
) -> UserReadingProgress:
    """进度 upsert（单行 PK(user_id, book_id)；防抖写入由前端控制）。"""
    row = session.execute(
        select(UserReadingProgress).where(
            UserReadingProgress.user_id == user_id,
            UserReadingProgress.book_id == book_id,
        )
    ).scalar_one_or_none()
    if row is None:
        row = UserReadingProgress(
            user_id=user_id,
            book_id=book_id,
            chapter_id=chapter_id,
            char_offset=max(char_offset, 0),
            content_version=content_version,
        )
        session.add(row)
    else:
        row.chapter_id = chapter_id
        row.char_offset = max(char_offset, 0)
        row.content_version = content_version
    session.flush()
    return row


__all__ = [
    "LookupResult",
    "get_book",
    "list_books",
    "get_book_detail",
    "get_chapter_split",
    "lookup_word",
    "add_vocab",
    "list_vocab",
    "patch_vocab",
    "delete_vocab",
    "validate_annotation_range",
    "list_annotations_sync",
    "create_annotation",
    "update_annotation",
    "delete_annotation",
    "annotation_to_dict",
    "get_progress",
    "upsert_progress",
]
