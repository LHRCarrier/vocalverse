"""读书域（英文小说阅读）：books / book_chapters / dictionary_entries / dictionary_forms /
user_reading_progress / user_vocabulary / reading_annotations / tts_tasks。

写方矩阵（docs/10 §3 增补 · 数据模型拷问 V-1）：**全部 Python 写**（books/chapters/dictionary
由 seed 播种；用户数据由 reading 路由写）；Java 零改动；``check_single_writer`` 无需豁免
（本域模型不在 JAVA_WRITTEN_MODELS 即视为 Python 写）。管理端后置：books 未来若转 Java
编辑 → Single-Writer 反转 + ``content_version`` 守卫生效（docs/46 V-6）。

坐标系（docs/45 §3 / 拷问 V-20）：annotations 与 progress 的 ``start/end_offset``、``char_offset``
均为**章节正文整文本**的 char offset，与 ``app/reading/split.py::split_chapter`` 输出同源；
``content_version`` 为文本修订版本守卫（修订 +1 → 旧批注走重锚，不静默错位）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, bigint_pk, jsonb


class Book(TimestampMixin, Base):
    """书（内容域 · Python seed 写；公版书，source 标记版权口径）。

    - ``(title, author)`` 复合唯一 = seed 幂等自然键（同名异作/异版本场景，拷问 M-5）；
    - ``level`` 与 scenarios 一致用字符串 L1-L4（songs 的整数 1..4 语义不同，注释区分）；
    - ``word_count/chapter_count`` 为 seed 计算的派生计数器（静态）。
    """

    __tablename__ = "books"

    id: Mapped[int] = bigint_pk()
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'en'"))
    level: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'L1'"))
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'public_domain'")
    )
    cover_color: Mapped[str | None] = mapped_column(String(16))
    cover_emoji: Mapped[str | None] = mapped_column(String(8))
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    chapter_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'published'")
    )

    __table_args__ = (
        CheckConstraint("level IN ('L1', 'L2', 'L3', 'L4')", name="level"),
        CheckConstraint("source IN ('public_domain', 'original', 'demo_only')", name="source"),
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="status"),
        UniqueConstraint("title", "author", name="uq_books_title_author"),
    )


class BookChapter(TimestampMixin, Base):
    """章节（内容域 · Python seed 写）。

    - ``content`` = 段落以 ``\\n\\n`` 分隔的纯文本（**TEXT 无界**：SQLite 不强制 VARCHAR(n)
      长度而 PG 强制——正文一律 TEXT，拷问 V-3）；
    - ``content_version`` 文本修订版本（V-4）：修订 +1；批注/进度按版本重锚；
    - ``status`` 章级上下架（迁移 0013 · docs/50 §5.4）：与 ``books.status`` 同取值集，
      ``server_default='published'`` 保证既有章节行默认可见；上架校验要求每章 published（§6.1）。
    """

    __tablename__ = "book_chapters"

    id: Mapped[int] = bigint_pk()
    book_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("books.id"), nullable=False)
    chapter_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'published'")
    )

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="status"),
        UniqueConstraint("book_id", "chapter_no", name="uq_book_chapters_no"),
        Index("ix_book_chapters_book", "book_id"),
        # 运营侧按状态过滤（草稿/已归档章节清单）；上架校验走 (book_id, status) 前缀
        Index("ix_book_chapters_status", "status"),
    )


class DictionaryEntry(TimestampMixin, Base):
    """词典条目（ECDICT skywind3000 · MIT · 子集 seed 导入 · 只读）。

    - ``word`` 为归一化规范键（ECDICT sw 口径：小写、无连字符拆分），unique；
    - ``translation``（中文释义）多义多行（\\n 分隔），TEXT 整存（展示层取首义）；
    - ``exchange`` 词形变化（ECDICT：p 过去式 / d 过去分词 / i 现在分词 / 3 三单 /
      r 比较级 / t 最高级 / s 复数），jsonb 整存；``dictionary_forms`` 由它派生
      （反向词形索引，见 DictionaryForm）；
    - ``frequency`` 词频**位次**（ECDICT frq 优先、bnc 兜底；**值越小越常见**，注释防排序反向）。
    """

    __tablename__ = "dictionary_entries"

    id: Mapped[int] = bigint_pk()
    word: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    phonetic: Mapped[str | None] = mapped_column(String(255))
    translation: Mapped[str | None] = mapped_column(Text)
    definition: Mapped[str | None] = mapped_column(Text)
    pos: Mapped[str | None] = mapped_column(String(16))
    exchange: Mapped[dict[str, Any] | None] = mapped_column(jsonb())
    frequency: Mapped[int | None] = mapped_column(Integer)


class DictionaryForm(TimestampMixin, Base):
    """词形 → 词典条目反向索引（seed 从 dictionary_entries.exchange 派生；只读）。

    查词命中链：用户点词 → normalize_word → 精确查 ``dictionary_entries`` →
    未命中 → 查 ``dictionary_forms``（如 "inventions" → invention）→ 返回头词条目。
    """

    __tablename__ = "dictionary_forms"

    id: Mapped[int] = bigint_pk()
    form: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dictionary_entries.id"), nullable=False
    )


class UserReadingProgress(Base):
    """阅读进度（Python 写 · 单行 upsert 当前位；不做历史表，拷问 V-12）。

    - PK(user_id, book_id) 复合主键（无代理 id）；
    - ``char_offset`` 为**章内** char offset（Integer，章 2-5k 字符足够）；
    - ``content_version`` 版本守卫（章节修订 → 进度陈旧检测）；
    - FK RESTRICT：书/章不物理删（P7 内容不物理删策略）。
    """

    __tablename__ = "user_reading_progress"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, primary_key=True
    )
    book_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("books.id"), nullable=False, primary_key=True
    )
    chapter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("book_chapters.id"), nullable=False
    )
    char_offset: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    content_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class UserVocabulary(TimestampMixin, Base):
    """生词本（Python 写 · unique(user_id, word) 幂等）。

    - ``word`` = 归一化后词典头词（词形 → 头词在 lookup 阶段解析，context_snippet 存**原句**，
      含被点词形，如 "inventions" + 头词 "invention"）；
    - ``book_id`` first-write-wins：幂等添加不覆盖来源/语境（显式改走 PATCH）；
    - ``scene`` 预留社区划词/手动（社区划词为远期；届时 Java→Python 写需内部 REST 委托，
      登记 docs/46 V-10）；
    - ``chapter_id SET NULL``：删章后生词仍保（回到原文降级为书级）。
    """

    __tablename__ = "user_vocabulary"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    word: Mapped[str] = mapped_column(String(128), nullable=False)
    scene: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'reading'"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'new'"))
    book_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("books.id"))
    chapter_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("book_chapters.id", ondelete="SET NULL")
    )
    context_snippet: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("scene IN ('reading', 'community', 'manual')", name="scene"),
        CheckConstraint("status IN ('new', 'learning', 'known')", name="status"),
        UniqueConstraint("user_id", "word", name="uq_user_vocabulary_user_word"),
        Index(
            "ix_user_vocabulary_user_status_created",
            "user_id",
            "status",
            "created_at",
        ),
    )


class ReadingAnnotation(TimestampMixin, Base):
    """阅读批注（Python 写）：划词高亮（highlight）/ 带笔记批注（note）。

    - ``start_offset/end_offset`` = 章内 char offset 主锚（同一坐标系的权威见模块 docstring）；
    - ``content_version`` 版本守卫 + ``sentence_idx`` 重锚助手（起点句）+ ``text_snippet``
      选中快照（V-6：版本不匹配 → sentence_idx+snippet 重定位，仍失败标「已脱离原文」，
      **不自动删用户批注**）；
    - ``(chapter_id, user_id)`` 索引覆盖主查询路径（本章批注列表；V-13）。
    """

    __tablename__ = "reading_annotations"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    book_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("books.id"), nullable=False)
    chapter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("book_chapters.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    content_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    sentence_idx: Mapped[int | None] = mapped_column(SmallInteger)
    text_snippet: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(16))

    __table_args__ = (
        CheckConstraint("kind IN ('highlight', 'note')", name="kind"),
        CheckConstraint("end_offset >= start_offset", name="offset_order"),
        Index(
            "ix_reading_annotations_chapter_user",
            "chapter_id",
            "user_id",
        ),
    )


class TtsTask(TimestampMixin, Base):
    """听书预合成任务（Python 写 · 操作日志性质 —— 音频在文件缓存，本表只存进度元数据）。

    - 状态机：queued → running → done/failed/cancelled（VoiceStudio jobs 借鉴 · 自研实现）；
    - ``error`` jsonb（对齐 attempts.error 惯例：{reason, sentence_idx, engine}）；
    - ``provider`` 记录实际使用引擎（edge/kitten/…，informational，无 CHECK）；
    - 索引：``(chapter_id, status)``（prepare/启动扫孤儿）+ ``(status, finished_at)``（清理）；
    - 清理：done/failed/cancelled 超 30 天**物理删**（非用户业务数据；docs/45 §8）。
    """

    __tablename__ = "tts_tasks"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    book_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("books.id"), nullable=False)
    chapter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("book_chapters.id"), nullable=False
    )
    voice: Mapped[str] = mapped_column(String(64), nullable=False)
    rate: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'+0%'"))
    provider: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'auto'"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'queued'"))
    total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    done: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error: Mapped[dict[str, Any] | None] = mapped_column(jsonb())
    cancel_reason: Mapped[str | None] = mapped_column(String(16))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed', 'cancelled')",
            name="status",
        ),
        CheckConstraint(
            "cancel_reason IN ('user', 'system', 'timeout') OR cancel_reason IS NULL",
            name="cancel_reason",
        ),
        Index("ix_tts_tasks_chapter_status", "chapter_id", "status"),
        Index("ix_tts_tasks_status_finished", "status", "finished_at"),
    )


__all__ = [
    "Book",
    "BookChapter",
    "DictionaryEntry",
    "DictionaryForm",
    "UserReadingProgress",
    "UserVocabulary",
    "ReadingAnnotation",
    "TtsTask",
]
