"""管理端控制台 · 内容审核域（docs/50 §5.3.8~§5.3.9 · 迁移 0013）。

**写方矩阵**：两表全 **Java** 写（审核工单状态机与处置动作在 Java 侧事务内完成，docs/50 §6.2）；
Python 侧只读映射（列表/详情查询），**禁止任何写路径**。

设计要点（docs/50 §5.3）：

- **部分唯一索引保证幂等建单**（§5.3.8）：``uq_moderation_cases_target_pending`` 只约束
  ``status IN ('pending','escalated')`` 的行——同一目标不重复建待审单，终态历史行可留多条；
  举报同理（``uq_moderation_reports_reporter_target`` 仅 ``status='pending'``，防止刷举报；
  双方言声明 ``postgresql_where`` + ``sqlite_where``，SQLite 单测同样生效（docs/47 先例）；
- **跨域弱引用不加 FK**：``target_id`` 指向 posts/post_comments/media_assets/direct_messages，
  ``reporter_user_id`` 指向 ``users.id``——控制台与各业务域生命周期解耦，跨服务 FK 会把
  「删内容」绑死成「删审核历史」（§5.4 不新增 FK 跨域）；
- **``snapshot`` 只存摘要不存全文**（§5.3.8）：送审内容截断快照（``snippet`` 500 字 +
  结构化摘要），避免审核侧形成第二份内容留存（隐私最小化）；
- **审核决定不落本表**：前后状态写进 ``admin_audit_logs.detail``（单一审计流原则，§5.3.7），
  本域只存**当前状态**（``status``）。
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
    SmallInteger,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, bigint_pk, jsonb


class ModerationCase(TimestampMixin, Base):
    """审核工单（Java 写；状态机 pending→approved/rejected/escalated/withdrawn，docs/50 §6.2）。"""

    __tablename__ = "moderation_cases"

    id: Mapped[int] = bigint_pk()
    #: post | comment | media | direct_message
    #: （对应 posts / post_comments / media_assets / direct_messages 的 id）
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: auto（自动送审，本期未接引擎）/ report（举报建单）/ manual（人工建单）
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    #: spam|abuse|porn|violence|politics|ad|copyright|misinfo|other（值集由服务层约束）
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("2"))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    #: 送审内容快照（截断；不存全文，避免二次留存）
    snippet: Mapped[str | None] = mapped_column(String(500))
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(jsonb())
    #: 举报来源用户（users.id，跨域弱引用，不加 FK）
    reporter_user_id: Mapped[int | None] = mapped_column(BigInteger)
    assignee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    decided_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: 处置理由（经公开面白名单下发给作者，不含审核员身份，docs/50 §6.2 硬点 3）
    decision_note: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('post', 'comment', 'media', 'direct_message')", name="target_type"
        ),
        CheckConstraint("source IN ('auto', 'report', 'manual')", name="source"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'escalated', 'withdrawn')",
            name="status",
        ),
        # 幂等建单：同一目标在「待审/已升级」期间只允许一单（终态不占约束，历史可多条）
        Index(
            "uq_moderation_cases_target_pending",
            "target_type",
            "target_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'escalated')"),
            sqlite_where=text("status IN ('pending', 'escalated')"),
        ),
        Index("ix_moderation_cases_queue", "status", "priority", "created_at"),
        Index("ix_moderation_cases_assignee", "assignee_id", "status"),
    )


class ModerationReport(TimestampMixin, Base):
    """用户举报（Java 写；受理后关联工单，docs/50 §5.3.9）。

    与工单解耦：同一目标可被多人举报（``case_id`` 指向汇总工单），
    同一举报人对同一目标**待处理期间只能一条**（部分唯一索引，防刷）。
    """

    __tablename__ = "moderation_reports"

    id: Mapped[int] = bigint_pk()
    #: users.id（跨域弱引用，不加 FK）
    reporter_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    case_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("moderation_cases.id", ondelete="SET NULL")
    )
    handled_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('post', 'comment', 'media', 'direct_message')", name="target_type"
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'duplicate')", name="status"
        ),
        # 防刷：同一举报人对同一目标「待处理」期间只允许一条（终态可再次举报）
        Index(
            "uq_moderation_reports_reporter_target",
            "reporter_user_id",
            "target_type",
            "target_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        Index("ix_moderation_reports_pending", "status", "created_at"),
    )


class ModerationStatus:
    """``moderation_cases.status`` 取值（终态：approved / rejected / withdrawn）。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    WITHDRAWN = "withdrawn"


class ModerationReportStatus:
    """``moderation_reports.status`` 取值。"""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"


__all__ = [
    "ModerationCase",
    "ModerationReport",
    "ModerationStatus",
    "ModerationReportStatus",
]
