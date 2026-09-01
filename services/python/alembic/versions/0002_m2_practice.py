"""M2 practice schema: defense_profiles + CHECK 扩展

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-01

依据（docs/14 §6.1 · docs/17 §4 拍板 · docs/18 §3-J2）：
- 新表 defense_profiles：用户答辩档案（软删+脱敏，knowledge_bank 入库前 Pydantic 校验）；
- sessions.kind + 'defense'；attempts.kind + 'defense_answer'；
  scenario_messages.action + 'hint'；events.event_type + 'corpus_hit'（9→10 类）；
- sessions.profile_id FK defense_profiles SET NULL（与 scenario_id/song_id 语义一致）；
- 实现决策（docs/18）：defense 设定题数**复用 sessions.assigned_turns** 做会话级快照，不新增列；
- 枚举策略为 VARCHAR+命名 CHECK（非 PG ENUM）：变更 = DROP CONSTRAINT + ADD CONSTRAINT；
  events 为大表（只追加），ADD 用 NOT VALID + VALIDATE 分两段（docs/11 Q-A17）；
- 迁移后首日：alembic upgrade head && alembic check 零 diff 门禁（docs/10 §7.1）。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ---- 1. 新表 defense_profiles（先建，profile_id FK 依赖） ----
    op.create_table(
        "defense_profiles",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("outline", sa.Text(), nullable=False),
        sa.Column("highlights", sa.Text(), nullable=False),
        sa.Column("thesis_text", sa.Text(), nullable=True),
        sa.Column("question_count", sa.SmallInteger(), server_default=sa.text("6"), nullable=False),
        sa.Column(
            "emphasis", sa.String(length=16), server_default=sa.text("'balanced'"), nullable=False
        ),
        sa.Column(
            "knowledge_bank",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("bank_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_defense_profiles_user_id_users")
        ),
        sa.CheckConstraint(
            "question_count BETWEEN 5 AND 8", name=op.f("ck_defense_profiles_question_count")
        ),
        sa.CheckConstraint(
            "emphasis IN ('basic', 'balanced', 'divergent')",
            name=op.f("ck_defense_profiles_emphasis"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'deleted', 'generating', 'failed')",
            name=op.f("ck_defense_profiles_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_defense_profiles")),
    )
    op.create_index(
        "ix_defense_profiles_user_status", "defense_profiles", ["user_id", "status"], unique=False
    )

    # ---- 2. sessions.profile_id（SET NULL） ----
    op.add_column("sessions", sa.Column("profile_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_sessions_profile_id_defense_profiles",
        "sessions",
        "defense_profiles",
        ["profile_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---- 3. sessions.kind CHECK 扩值 ----
    op.drop_constraint(op.f("ck_sessions_kind"), "sessions", type_="check")
    op.create_check_constraint(
        op.f("ck_sessions_kind"), "sessions", "kind IN ('dialog', 'sing', 'defense')"
    )

    # ---- 4. attempts.kind CHECK 扩值 ----
    op.drop_constraint(op.f("ck_attempts_kind"), "attempts", type_="check")
    op.create_check_constraint(
        op.f("ck_attempts_kind"),
        "attempts",
        "kind IN ('dialog_speech', 'free_practice', 'placement_item', 'defense_answer')",
    )

    # ---- 5. scenario_messages.action CHECK 扩值（+hint） ----
    op.drop_constraint(op.f("ck_scenario_messages_action"), "scenario_messages", type_="check")
    op.create_check_constraint(
        op.f("ck_scenario_messages_action"),
        "scenario_messages",
        "action IN ('demo', 'correction', 'retry', 'hint') OR action IS NULL",
    )

    # ---- 6. events.event_type CHECK 扩值（大表：NOT VALID + VALIDATE 分两段） ----
    op.drop_constraint(op.f("ck_events_event_type"), "events", type_="check")
    op.execute(
        "ALTER TABLE events ADD CONSTRAINT ck_events_event_type "
        "CHECK (event_type IN ('page_view', 'scene_start', 'recording_start', "
        "'recording_complete', 'score_event', 'recommend_impression', "
        "'recommend_click', 'practice_complete', 'fun_action', 'corpus_hit')) "
        "NOT VALID"
    )
    op.execute("ALTER TABLE events VALIDATE CONSTRAINT ck_events_event_type")

    # ---- 7. reports.scope CHECK 扩值（会话级报告独立于 user/song 聚合，docs/14 §5） ----
    op.drop_constraint(op.f("ck_reports_scope"), "reports", type_="check")
    op.create_check_constraint(
        op.f("ck_reports_scope"),
        "reports",
        "scope IN ('global', 'user', 'scene', 'song', 'session')",
    )


def downgrade() -> None:
    # 逆序回退：先约束后表（FK 安全）
    op.drop_constraint(op.f("ck_reports_scope"), "reports", type_="check")
    op.create_check_constraint(
        op.f("ck_reports_scope"), "reports", "scope IN ('global', 'user', 'scene', 'song')"
    )

    op.execute("ALTER TABLE events DROP CONSTRAINT ck_events_event_type")
    op.create_check_constraint(
        op.f("ck_events_event_type"),
        "events",
        "event_type IN ('page_view', 'scene_start', 'recording_start', "
        "'recording_complete', 'score_event', 'recommend_impression', "
        "'recommend_click', 'practice_complete', 'fun_action')",
    )

    op.drop_constraint(op.f("ck_scenario_messages_action"), "scenario_messages", type_="check")
    op.create_check_constraint(
        op.f("ck_scenario_messages_action"),
        "scenario_messages",
        "action IN ('demo', 'correction', 'retry') OR action IS NULL",
    )

    op.drop_constraint(op.f("ck_attempts_kind"), "attempts", type_="check")
    op.create_check_constraint(
        op.f("ck_attempts_kind"),
        "attempts",
        "kind IN ('dialog_speech', 'free_practice', 'placement_item')",
    )

    op.drop_constraint(op.f("ck_sessions_kind"), "sessions", type_="check")
    op.create_check_constraint(op.f("ck_sessions_kind"), "sessions", "kind IN ('dialog', 'sing')")

    op.drop_constraint(
        op.f("fk_sessions_profile_id_defense_profiles"), "sessions", type_="foreignkey"
    )
    op.drop_column("sessions", "profile_id")

    op.drop_index("ix_defense_profiles_user_status", table_name="defense_profiles")
    op.drop_table("defense_profiles")
