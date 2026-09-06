"""社区内容 S1：5 表（posts / post_comments / post_likes 键改造 / post_interactions / follows）+ user_profiles.handle/tint

依据 docs/37 §3.1（定稿）：
- 写方矩阵：社区 5 表全部 Java 写，Python 仅只读映射（app/models/community.py = alembic check 真源）；
- post_likes 由「打卡点赞」(liker_id, author_id, practice_date) 改造为「帖子点赞」(post_id, liker_id)：
  在线模式 0 行断言（旧键无数据才允许重建；离线 --sql 只渲染纯 DDL）；
- 部分唯一索引 uq_posts_checkin（每日一卡，仅 kind='checkin'）双方言声明（SQLite 单测兼容）；
- 索引形态：混排/领域 Tab 均为 (status, ...) 前缀（PG 反向扫描即 DESC 序，keyset 分页可命中）。

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ---- 0 行断言（仅在线；断言失败 = 整条回滚，人工清理后重跑，docs/37 §3.1） ----
    if not op.get_context().as_sql:
        conn = op.get_bind()
        rows = conn.execute(sa.text("SELECT count(*) FROM post_likes")).scalar_one()
        if rows:
            raise RuntimeError(
                f"post_likes 存在 {rows} 行旧键存量（打卡点赞语义），须人工清理后重跑迁移 0007"
            )

    # ---- user_profiles：社区展示字段（Java 写） ----
    op.add_column("user_profiles", sa.Column("handle", sa.String(length=32), nullable=True))
    op.add_column("user_profiles", sa.Column("tint", sa.String(length=16), nullable=True))

    # ---- posts ----
    op.create_table(
        "posts",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("domain", sa.String(length=16), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "tags",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "media",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'visible'"), nullable=False
        ),
        sa.Column("checkin_date", sa.Date(), nullable=True),
        sa.Column(
            "checkin_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("like_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("coin_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("comment_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("share_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
        sa.CheckConstraint(
            "kind IN ('article', 'video', 'checkin')", name=op.f("ck_posts_kind")
        ),
        sa.CheckConstraint(
            "domain IS NULL OR domain IN ('news', 'teaching', 'overseas')",
            name=op.f("ck_posts_domain"),
        ),
        sa.CheckConstraint(
            "status IN ('visible', 'hidden', 'deleted')", name=op.f("ck_posts_status")
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_posts_author_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name=op.f("fk_posts_session_id_sessions"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posts")),
        sa.UniqueConstraint("slug", name="uq_posts_slug"),
    )
    op.create_index(
        "ix_posts_feed_time", "posts", ["status", "created_at", "id"], unique=False
    )
    op.create_index(
        "ix_posts_domain_time", "posts", ["status", "domain", "created_at", "id"], unique=False
    )
    op.create_index("ix_posts_author", "posts", ["author_id", "created_at"], unique=False)
    # 每日一卡：部分唯一（仅 kind='checkin'）；双方言声明（SQLite 单测可建）
    op.create_index(
        "uq_posts_checkin",
        "posts",
        ["author_id", "checkin_date"],
        unique=True,
        postgresql_where=sa.text("kind = 'checkin'"),
        sqlite_where=sa.text("kind = 'checkin'"),
    )

    # ---- post_likes：推翻重建（0 行保证；新键 (post_id, liker_id)） ----
    op.drop_table("post_likes")
    op.create_table(
        "post_likes",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("post_id", sa.BigInteger(), nullable=False),
        sa.Column("liker_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["post_id"], ["posts.id"], name=op.f("fk_post_likes_post_id_posts")
        ),
        sa.ForeignKeyConstraint(
            ["liker_id"], ["users.id"], name=op.f("fk_post_likes_liker_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_post_likes")),
        sa.UniqueConstraint("post_id", "liker_id", name="uq_post_likes_post_liker"),
    )
    op.create_index("ix_post_likes_post", "post_likes", ["post_id"], unique=False)

    # ---- post_comments ----
    op.create_table(
        "post_comments",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("post_id", sa.BigInteger(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("root_id", sa.BigInteger(), nullable=True),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("reply_to_user_id", sa.BigInteger(), nullable=True),
        sa.Column("reply_to_nickname", sa.String(length=64), nullable=True),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'visible'"), nullable=False
        ),
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
        sa.CheckConstraint(
            "status IN ('visible', 'hidden', 'deleted')", name=op.f("ck_post_comments_status")
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_post_comments_author_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["post_id"], ["posts.id"], name=op.f("fk_post_comments_post_id_posts")
        ),
        sa.ForeignKeyConstraint(
            ["reply_to_user_id"],
            ["users.id"],
            name=op.f("fk_post_comments_reply_to_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["root_id"], ["post_comments.id"], name=op.f("fk_post_comments_root_id_post_comments")
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["post_comments.id"], name=op.f("fk_post_comments_parent_id_post_comments")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_post_comments")),
    )
    op.create_index(
        "ix_post_comments_status_post",
        "post_comments",
        ["status", "post_id", "created_at", "id"],
        unique=False,
    )

    # ---- post_interactions ----
    op.create_table(
        "post_interactions",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("post_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('like', 'coin', 'share')", name=op.f("ck_post_interactions_action")
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_post_interactions_actor_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["post_id"], ["posts.id"], name=op.f("fk_post_interactions_post_id_posts")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_post_interactions")),
        sa.UniqueConstraint(
            "actor_id", "post_id", "action", name="uq_post_interactions_actor_post_action"
        ),
    )
    op.create_index(
        "ix_post_interactions_post_action",
        "post_interactions",
        ["post_id", "action", "created_at"],
        unique=False,
    )

    # ---- follows ----
    op.create_table(
        "follows",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("follower_id", sa.BigInteger(), nullable=False),
        sa.Column("followee_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "follower_id <> followee_id", name=op.f("ck_follows_no_self_follow")
        ),
        sa.ForeignKeyConstraint(
            ["follower_id"], ["users.id"], name=op.f("fk_follows_follower_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["followee_id"], ["users.id"], name=op.f("fk_follows_followee_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_follows")),
        sa.UniqueConstraint("follower_id", "followee_id", name="uq_follows_follower_followee"),
    )
    op.create_index("ix_follows_followee", "follows", ["followee_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_follows_followee", table_name="follows")
    op.drop_table("follows")
    op.drop_index("ix_post_interactions_post_action", table_name="post_interactions")
    op.drop_table("post_interactions")
    op.drop_index("ix_post_comments_status_post", table_name="post_comments")
    op.drop_table("post_comments")
    op.drop_index("ix_post_likes_post", table_name="post_likes")
    op.drop_table("post_likes")
    op.drop_index("uq_posts_checkin", table_name="posts")
    op.drop_index("ix_posts_author", table_name="posts")
    op.drop_index("ix_posts_domain_time", table_name="posts")
    op.drop_index("ix_posts_feed_time", table_name="posts")
    op.drop_table("posts")
    op.drop_column("user_profiles", "tint")
    op.drop_column("user_profiles", "handle")
