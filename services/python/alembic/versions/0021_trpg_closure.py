"""跑团闭环：实体立绘 + 一局收尾标记（docs/56 §4/§G）

- ``trpg_entities.portrait_media_id``（String(64)，nullable）：实体立绘指向
  ``media_assets.public_id``（URL = ``/api/v1/media/{public_id}``）；NULL = 未挂图
  （前端按实体名命中内置素材）。挂/卸走 ``POST|DELETE
  /api/v1/trpg/campaigns/{id}/entities/{entity_id}/portrait``（owner 校验 + 媒体归属校验）。
- ``trpg_campaigns.finished_at``（timestamptz，nullable）：``complete_quest`` 结算后置位，
  作为「一局已收尾」的归档判据；NULL = 尚在冒险中。

两列均纯 Python 写（与 trpg 域一致），Java 只读；可空列无回填、零迁移风险。

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "trpg_entities", sa.Column("portrait_media_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "trpg_campaigns", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("trpg_campaigns", "finished_at")
    op.drop_column("trpg_entities", "portrait_media_id")
