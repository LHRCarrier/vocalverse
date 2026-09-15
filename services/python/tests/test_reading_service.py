"""读书域 · service 层测试（:memory: DB；修复前必失败——全新实现）。"""

from __future__ import annotations

import pytest
from app.core.response import BizError
from app.db import get_session_factory
from app.models import Book, BookChapter, DictionaryEntry, DictionaryForm
from app.reading import service


@pytest.fixture()
def reading_data():
    """迷你书/章/词典（含词形 inventions→invention）。"""
    with get_session_factory()() as session:
        book = Book(title="Demo Book", author="Tester", level="L1", chapter_count=1, word_count=0)
        session.add(book)
        session.flush()
        chapter = BookChapter(
            book_id=book.id,
            chapter_no=1,
            title="Chapter 1",
            content="Alice knew it was only a dream. The inventions amazed her!",
            content_version=1,
            word_count=10,
            char_count=63,
        )
        session.add(chapter)
        session.flush()
        entry = DictionaryEntry(
            word="invention",
            phonetic="in'venʃәn",
            translation="n. 发明",
            pos="n",
            exchange={"s": "inventions"},
            frequency=4773,
        )
        session.add(entry)
        session.flush()
        session.add(DictionaryForm(form="inventions", entry_id=entry.id))
        session.add(DictionaryEntry(word="dream", translation="n. 梦"))
        session.commit()
        return {"book_id": book.id, "chapter_id": chapter.id, "entry_id": entry.id}


class TestLookup:
    def test_exact_word(self, reading_data):
        with get_session_factory()() as session:
            r = service.lookup_word(session, 1, "  Invention ")
            assert r is not None
            assert r.entry.word == "invention"
            assert r.in_vocab is False

    def test_inflected_form_resolves_headword(self, reading_data):
        with get_session_factory()() as session:
            r = service.lookup_word(session, 1, "inventions")
            assert r is not None
            assert r.entry.word == "invention"
            assert r.matched == "inventions"

    def test_miss_returns_none(self, reading_data):
        with get_session_factory()() as session:
            assert service.lookup_word(session, 1, "nonexistentzzz") is None


class TestVocab:
    def test_add_idempotent(self, reading_data):
        with get_session_factory()() as session:
            row, added = service.add_vocab(
                session,
                1,
                "Invention",
                book_id=reading_data["book_id"],
                chapter_id=reading_data["chapter_id"],
                context_snippet="The inventions amazed her!",
            )
            session.commit()
            assert added is True
            assert row.word == "invention"  # 头词归一化
            row2, added2 = service.add_vocab(
                session,
                1,
                "invention",
                book_id=reading_data["book_id"],
                chapter_id=reading_data["chapter_id"],
                context_snippet="other",
            )
            session.commit()
            assert added2 is False
            assert row2.id == row.id  # first-write-wins
            assert row2.context_snippet == "The inventions amazed her!"

    def test_list_and_patch(self, reading_data):
        with get_session_factory()() as session:
            row, _ = service.add_vocab(
                session,
                1,
                "dream",
                book_id=reading_data["book_id"],
                chapter_id=reading_data["chapter_id"],
                context_snippet="s",
            )
            session.commit()
            items, cursor, more = service.list_vocab(session, 1)
            assert len(items) == 1
            patched = service.patch_vocab(session, 1, row.id, status="known", note="记住了")
            session.commit()
            assert patched.status == "known"
            assert service.delete_vocab(session, 1, row.id) is True
            session.commit()
            items, _, _ = service.list_vocab(session, 1)
            assert items == []

    def test_ownership(self, reading_data):
        with get_session_factory()() as session:
            row, _ = service.add_vocab(
                session,
                1,
                "dream",
                book_id=reading_data["book_id"],
                chapter_id=reading_data["chapter_id"],
                context_snippet="s",
            )
            session.commit()
            assert service.patch_vocab(session, 2, row.id, status="known", note=None) is None


class TestAnnotations:
    def test_create_and_range_guard(self, reading_data):
        with get_session_factory()() as session:
            chapter = session.get(BookChapter, reading_data["chapter_id"])
            row = service.create_annotation(
                session,
                user_id=1,
                chapter=chapter,
                kind="highlight",
                start_offset=0,
                end_offset=5,
                text_snippet="Alice",
                note=None,
                color="#fbbf24",
                sentence_idx=0,
            )
            session.commit()
            assert row.kind == "highlight"
            with pytest.raises(BizError) as exc:
                service.create_annotation(
                    session,
                    user_id=1,
                    chapter=chapter,
                    kind="note",
                    start_offset=10,
                    end_offset=5,
                    text_snippet=None,
                    note=None,
                    color=None,
                    sentence_idx=None,
                )
            assert exc.value.code == 45004
            with pytest.raises(BizError):
                service.create_annotation(
                    session,
                    user_id=1,
                    chapter=chapter,
                    kind="note",
                    start_offset=0,
                    end_offset=99999,
                    text_snippet=None,
                    note=None,
                    color=None,
                    sentence_idx=None,
                )

    def test_list_and_delete(self, reading_data):
        with get_session_factory()() as session:
            chapter = session.get(BookChapter, reading_data["chapter_id"])
            service.create_annotation(
                session,
                user_id=1,
                chapter=chapter,
                kind="highlight",
                start_offset=0,
                end_offset=5,
                text_snippet="Alice",
                note=None,
                color="#fbbf24",
                sentence_idx=0,
            )
            session.commit()
            rows = service.list_annotations_sync(session, 1, chapter.id)
            assert len(rows) == 1
            assert service.delete_annotation(session, 1, rows[0].id) is True
            session.commit()
            assert service.list_annotations_sync(session, 1, chapter.id) == []


class TestProgress:
    def test_upsert_single_row(self, reading_data):
        with get_session_factory()() as session:
            chapter_id = reading_data["chapter_id"]
            service.upsert_progress(
                session,
                1,
                reading_data["book_id"],
                chapter_id=chapter_id,
                char_offset=10,
                content_version=1,
            )
            session.commit()
            service.upsert_progress(
                session,
                1,
                reading_data["book_id"],
                chapter_id=chapter_id,
                char_offset=55,
                content_version=1,
            )
            session.commit()
            row = service.get_progress(session, 1, reading_data["book_id"])
            assert row.char_offset == 55
            assert service.get_progress(session, 2, reading_data["book_id"]) is None


class TestSegments:
    def test_chapter_split_roundtrip_coordinates(self, reading_data):
        with get_session_factory()() as session:
            got = service.get_chapter_split(session, reading_data["chapter_id"])
            assert got is not None
            chapter, split = got
            assert len(split.paragraphs) == 1
            assert split.sentences[0].text == "Alice knew it was only a dream."
            # offset 重建：start 与 content 切片一致（同一坐标系，docs/45 §3）
            for s in split.sentences:
                assert chapter.content[s.start : s.end] == s.text

    def test_book_list_includes_progress(self, reading_data):
        with get_session_factory()() as session:
            service.upsert_progress(
                session,
                1,
                reading_data["book_id"],
                chapter_id=reading_data["chapter_id"],
                char_offset=5,
                content_version=1,
            )
            session.commit()
            rows, _, _ = service.list_books(session, user_id=1)
            assert len(rows) == 1
            assert rows[0]["progress"] is not None
            rows2, _, _ = service.list_books(session, user_id=2)
            assert rows2[0]["progress"] is None
