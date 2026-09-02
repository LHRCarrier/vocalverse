"""匹配机制：user_mastery / user_corpus_mastery（**Python 写**；local/31 §2.3）。

- user_mastery：场景/素材级掌握度快照，**推荐 SQL 直读**（未掌握判定的 P0 键）；
- user_corpus_mastery：语料句级掌握明细，**聚合派生** user_mastery + 报告"需纠错/待练"栏
  + 复习席句级细化（local/29 §3.1 分工）。两表 Python 写、会话收尾同事务。

派生链：attempts × corpus_hit → user_corpus_mastery（句级）→ 聚合 → user_mastery（场景级）。
场景级状态 = 句级聚合：全部 mastered → mastered；任一 not_mastered → not_mastered；
否则 in_progress。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, MasteryStatus, TimestampMixin, bigint_pk, jsonb


class UserMastery(TimestampMixin, Base):
    __tablename__ = "user_mastery"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    content_type: Mapped[str] = mapped_column(String(16), nullable=False)  # 'scene' | 'shadow'
    content_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 多态引用（无 FK）
    mastery_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )  # 掌握度 0-100（0.6·pron+0.4·flu EWMA）
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    pass_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{MasteryStatus.NOT_MASTERED}'")
    )
    details: Mapped[dict] = mapped_column(jsonb(), nullable=False, server_default=text("'{}'"))

    __table_args__ = (
        UniqueConstraint("user_id", "content_type", "content_id", name="uq_user_mastery_item"),
        CheckConstraint("content_type IN ('scene', 'shadow')", name="content_type"),
        CheckConstraint(
            f"status IN ('{MasteryStatus.NOT_MASTERED}', '{MasteryStatus.IN_PROGRESS}', "
            f"'{MasteryStatus.MASTERED}')",
            name="status",
        ),
        CheckConstraint("mastery_score BETWEEN 0 AND 100", name="mastery_score"),
        Index("ix_user_mastery_user_status", "user_id", "status"),
    )


class UserCorpusMastery(TimestampMixin, Base):
    __tablename__ = "user_corpus_mastery"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    scenario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("scenarios.id"), nullable=False
    )  # 场景；归档语义 RESTRICT（local/29 §10.3-2，待拍板）
    line_index: Mapped[int] = mapped_column(
        SmallInteger, nullable=False
    )  # target_corpus 第几句（1..n）
    phrase: Mapped[str] = mapped_column(Text, nullable=False)  # 语料句快照（原文，审计对照）
    mastery_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    pass_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{MasteryStatus.NOT_MASTERED}'")
    )

    __table_args__ = (
        UniqueConstraint("user_id", "scenario_id", "line_index", name="uq_user_corpus_mastery"),
        CheckConstraint(
            f"status IN ('{MasteryStatus.NOT_MASTERED}', '{MasteryStatus.IN_PROGRESS}', "
            f"'{MasteryStatus.MASTERED}')",
            name="status",
        ),
        CheckConstraint("mastery_score BETWEEN 0 AND 100", name="mastery_score"),
        Index("ix_user_corpus_mastery_scene", "user_id", "scenario_id", "status"),
    )
