"""LLM 框架补齐：sessions 摘要三列 + usage_log 用量表（docs/26 §10.3）

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-03

依据（对比 ai4u schema 的两处缺口，docs/26 §10.3）：
- sessions.summary / summary_updated_at / summary_failed_at —— 摘要双轨落库
  （对照 ai4u agent_conversation.summary* 三列；摘要不再只存进程内 digest，
  长会话不失忆、跨会话续聊有基础，失败标记供前端提示与自动重试）；
- usage_log —— LLM 用量记账（对照 ai4u usage_log：source/model/prompt_tokens/…），
  M3 报表成本可溯源；**Python 写**，Alembic 唯一 schema 真源。
- 迁移后：alembic upgrade head && alembic check 零 diff；SQLite render_as_batch 兼容。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def _pki() -> sa.Column:
    return sa.Column(
        "id",
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.Identity(always=False),
        nullable=False,
    )


def _ts() -> list[sa.Column]:
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


def upgrade() -> None:
    # ---- sessions 摘要三列（直接 add_column：PG/SQLite 均支持 ALTER ADD COLUMN；
    # offline --sql 渲染不支持 batch_alter_table，故 batch 仅用于 downgrade 的 drop）----
    op.add_column("sessions", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "sessions", sa.Column("summary_updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "sessions", sa.Column("summary_failed_at", sa.DateTime(timezone=True), nullable=True)
    )

    # ---- usage_log 用量表（样式对齐 0003：显式 PK 约束 + length 形参）----
    op.create_table(
        "usage_log",
        _pki(),
        sa.Column("source", sa.String(length=32), nullable=False, server_default=sa.text("'turn'")),
        sa.Column("model", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("meta", sa.Text(), nullable=True),
        *_ts(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_log")),
    )
    op.create_index("ix_usage_log_created_at", "usage_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_usage_log_created_at", table_name="usage_log")
    op.drop_table("usage_log")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("summary_failed_at")
        batch.drop_column("summary_updated_at")
        batch.drop_column("summary")
