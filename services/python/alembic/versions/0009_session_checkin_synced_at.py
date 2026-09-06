"""sessions.checkin_synced_at：打卡卡同步标记（docs/37 §5 · C-17）

练习收尾成功后 Python 调 /internal/checkin 委托 Java 落打卡卡（每日一卡、幂等键
(author_id, checkin_date)）；本列记录成功同步时间——NULL=未同步（失败不阻塞收尾，
留待 P2 补扫/重试；幂等键稳定 → 重试无害）。

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("checkin_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sessions", "checkin_synced_at")
