"""跟唱收藏：song_favorites 新表（docs/10）

依据（2026-09-10 组长需求）：唱吧「收藏」tab 必须由用户自主选择，而不是难度等启发式过滤；
每首歌一个收藏按钮，再点取消。收藏态 = 行存在，取消 = 删行（无软删状态列）。

- ``uq_song_favorites_user_song``：同一用户同一首歌唯一（重复收藏/取消失败转为幂等，
  见 app/sing/favorites.py——弱网重试与双击不得翻转状态）；
- ``song_id`` FK CASCADE：歌曲行删除时收藏随之清理（内容下架只置 archived 不删行，
  CASCADE 只兜真删的例外路径）；``user_id`` 无 ondelete（users 只禁用不物理删除）。
- 写归属：**Python**（用户交互数据；songs 仍 Java 独占写，本表只读引用其 id）。

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "song_favorites",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("song_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["song_id"],
            ["songs.id"],
            name=op.f("fk_song_favorites_song_id_songs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_song_favorites_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_song_favorites")),
        sa.UniqueConstraint("user_id", "song_id", name="uq_song_favorites_user_song"),
    )
    op.create_index(
        "ix_song_favorites_user_created", "song_favorites", ["user_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_song_favorites_user_created", table_name="song_favorites")
    op.drop_table("song_favorites")
