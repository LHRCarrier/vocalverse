"""媒体域迁移：media_assets 表 + user_profiles.handle 大小写不敏感唯一索引。

依据 docs/47 §3（定稿 v2 · 六路拷问合流 docs/48）：
- **写方矩阵**：media_assets 全 Python 写（docs/10 §3.1）；Java 只在 posts.media jsonb 存 URL，
  不读写本表（跨服务读表破坏写方矩阵，docs/48 §3-A）；
- **对外标识**：public_id（随机 hex，唯一）才是 URL 路径段——自增 id 不外露，
  否则逐号 curl 可枚举全站媒体（docs/48 B2）；
- **去重键**：行级唯一 = (owner_id, sha256) WHERE status='ready'（部分唯一索引）——
  全局唯一 + 软删会让「传→删→再传」永久失败、并可被单用户投毒（docs/48 B1）；
  物理文件按 sha256 内容寻址共享一份；
- **软删**：status='deleted' 只标记，物理文件不动；回收三条件设计登记 S4（docs/48 B19）；
- **handle 唯一**：user_profiles.handle 此前无任何唯一约束（docs/48 B17），
  本迁移先对重复值去重（保留最早一条，其余追加 -<user_id>）再建 lower(handle) 唯一索引。

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
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
        "media_assets",
        _bigint_pk(),
        sa.Column("public_id", sa.String(32), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.String(255), nullable=False),
        sa.Column("width", sa.BigInteger(), nullable=True),
        sa.Column("height", sa.BigInteger(), nullable=True),
        sa.Column("duration_s", sa.Numeric(8, 2), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'ready'")),
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
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_media_assets_owner_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint("kind IN ('image', 'video', 'avatar')", name="ck_media_assets_kind"),
        sa.CheckConstraint("status IN ('ready', 'deleted')", name="ck_media_assets_status"),
        sa.CheckConstraint("size_bytes > 0", name="ck_media_assets_size_positive"),
        sa.UniqueConstraint("public_id", name="uq_media_assets_public_id"),
    )
    op.create_index(
        "uq_media_assets_owner_sha_ready",
        "media_assets",
        ["owner_id", "sha256"],
        unique=True,
        postgresql_where=sa.text("status = 'ready'"),
        sqlite_where=sa.text("status = 'ready'"),
    )
    op.create_index(
        "ix_media_assets_owner_time", "media_assets", ["owner_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_media_assets_status_time", "media_assets", ["status", "created_at"], unique=False
    )

    # handle 去重（只动重复项，保留最早一条；不删除任何用户资料）
    op.execute(
        """
        UPDATE user_profiles p
           SET handle = p.handle || '-' || p.user_id
         WHERE p.handle IS NOT NULL
           AND p.id <> (
                SELECT MIN(q.id) FROM user_profiles q
                 WHERE lower(q.handle) = lower(p.handle)
           )
        """
    )
    op.create_index(
        "uq_user_profiles_handle_lower",
        "user_profiles",
        [sa.text("lower(handle)")],
        unique=True,
        postgresql_where=sa.text("handle IS NOT NULL"),
        sqlite_where=sa.text("handle IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_user_profiles_handle_lower", table_name="user_profiles")
    op.drop_index("ix_media_assets_status_time", table_name="media_assets")
    op.drop_index("ix_media_assets_owner_time", table_name="media_assets")
    op.drop_index("uq_media_assets_owner_sha_ready", table_name="media_assets")
    op.drop_table("media_assets")
