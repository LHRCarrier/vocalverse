"""books.cover_url：书封图（真实封面图支持 · 2026-09-14）

背景：书房（reading 模块）原先只有 `cover_color` + `cover_emoji` 两个**合成封面**字段
（前端 `MobileBookCover.vue` 渲染色块 + emoji），没有任何真实封面图能力 —— 而
`songs` 早就有 `cover_url`。演示/答辩场景需要"书架上是一本本真书"，故补齐。

口径：
- 值为**站点相对路径**（`/api/v1/reading/covers/<file>`）或外链；NULL 时前端回退合成封面，
  历史三本（Alice / P&P / Oz）行为完全不变（零迁移风险：可空列，无默认值）；
- 图片本体是**公版**资产，随仓库分发在 `data/seed/covers/`（`.gitignore` 已豁免 `data/seed/**`），
  由 `GET /api/v1/reading/covers/{name}` 提供（公开端点，白名单文件名，见 routes/reading.py）；
- 长度对齐 `songs.cover_url`（512）与 `media_assets` 的 URL 口径。

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("books", sa.Column("cover_url", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("books", "cover_url")
