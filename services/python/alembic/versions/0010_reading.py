"""读书域迁移：8 表（books / book_chapters / dictionary_entries / dictionary_forms /
user_reading_progress / user_vocabulary / reading_annotations / tts_tasks）+ events 埋点扩值。

依据 docs/45（定稿 · 四官拷问合流）：
- 写方矩阵：本域全部 Python 写（seed 播种 + reading 路由写），Java 零改动；
  books 管理端后置（届时触发 Single-Writer 反转 + content_version 守卫，docs/46 V-1/V-6）；
- 迁移只建表（0 需断言——全新表无存量）；数据（书 + 词典子集 2 万行）走 app/db/seed_reading.py
  （docs/10 §7.3：alembic 只 DDL，docs/46 M-4/V-14/V-15）；
- 坐标系：annotations/progress 的 offset 均为**章节正文整文本** char offset；
  content_version 为文本修订版本守卫（docs/46 V-6）；
- events.event_type CHECK 扩 5 值（word_lookup/vocab_add/annotation_add/tts_play/tts_prepare），
  沿用 0006 的 PG 大表姿势（NOT VALID + VALIDATE，docs/46 V-17/B-15）。

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None


def _bigint_pk() -> sa.Column:
    return sa.Column(
        "id",
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.Identity(always=False),
        nullable=False,
        primary_key=True,  # 必须显式：PG 对 FK 引用列要求 UNIQUE/PK（2026-09-10 实跑复现）
    )


def _jsonb_col(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
        nullable=True,
    )


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


_EVENT_NEW_TYPES = (
    "'page_view', 'scene_start', 'recording_start', 'recording_complete', "
    "'score_event', 'recommend_impression', 'recommend_click', 'practice_complete', "
    "'fun_action', 'corpus_hit', 'free_chat_open', 'free_chat_turn', "
    "'free_chat_switch', 'free_chat_reset', 'free_chat_rate', 'word_lookup', "
    "'vocab_add', 'annotation_add', 'tts_play', 'tts_prepare'"
)
_EVENT_OLD_TYPES = (
    "'page_view', 'scene_start', 'recording_start', 'recording_complete', "
    "'score_event', 'recommend_impression', 'recommend_click', 'practice_complete', "
    "'fun_action', 'corpus_hit', 'free_chat_open', 'free_chat_turn', "
    "'free_chat_switch', 'free_chat_reset', 'free_chat_rate'"
)


def upgrade() -> None:
    # ---- 内容域 ----
    op.create_table(
        "books",
        _bigint_pk(),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("author", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=8), server_default=sa.text("'en'"), nullable=False),
        sa.Column("level", sa.String(length=8), server_default=sa.text("'L1'"), nullable=False),
        sa.Column(
            "source",
            sa.String(length=32),
            server_default=sa.text("'public_domain'"),
            nullable=False,
        ),
        sa.Column("cover_color", sa.String(length=16), nullable=True),
        sa.Column("cover_emoji", sa.String(length=8), nullable=True),
        sa.Column("word_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("chapter_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'published'"), nullable=False
        ),
        *_timestamps(),
        sa.CheckConstraint("level IN ('L1', 'L2', 'L3', 'L4')", name=op.f("ck_books_level")),
        sa.CheckConstraint(
            "source IN ('public_domain', 'original', 'demo_only')", name=op.f("ck_books_source")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')", name=op.f("ck_books_status")
        ),
        sa.UniqueConstraint("title", "author", name=op.f("uq_books_title_author")),
    )

    op.create_table(
        "book_chapters",
        _bigint_pk(),
        sa.Column("book_id", sa.BigInteger(), nullable=False),
        sa.Column("chapter_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "content_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("word_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("char_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["book_id"], ["books.id"], name=op.f("fk_book_chapters_book_id_books")
        ),
        sa.UniqueConstraint("book_id", "chapter_no", name=op.f("uq_book_chapters_no")),
        sa.Index(op.f("ix_book_chapters_book"), "book_id"),
    )

    op.create_table(
        "dictionary_entries",
        _bigint_pk(),
        sa.Column("word", sa.String(length=128), nullable=False),
        sa.Column("phonetic", sa.String(length=255), nullable=True),
        sa.Column("translation", sa.Text(), nullable=True),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("pos", sa.String(length=16), nullable=True),
        _jsonb_col("exchange"),
        sa.Column("frequency", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("word", name=op.f("uq_dictionary_entries_word")),
    )

    op.create_table(
        "dictionary_forms",
        _bigint_pk(),
        sa.Column("form", sa.String(length=128), nullable=False),
        sa.Column("entry_id", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["dictionary_entries.id"],
            name=op.f("fk_dictionary_forms_entry_id_dictionary_entries"),
        ),
        sa.UniqueConstraint("form", name=op.f("uq_dictionary_forms_form")),
    )

    # ---- 用户域 ----
    op.create_table(
        "user_reading_progress",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("book_id", sa.BigInteger(), nullable=False),
        sa.Column("chapter_id", sa.BigInteger(), nullable=False),
        sa.Column("char_offset", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "content_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_reading_progress_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["book_id"], ["books.id"], name=op.f("fk_user_reading_progress_book_id_books")
        ),
        sa.ForeignKeyConstraint(
            ["chapter_id"],
            ["book_chapters.id"],
            name=op.f("fk_user_reading_progress_chapter_id_book_chapters"),
        ),
        sa.PrimaryKeyConstraint("user_id", "book_id", name=op.f("pk_user_reading_progress")),
    )

    op.create_table(
        "user_vocabulary",
        _bigint_pk(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("word", sa.String(length=128), nullable=False),
        sa.Column(
            "scene", sa.String(length=16), server_default=sa.text("'reading'"), nullable=False
        ),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'new'"), nullable=False),
        sa.Column("book_id", sa.BigInteger(), nullable=True),
        sa.Column("chapter_id", sa.BigInteger(), nullable=True),
        sa.Column("context_snippet", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_vocabulary_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["book_id"], ["books.id"], name=op.f("fk_user_vocabulary_book_id_books")
        ),
        sa.ForeignKeyConstraint(
            ["chapter_id"],
            ["book_chapters.id"],
            name=op.f("fk_user_vocabulary_chapter_id_book_chapters"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "scene IN ('reading', 'community', 'manual')", name=op.f("ck_user_vocabulary_scene")
        ),
        sa.CheckConstraint(
            "status IN ('new', 'learning', 'known')", name=op.f("ck_user_vocabulary_status")
        ),
        sa.UniqueConstraint("user_id", "word", name=op.f("uq_user_vocabulary_user_word")),
        sa.Index(op.f("ix_user_vocabulary_user_status_created"), "user_id", "status", "created_at"),
    )

    op.create_table(
        "reading_annotations",
        _bigint_pk(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("book_id", sa.BigInteger(), nullable=False),
        sa.Column("chapter_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column(
            "content_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("sentence_idx", sa.SmallInteger(), nullable=True),
        sa.Column("text_snippet", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_reading_annotations_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["book_id"], ["books.id"], name=op.f("fk_reading_annotations_book_id_books")
        ),
        sa.ForeignKeyConstraint(
            ["chapter_id"],
            ["book_chapters.id"],
            name=op.f("fk_reading_annotations_chapter_id_book_chapters"),
        ),
        sa.CheckConstraint(
            "kind IN ('highlight', 'note')", name=op.f("ck_reading_annotations_kind")
        ),
        sa.CheckConstraint(
            "end_offset >= start_offset", name=op.f("ck_reading_annotations_offset_order")
        ),
        sa.Index(op.f("ix_reading_annotations_chapter_user"), "chapter_id", "user_id"),
    )

    op.create_table(
        "tts_tasks",
        _bigint_pk(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("book_id", sa.BigInteger(), nullable=False),
        sa.Column("chapter_id", sa.BigInteger(), nullable=False),
        sa.Column("voice", sa.String(length=64), nullable=False),
        sa.Column("rate", sa.String(length=16), server_default=sa.text("'+0%'"), nullable=False),
        sa.Column(
            "provider", sa.String(length=32), server_default=sa.text("'auto'"), nullable=False
        ),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'queued'"), nullable=False
        ),
        sa.Column("total", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("done", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        _jsonb_col("error"),
        sa.Column("cancel_reason", sa.String(length=16), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_tts_tasks_user_id_users")),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], name=op.f("fk_tts_tasks_book_id_books")),
        sa.ForeignKeyConstraint(
            ["chapter_id"], ["book_chapters.id"], name=op.f("fk_tts_tasks_chapter_id_book_chapters")
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed', 'cancelled')",
            name=op.f("ck_tts_tasks_status"),
        ),
        sa.CheckConstraint(
            "cancel_reason IN ('user', 'system', 'timeout') OR cancel_reason IS NULL",
            name=op.f("ck_tts_tasks_cancel_reason"),
        ),
        sa.Index(op.f("ix_tts_tasks_chapter_status"), "chapter_id", "status"),
        sa.Index(op.f("ix_tts_tasks_status_finished"), "status", "finished_at"),
    )

    # ---- events.event_type 埋点扩 5 值（docs/46 V-17；PG 大表姿势同 0006） ----
    _drop_events_check()
    op.execute(
        f"ALTER TABLE events ADD CONSTRAINT {op.f('ck_events_event_type')} "
        f"CHECK (event_type IN ({_EVENT_NEW_TYPES})) NOT VALID"
    )
    op.execute(f"ALTER TABLE events VALIDATE CONSTRAINT {op.f('ck_events_event_type')}")


def _drop_events_check() -> None:
    op.drop_constraint(op.f("ck_events_event_type"), "events", type_="check")


def downgrade() -> None:
    _drop_events_check()
    op.create_check_constraint(
        op.f("ck_events_event_type"),
        "events",
        f"event_type IN ({_EVENT_OLD_TYPES})",
    )
    op.drop_table("tts_tasks")
    op.drop_table("reading_annotations")
    op.drop_table("user_vocabulary")
    op.drop_table("user_reading_progress")
    op.drop_table("dictionary_forms")
    op.drop_table("dictionary_entries")
    op.drop_table("book_chapters")
    op.drop_table("books")
