"""events.event_type CHECK 扩值：+free_chat_switch / free_chat_reset / free_chat_rate（docs/14 §12.3）

自由对话 Grok 式功能行（切场景/新对话/语速，2026-09-05）埋点事件入白名单；
同前序迁移大表姿势：NOT VALID + VALIDATE 分两段。

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-05
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_NEW_TYPES = (
    "'page_view', 'scene_start', 'recording_start', 'recording_complete', "
    "'score_event', 'recommend_impression', 'recommend_click', 'practice_complete', "
    "'fun_action', 'corpus_hit', 'free_chat_open', 'free_chat_turn', "
    "'free_chat_switch', 'free_chat_reset', 'free_chat_rate'"
)
_OLD_TYPES = (
    "'page_view', 'scene_start', 'recording_start', 'recording_complete', "
    "'score_event', 'recommend_impression', 'recommend_click', 'practice_complete', "
    "'fun_action', 'corpus_hit', 'free_chat_open', 'free_chat_turn'"
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
