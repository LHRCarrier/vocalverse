"""events.event_type CHECK 扩值：+free_chat_open / free_chat_turn（docs/14 §12.3）

自由对话（MVP，2026-09-05）埋点事件入白名单；
同 0002 大表姿势：NOT VALID + VALIDATE 分两段（存量数据零扫描风险）。

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-05
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_NEW_TYPES = (
    "'page_view', 'scene_start', 'recording_start', 'recording_complete', "
    "'score_event', 'recommend_impression', 'recommend_click', 'practice_complete', "
    "'fun_action', 'corpus_hit', 'free_chat_open', 'free_chat_turn'"
)
_OLD_TYPES = (
    "'page_view', 'scene_start', 'recording_start', 'recording_complete', "
    "'score_event', 'recommend_impression', 'recommend_click', 'practice_complete', "
    "'fun_action', 'corpus_hit'"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_events_event_type"), "events", type_="check")
    op.execute(
        f"ALTER TABLE events ADD CONSTRAINT ck_events_event_type "
        f"CHECK (event_type IN ({_NEW_TYPES})) NOT VALID"
    )
    op.execute("ALTER TABLE events VALIDATE CONSTRAINT ck_events_event_type")


def downgrade() -> None:
    op.execute("ALTER TABLE events DROP CONSTRAINT ck_events_event_type")
    op.create_check_constraint(
        op.f("ck_events_event_type"),
        "events",
        f"event_type IN ({_OLD_TYPES})",
    )
