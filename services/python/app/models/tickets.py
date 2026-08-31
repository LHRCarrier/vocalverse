"""技术支持：tickets（工单）——**Java 写**（docs/06 §9.6 管理端最小集）。

用户提交反馈/报错/纠误 → open → processing → resolved → closed；
演示期可不做 admin 校验之外的复杂状态机（状态流转由 Java 应用层约束）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TicketStatuses, TimestampMixin, bigint_pk


class Ticket(TimestampMixin, Base):
    """工单（Java 写；处理人/回复可空=待认领状态）。

    - kind：feedback(反馈)/bug(报错)/content_correction(内容纠误)；
    - 用户侧只能建单 + 看状态；管理员处理/回复/关闭；
    - admin_id 引用 users（可空：未指派）。
    """

    __tablename__ = "tickets"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # 内容纠误目标（docs/11 Q-B18）：content_correction 挂到具体场景/歌曲/评分
    target_type: Mapped[str | None] = mapped_column(String(16))
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    title: Mapped[str | None] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{TicketStatuses.OPEN}'")
    )
    admin_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    admin_reply: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("kind IN ('feedback', 'bug', 'content_correction')", name="kind"),
        CheckConstraint(
            "target_type IN ('scene', 'song', 'attempt', 'none') OR target_type IS NULL",
            name="target_type",
        ),
        CheckConstraint("status IN ('open', 'processing', 'resolved', 'closed')", name="status"),
        Index("ix_tickets_status_created", "status", "created_at"),
        Index("ix_tickets_user_id", "user_id"),
    )
