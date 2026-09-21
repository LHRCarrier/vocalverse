"""埋点扩展：target_type 枚举扩值（答辩/酒馆/读书/推荐/生词本/社区）

依据 docs/53 P1（2026-09-21 M3 收口）：

- ``events.target_type`` 原 CHECK 只允许 ``('scene','song','home')``，而答辩导师
  （``DefenseView``）上报 ``target_type='defense'`` → **IntegrityError 被当作重复上报静默吞掉**，
  答辩链路 scene_start/recording_start/recording_complete 实际 0 落库（docs/53 §0 盘点缺陷 1）。
- 本次扩到 9 值：``scene``（退役保留）/``song``/``home``/``defense``/``trpg``/``book``/
  ``card``/``vocab``/``post``；四处同步 = ``app/models/base.py:TargetTypes`` + 本迁移 +
  ``app/models/analytics.py`` CHECK + 前端 ``api/events.ts``。
- 大表 CHECK 演进按 docs/11 Q-A17：``NOT VALID`` + ``VALIDATE`` 两段（避免全表长锁）。

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-21
"""

from __future__ import annotations

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | None = None
depends_on: str | None = None

_NEW_VALUES = "'scene', 'song', 'home', 'defense', 'trpg', 'book', 'card', 'vocab', 'post'"
_OLD_VALUES = "'scene', 'song', 'home'"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_events_target_type"), "events", type_="check")
    op.execute(
        "ALTER TABLE events ADD CONSTRAINT ck_events_target_type "
        f"CHECK (target_type IN ({_NEW_VALUES}) OR target_type IS NULL) "
        "NOT VALID"
    )
    op.execute("ALTER TABLE events VALIDATE CONSTRAINT ck_events_target_type")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_events_target_type"), "events", type_="check")
    op.execute(
        "ALTER TABLE events ADD CONSTRAINT ck_events_target_type "
        f"CHECK (target_type IN ({_OLD_VALUES}) OR target_type IS NULL) "
        "NOT VALID"
    )
    op.execute("ALTER TABLE events VALIDATE CONSTRAINT ck_events_target_type")
