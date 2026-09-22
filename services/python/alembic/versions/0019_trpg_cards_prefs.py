"""酒馆扩展：场景卡（启用 + 用户私有）与用户偏好（跨设备）

依据 docs/52 §12（2026-09-21 组长追加需求）：

- ``trpg_scenario_cards``：开局模板卡。``owner_user_id`` NULL = 平台固定卡（管理端维护、
  上架后所有用户可选）；非 NULL = 用户私有卡（按关键词 LLM 生成，仅本人可见）。
  ``template``（JSONB）承载初始 pc/facts/tasks/clues，应用时经服务器白名单校验后落 campaign。
- ``trpg_user_prefs``：酒馆用户偏好（lang=DM 输出语言 / voice_enabled=自动朗读开关 /
  voice_name=音色预留）。user_id 唯一（一人一行，upsert）。

两表均 Python 写（App + Python 控制台端点），Java 只读（权限码 content:scenario:*）。

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | None = None
depends_on: str | None = None


def _jsonb():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "trpg_scenario_cards",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=8), server_default=sa.text("'admin'"), nullable=False),
        sa.Column(
            "status", sa.String(length=12), server_default=sa.text("'draft'"), nullable=False
        ),
        sa.Column("title", sa.String(length=60), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=True),
        sa.Column("language", sa.String(length=8), server_default=sa.text("'zh'"), nullable=False),
        sa.Column("tags", _jsonb(), nullable=True),
        sa.Column("scene", sa.String(length=40), nullable=True),
        sa.Column("opening_line", sa.Text(), nullable=True),
        sa.Column("template", _jsonb(), nullable=True),
        sa.Column("keywords", sa.String(length=200), nullable=True),
        sa.Column("generated_by", sa.String(length=12), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('admin', 'user')", name=op.f("ck_trpg_scenario_cards_source")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name=op.f("ck_trpg_scenario_cards_status"),
        ),
        sa.CheckConstraint(
            "language IN ('zh', 'en')", name=op.f("ck_trpg_scenario_cards_language")
        ),
        sa.CheckConstraint(
            "length(title) > 0", name=op.f("ck_trpg_scenario_cards_title_not_empty")
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_trpg_scenario_cards_owner_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trpg_scenario_cards")),
    )
    with op.batch_alter_table("trpg_scenario_cards", schema=None) as batch_op:
        batch_op.create_index(
            "ix_trpg_scenario_cards_owner_status", ["owner_user_id", "status"], unique=False
        )
        batch_op.create_index("ix_trpg_scenario_cards_status_id", ["status", "id"], unique=False)

    op.create_table(
        "trpg_user_prefs",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("lang", sa.String(length=8), server_default=sa.text("'zh'"), nullable=False),
        sa.Column("voice_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("voice_name", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("lang IN ('zh', 'en')", name=op.f("ck_trpg_user_prefs_lang")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_trpg_user_prefs_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trpg_user_prefs")),
        sa.UniqueConstraint("user_id", name="uq_trpg_user_prefs_user_id"),
    )


def downgrade() -> None:
    op.drop_table("trpg_user_prefs")

    with op.batch_alter_table("trpg_scenario_cards", schema=None) as batch_op:
        batch_op.drop_index("ix_trpg_scenario_cards_status_id")
        batch_op.drop_index("ix_trpg_scenario_cards_owner_status")
    op.drop_table("trpg_scenario_cards")
