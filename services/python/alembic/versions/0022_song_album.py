"""songs.album：专辑名（唱吧歌单「歌曲信息」补全 · 2026-09-22）

背景：唱吧歌单行/精选卡此前只显示「歌手」与练习元数据（难度 Lx、句数）。用户口径
「卡片上应该是歌曲信息」——补 `album` 作为纯展示字段，歌单行显示「歌手 · 专辑 + 时长」。

口径：
- **纯展示字段**（可空、无默认值、不参与选歌过滤/评分/参考旋律提取）；历史行 NULL，
  前端缺省时只显示歌手（行为与迁移前一致，零迁移风险）；
- 长度 128 对齐 `title`/`artist`；写入方仍为 Java（docs/10 §3 单写方纪律），
  由 `SongSeeder` 从 `data/seed/songs.json` 的 `album` 键播种（含空值回填）。

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("songs", sa.Column("album", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("songs", "album")
