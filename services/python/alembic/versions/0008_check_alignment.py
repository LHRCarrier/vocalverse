"""alembic check 存量漂移修正：user_skill_state 唯一约束名对齐元数据

0003 建表时以 op.f("uq_user_skill_state_user") 命名，而元数据（skill.py 的
user_id unique=True + naming_convention）期望 uq_user_skill_state_user_id——
DB 与元数据不一致导致 alembic check 报 add/remove_constraint 噪音。
本次仅重命名约束（同列同语义），不改变任何结构。

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-06
"""

from __future__ import annotations

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE user_skill_state "
        "RENAME CONSTRAINT uq_user_skill_state_user TO uq_user_skill_state_user_id"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE user_skill_state "
        "RENAME CONSTRAINT uq_user_skill_state_user_id TO uq_user_skill_state_user"
    )
