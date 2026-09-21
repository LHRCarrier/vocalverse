"""酒馆（TRPG 跑团）域新表：campaigns / facts / tasks / clues / entities / events / messages

迁移来源：ai4u 跑团三件套（P2-22/24/28/29/42，docs/30-M3酒馆跑团实施设计 §3），按
VocalVerse 多用户口径补 ``user_id`` 归属；表名统一 ``trpg_`` 前缀。

- ``trpg_campaigns``：剧本实例（用户私有；narrative_summary 由状态渲染，P2-45）；
- ``trpg_facts``：剧情事实表，唯一键 ``(campaign_id, fact_key)`` 为 upsert 锚点；
  ``user_deleted_at`` 墓碑防提取复活（P2-35），``user_touched_at`` 用户手改优先（P2-26）；
- ``trpg_tasks`` / ``trpg_clues``：结构化任务/线索（快照注入与主持台消费）；
- ``trpg_entities``：实体注册表（pending 懒确认，P2-42）；
- ``trpg_events``：append-only 事件日志（判定卡数据源，P2-29）；
- ``trpg_messages``：对话流水 + 系统卡（kind=system，payload.trpgSys 协议）。

明细表对剧本 CASCADE（随父级删除；用户删号路径由 Java 侧软删，不触物理删除）；
``user_id`` 对 users 不写 ondelete（RESTRICT，与 sessions 同口径）。

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | None = None
depends_on: str | None = None


def _jsonb():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "trpg_campaigns",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("narrative_summary", sa.Text(), nullable=True),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.CheckConstraint("length(name) > 0", name=op.f("ck_trpg_campaigns_name_not_empty")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_trpg_campaigns_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trpg_campaigns")),
    )
    with op.batch_alter_table("trpg_campaigns", schema=None) as batch_op:
        batch_op.create_index(
            "ix_trpg_campaigns_user_active", ["user_id", "last_active_at"], unique=False
        )

    op.create_table(
        "trpg_facts",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("fact_key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.String(length=200), nullable=False),
        sa.Column(
            "modality", sa.String(length=8), server_default=sa.text("'fact'"), nullable=False
        ),
        sa.Column("speaker", sa.String(length=60), nullable=True),
        sa.Column("importance", sa.Float(), server_default=sa.text("0.5"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("user_touched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_message_id", sa.BigInteger(), nullable=True),
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
        sa.CheckConstraint("kind IN ('state', 'fact')", name=op.f("ck_trpg_facts_kind")),
        sa.CheckConstraint(
            "modality IN ('fact', 'claim', 'rumor')", name=op.f("ck_trpg_facts_modality")
        ),
        sa.CheckConstraint(
            "importance >= 0 AND importance <= 1", name=op.f("ck_trpg_facts_importance")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_trpg_facts_version")),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["trpg_campaigns.id"],
            name=op.f("fk_trpg_facts_campaign_id_trpg_campaigns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trpg_facts")),
        sa.UniqueConstraint("campaign_id", "fact_key", name="uq_trpg_facts_campaign_key"),
    )
    with op.batch_alter_table("trpg_facts", schema=None) as batch_op:
        batch_op.create_index("ix_trpg_facts_campaign_kind", ["campaign_id", "kind"], unique=False)

    op.create_table(
        "trpg_tasks",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=60), nullable=False),
        sa.Column(
            "status", sa.String(length=8), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column("scene", sa.String(length=40), nullable=True),
        sa.Column(
            "last_mentioned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_message_id", sa.BigInteger(), nullable=True),
        sa.Column("user_touched_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('active', 'done', 'failed')", name=op.f("ck_trpg_tasks_status")
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["trpg_campaigns.id"],
            name=op.f("fk_trpg_tasks_campaign_id_trpg_campaigns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trpg_tasks")),
    )
    with op.batch_alter_table("trpg_tasks", schema=None) as batch_op:
        batch_op.create_index(
            "ix_trpg_tasks_campaign_status", ["campaign_id", "status"], unique=False
        )

    op.create_table(
        "trpg_clues",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=60), nullable=False),
        sa.Column("content", sa.String(length=300), nullable=True),
        sa.Column("scene", sa.String(length=40), nullable=True),
        sa.Column("found", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("recovered", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "last_mentioned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_message_id", sa.BigInteger(), nullable=True),
        sa.Column("user_touched_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["trpg_campaigns.id"],
            name=op.f("fk_trpg_clues_campaign_id_trpg_campaigns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trpg_clues")),
    )
    with op.batch_alter_table("trpg_clues", schema=None) as batch_op:
        batch_op.create_index(
            "ix_trpg_clues_campaign_found", ["campaign_id", "found", "recovered"], unique=False
        )

    op.create_table(
        "trpg_entities",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column(
            "status", sa.String(length=8), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column("pending", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "last_mentioned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
            "kind IN ('npc', 'pc', 'task', 'clue', 'scene')", name=op.f("ck_trpg_entities_kind")
        ),
        sa.CheckConstraint(
            "status IN ('active', 'pending', 'cleared')", name=op.f("ck_trpg_entities_status")
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["trpg_campaigns.id"],
            name=op.f("fk_trpg_entities_campaign_id_trpg_campaigns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trpg_entities")),
        sa.UniqueConstraint(
            "campaign_id", "kind", "name", name="uq_trpg_entities_campaign_kind_name"
        ),
    )

    op.create_table(
        "trpg_events",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("round", sa.SmallInteger(), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["trpg_campaigns.id"],
            name=op.f("fk_trpg_events_campaign_id_trpg_campaigns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trpg_events")),
    )
    with op.batch_alter_table("trpg_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_trpg_events_campaign_round", ["campaign_id", "round"], unique=False
        )

    op.create_table(
        "trpg_messages",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("kind", sa.String(length=8), server_default=sa.text("'text'"), nullable=False),
        sa.Column("content", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("payload", _jsonb(), nullable=True),
        sa.Column("meta", _jsonb(), nullable=True),
        sa.Column("usage", _jsonb(), nullable=True),
        sa.Column("audio_url", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f("ck_trpg_messages_role")),
        sa.CheckConstraint("kind IN ('text', 'system')", name=op.f("ck_trpg_messages_kind")),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["trpg_campaigns.id"],
            name=op.f("fk_trpg_messages_campaign_id_trpg_campaigns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trpg_messages")),
    )
    with op.batch_alter_table("trpg_messages", schema=None) as batch_op:
        batch_op.create_index("ix_trpg_messages_campaign_id", ["campaign_id", "id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("trpg_messages", schema=None) as batch_op:
        batch_op.drop_index("ix_trpg_messages_campaign_id")
    op.drop_table("trpg_messages")

    with op.batch_alter_table("trpg_events", schema=None) as batch_op:
        batch_op.drop_index("ix_trpg_events_campaign_round")
    op.drop_table("trpg_events")

    op.drop_table("trpg_entities")

    with op.batch_alter_table("trpg_clues", schema=None) as batch_op:
        batch_op.drop_index("ix_trpg_clues_campaign_found")
    op.drop_table("trpg_clues")

    with op.batch_alter_table("trpg_tasks", schema=None) as batch_op:
        batch_op.drop_index("ix_trpg_tasks_campaign_status")
    op.drop_table("trpg_tasks")

    with op.batch_alter_table("trpg_facts", schema=None) as batch_op:
        batch_op.drop_index("ix_trpg_facts_campaign_kind")
    op.drop_table("trpg_facts")

    with op.batch_alter_table("trpg_campaigns", schema=None) as batch_op:
        batch_op.drop_index("ix_trpg_campaigns_user_active")
    op.drop_table("trpg_campaigns")
