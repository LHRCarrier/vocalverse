"""私信（IM）域迁移：direct_messages + dm_read_state。

依据 docs/49（私信 IM 实施设计 · 定稿 · 两路拷问回填）与 docs/41 §1 口径变更：

- **写方矩阵**：两表全 **Java** 写（社区主服务，与 posts/follows 同域）；Python 侧
  仅在本文件声明只读映射（alembic check 的 metadata 真源），**禁止任何写路径**；
- **水位口径**：``dm_read_state.last_read_id``（而非时间戳）——时间戳水位在并发提交下会
  「跨过」尚未渲染的消息造成**永久漏未读**；消息 id 单调，取 max(现有, upTo) 无此问题
  （docs/49 §1.2 / §4.3 B2）；
- **发送方/接收方**：CHECK ``sender_id <> recipient_id``（自聊在服务层先拦 42203，DB 兜底）；
- **软删位**：``status`` 为将来治理预留（本轮无删除入口，恒 'visible'）；
- **索引**：按 (sender, recipient) / (recipient) / (sender) 建时间倒序友好索引——
  会话列表与未读判定（``id > last_read_id``）都走这三条之一；
- **主键形态**：``dm_read_state`` 用代理主键 ``id`` + 业务唯一键 ``uq_dm_read_state_user_peer``
  （本仓 Java/JPA 侧全部实体统一 ``@Id Long id``；业务唯一语义由唯一约束保证）。

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None


def _bigint_pk() -> sa.Column:
    return sa.Column(
        "id",
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.Identity(always=False),
        nullable=False,
        primary_key=True,
    )


def upgrade() -> None:
    op.create_table(
        "direct_messages",
        _bigint_pk(),
        sa.Column("sender_id", sa.BigInteger(), nullable=False),
        sa.Column("recipient_id", sa.BigInteger(), nullable=False),
        sa.Column("body", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'visible'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"], ["users.id"], name="fk_direct_messages_sender_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"], ["users.id"], name="fk_direct_messages_recipient_id_users"
        ),
        sa.CheckConstraint("sender_id <> recipient_id", name="ck_direct_messages_no_self_message"),
        sa.CheckConstraint("status IN ('visible', 'deleted')", name="ck_direct_messages_status"),
    )
    op.create_index(
        "ix_dm_pair_time", "direct_messages", ["sender_id", "recipient_id", "created_at", "id"]
    )
    op.create_index("ix_dm_recipient_time", "direct_messages", ["recipient_id", "created_at", "id"])
    op.create_index("ix_dm_sender_time", "direct_messages", ["sender_id", "created_at", "id"])

    op.create_table(
        "dm_read_state",
        _bigint_pk(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("peer_id", sa.BigInteger(), nullable=False),
        sa.Column("last_read_id", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_dm_read_state_user_id_users"),
        sa.ForeignKeyConstraint(["peer_id"], ["users.id"], name="fk_dm_read_state_peer_id_users"),
        sa.CheckConstraint("user_id <> peer_id", name="ck_dm_read_state_no_self_peer"),
        sa.UniqueConstraint("user_id", "peer_id", name="uq_dm_read_state_user_peer"),
    )
    op.create_index("ix_dm_read_state_user", "dm_read_state", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_dm_read_state_user", table_name="dm_read_state")
    op.drop_table("dm_read_state")
    op.drop_index("ix_dm_sender_time", table_name="direct_messages")
    op.drop_index("ix_dm_recipient_time", table_name="direct_messages")
    op.drop_index("ix_dm_pair_time", table_name="direct_messages")
    op.drop_table("direct_messages")
