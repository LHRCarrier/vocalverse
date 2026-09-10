"""sing_attempts 幂等键：UNIQUE(user_id, session_id)（docs/10 §4.3 · P1-3）

依据（2026-09-10 · 拷问报告 P1-3 / B-F7 / C-#3 / G-#9）：
`submit_song_audio` 的幂等是"先查后插"（`select ... .first()` 再 `db.add`），
并发双击/弱网重传时两个请求可同时通过检查 → 同一会话落**两行**（两份 pyin/DTW CPU +
重复 attempt 干扰看板），且**没有唯一键兜底**。

业务语义（与 service 层一致）：
- 同一 `(user, session)` 只有一行 → 重试 = **就地重置草稿行**（分数 NULL 的未定稿行可重写；
  已定稿行不再改写）；
- `session_id` 可空（会话删除时 SET NULL）：SQL 唯一索引对 NULL 不冲突，历史行不受影响。

迁移前自检：若库中已存在重复 `(user_id, session_id)` 行，本迁移**直接失败并给出清单**
（不静默删数据——合并/清理需人工决定）。

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None

_DUP_SQL = (
    "SELECT user_id, session_id, COUNT(*) AS n FROM sing_attempts "
    "WHERE session_id IS NOT NULL GROUP BY user_id, session_id HAVING COUNT(*) > 1"
)


def upgrade() -> None:
    # `--sql` 离线渲染（tests/test_models.py::test_alembic_offline_pg_render）下没有真实连接，
    # `op.get_bind().execute(...)` 返回 None：自检只在在线执行时跑，离线仅生成 DDL
    # （2026-09-10 踩坑：未加此守卫 → PG 方言离线渲染 AttributeError，门禁红）。
    if not context.is_offline_mode():
        dups = op.get_bind().execute(sa.text(_DUP_SQL)).fetchall()
        if dups:
            raise RuntimeError(
                "存在重复 (user_id, session_id) 的 sing_attempts 行，无法加唯一键——"
                "请先人工合并/清理后再迁移（不自动删数据）。前若干条："
                f"{[tuple(r) for r in dups[:5]]}"
            )
    op.create_unique_constraint(
        "uq_sing_attempts_user_session", "sing_attempts", ["user_id", "session_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_sing_attempts_user_session", "sing_attempts", type_="unique")
