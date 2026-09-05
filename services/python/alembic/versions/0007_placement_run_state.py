"""入学测试 run 状态机支撑（阶段 B1/B3）：attempts.placement_id + 部分唯一索引

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-03

依据（worklog 2026-09-03 阶段 B · local/34 B-1/B-3）：
- `attempts.placement_id`：attempt 从属于一个 in_progress 的 placements run（**消费标记**：
  已用过的 attempt 不再被其他 placement 复用；run 不复用 sessions，见 docs/10 §6 B-2）；
- `placements` 部分唯一索引 `(user_id) WHERE status='in_progress'`：**B1 并发 40910 守卫**
  —— 同一用户同时最多一个进行中的考试 run（PG/SQLite 均支持 partial unique index）。

注意：C8 已砍经验等级制（level_progress/xp_ledger），故**不新增** placements.kind，
复测用“最新 completed placement”语义（同一 user 多条 completed 记录）。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # attempts.placement_id（FK SET NULL：placements 不物理删除，SET NULL 仅防御）
    with op.batch_alter_table("attempts") as batch_op:
        batch_op.add_column(sa.Column("placement_id", sa.BigInteger(), nullable=True))
        batch_op.create_foreign_key(
            "fk_attempts_placement_id_placements",
            "placements",
            ["placement_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_attempts_placement_id", ["placement_id"])

    # B1 并发守卫：一用户一 in_progress run（PG/SQLite partial unique）
    op.create_index(
        "uq_placements_user_inprogress",
        "placements",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
        sqlite_where=sa.text("status = 'in_progress'"),
    )


def downgrade() -> None:
    op.drop_index("uq_placements_user_inprogress", table_name="placements")
    with op.batch_alter_table("attempts") as batch_op:
        batch_op.drop_index("ix_attempts_placement_id")
        batch_op.drop_constraint("fk_attempts_placement_id_placements", type_="foreignkey")
        batch_op.drop_column("placement_id")
