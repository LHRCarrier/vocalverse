"""推荐系统 schema：5 张新表 + sessions/attempts CHECK 扩展（local/31 §2）

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-02

依据（local/26~32 推荐系统设计说明书）：
- 新表（均 **Python 写**，Alembic 唯一 schema 真源，Java 侧 ddl-auto=none 只映射）：
  * user_skill_state          —— 用户水平动态评价（local/31 §2.1）
  * material_difficulty       —— 素材难度评价（local/31 §2.2；次生表，多态引用无 FK）
  * user_mastery              —— 场景/素材级掌握度快照（local/31 §2.3）
  * user_corpus_mastery       —— 语料句级掌握明细（local/31 §2.3）
  * shadow_materials          —— 影子跟读素材内容库（local/31 §2.4；**Java 写**，Alembic 建表）
- 会话域扩展（local/31 §2.4 前置迁移项）：
  * sessions.kind CHECK + 'shadow'；sessions.shadow_material_id FK shadow_materials SET NULL；
  * attempts.kind CHECK + 'shadow_speech'；
- events 无需变更（recommend_impression/click 已在 0001/0002）。
- 迁移后：alembic upgrade head && alembic check 零 diff（docs/10 §7.1）；SQLite render_as_batch 兼容。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def _pki() -> sa.Column:
    """bigint_pk 统一表示：BIGINT IDENTITY（PG） / INTEGER（SQLite 单测）。"""
    return sa.Column(
        "id",
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.Identity(always=False),
        nullable=False,
    )


def _ts() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    # ---- 1. user_skill_state（先建，独立于其他表） ----
    op.create_table(
        "user_skill_state",
        _pki(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("pron_est", sa.Numeric(5, 2), nullable=False),
        sa.Column("flu_est", sa.Numeric(5, 2), nullable=False),
        sa.Column("est_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("est_level", sa.String(length=8), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("sample_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_sample_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("downgrade_streak", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("slump_guard_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source_version",
            sa.String(length=16),
            server_default=sa.text("'win-v1'"),
            nullable=False,
        ),
        *_ts(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_skill_state_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_skill_state")),
        sa.UniqueConstraint("user_id", name=op.f("uq_user_skill_state_user")),
        sa.CheckConstraint(
            "est_level IN ('L1', 'L2', 'L3', 'L4')", name=op.f("ck_user_skill_state_est_level")
        ),
        sa.CheckConstraint(
            "est_score BETWEEN 0 AND 100", name=op.f("ck_user_skill_state_score_range")
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1", name=op.f("ck_user_skill_state_conf_range")
        ),
        sa.CheckConstraint(
            "downgrade_streak >= 0", name=op.f("ck_user_skill_state_downgrade_streak")
        ),
    )

    # ---- 2. material_difficulty（次生表，多态引用无 FK） ----
    op.create_table(
        "material_difficulty",
        _pki(),
        sa.Column("content_type", sa.String(length=16), nullable=False),
        sa.Column("content_id", sa.BigInteger(), nullable=False),
        sa.Column("diff_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("diff_level", sa.String(length=8), nullable=False),
        sa.Column(
            "difficulty_source",
            sa.String(length=16),
            server_default=sa.text("'expert'"),
            nullable=False,
        ),
        sa.Column("prior_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("calibrated_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("calibration_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("distinct_users", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_calibrated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "features",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("version", sa.String(length=16), nullable=False),
        *_ts(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_difficulty")),
        sa.UniqueConstraint("content_type", "content_id", name=op.f("uq_material_difficulty_item")),
        sa.CheckConstraint(
            "content_type IN ('scene', 'shadow')", name=op.f("ck_material_difficulty_content_type")
        ),
        sa.CheckConstraint(
            "diff_level IN ('L1', 'L2', 'L3', 'L4')", name=op.f("ck_material_difficulty_diff_level")
        ),
        sa.CheckConstraint(
            "diff_score BETWEEN 0 AND 100", name=op.f("ck_material_difficulty_diff_score")
        ),
        sa.CheckConstraint(
            "difficulty_source IN ('expert', 'blend', 'calibrated')",
            name=op.f("ck_material_difficulty_difficulty_source"),
        ),
    )
    op.create_index(
        "ix_material_difficulty_source",
        "material_difficulty",
        ["difficulty_source", "version"],
        unique=False,
    )

    # ---- 3. user_mastery ----
    op.create_table(
        "user_mastery",
        _pki(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=16), nullable=False),
        sa.Column("content_id", sa.BigInteger(), nullable=False),
        sa.Column("mastery_score", sa.Numeric(5, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("pass_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'not_mastered'"), nullable=False
        ),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        *_ts(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_mastery_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_mastery")),
        sa.UniqueConstraint(
            "user_id", "content_type", "content_id", name=op.f("uq_user_mastery_item")
        ),
        sa.CheckConstraint(
            "content_type IN ('scene', 'shadow')", name=op.f("ck_user_mastery_content_type")
        ),
        sa.CheckConstraint(
            "status IN ('not_mastered', 'in_progress', 'mastered')",
            name=op.f("ck_user_mastery_status"),
        ),
        sa.CheckConstraint(
            "mastery_score BETWEEN 0 AND 100", name=op.f("ck_user_mastery_mastery_score")
        ),
    )
    op.create_index(
        "ix_user_mastery_user_status", "user_mastery", ["user_id", "status"], unique=False
    )

    # ---- 4. user_corpus_mastery（句级；FK scenarios，归档语义 RESTRICT） ----
    op.create_table(
        "user_corpus_mastery",
        _pki(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("scenario_id", sa.BigInteger(), nullable=False),
        sa.Column("line_index", sa.SmallInteger(), nullable=False),
        sa.Column("phrase", sa.Text(), nullable=False),
        sa.Column("mastery_score", sa.Numeric(5, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("pass_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'not_mastered'"), nullable=False
        ),
        *_ts(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_corpus_mastery_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenarios.id"],
            name=op.f("fk_user_corpus_mastery_scenario_id_scenarios"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_corpus_mastery")),
        sa.UniqueConstraint(
            "user_id", "scenario_id", "line_index", name=op.f("uq_user_corpus_mastery")
        ),
        sa.CheckConstraint(
            "status IN ('not_mastered', 'in_progress', 'mastered')",
            name=op.f("ck_user_corpus_mastery_status"),
        ),
        sa.CheckConstraint(
            "mastery_score BETWEEN 0 AND 100", name=op.f("ck_user_corpus_mastery_mastery_score")
        ),
    )
    op.create_index(
        "ix_user_corpus_mastery_scene",
        "user_corpus_mastery",
        ["user_id", "scenario_id", "status"],
        unique=False,
    )

    # ---- 5. shadow_materials（Java 写内容库，Alembic 建表） ----
    op.create_table(
        "shadow_materials",
        _pki(),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("audio_url", sa.String(length=512), nullable=False),
        sa.Column("wpm", sa.SmallInteger(), nullable=True),
        sa.Column("duration_s", sa.BigInteger(), nullable=True),
        sa.Column(
            "interest_tags",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.String(length=32),
            server_default=sa.text("'public_domain'"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'draft'"), nullable=False
        ),
        *_ts(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shadow_materials")),
        sa.CheckConstraint("level BETWEEN 1 AND 4", name=op.f("ck_shadow_materials_level")),
        sa.CheckConstraint(
            "source IN ('public_domain', 'original', 'demo_only')",
            name=op.f("ck_shadow_materials_source"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')", name=op.f("ck_shadow_materials_status")
        ),
    )
    op.create_index(
        "ix_shadow_materials_status_level", "shadow_materials", ["status", "level"], unique=False
    )

    # ---- 6. sessions.kind CHECK 扩值（+ shadow） ----
    op.drop_constraint(op.f("ck_sessions_kind"), "sessions", type_="check")
    op.create_check_constraint(
        op.f("ck_sessions_kind"), "sessions", "kind IN ('dialog', 'sing', 'defense', 'shadow')"
    )

    # ---- 7. sessions.shadow_material_id FK shadow_materials SET NULL ----
    op.add_column("sessions", sa.Column("shadow_material_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_sessions_shadow_material_id_shadow_materials",
        "sessions",
        "shadow_materials",
        ["shadow_material_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---- 8. attempts.kind CHECK 扩值（+ shadow_speech） ----
    op.drop_constraint(op.f("ck_attempts_kind"), "attempts", type_="check")
    op.create_check_constraint(
        op.f("ck_attempts_kind"),
        "attempts",
        "kind IN ('dialog_speech', 'free_practice', 'placement_item', "
        "'defense_answer', 'shadow_speech')",
    )


def downgrade() -> None:
    # 逆序回退：先约束，后表（FK 安全）
    op.drop_constraint(op.f("ck_attempts_kind"), "attempts", type_="check")
    op.create_check_constraint(
        op.f("ck_attempts_kind"),
        "attempts",
        "kind IN ('dialog_speech', 'free_practice', 'placement_item', 'defense_answer')",
    )

    op.drop_constraint(
        op.f("fk_sessions_shadow_material_id_shadow_materials"), "sessions", type_="foreignkey"
    )
    op.drop_column("sessions", "shadow_material_id")

    op.drop_constraint(op.f("ck_sessions_kind"), "sessions", type_="check")
    op.create_check_constraint(
        op.f("ck_sessions_kind"), "sessions", "kind IN ('dialog', 'sing', 'defense')"
    )

    op.drop_index("ix_shadow_materials_status_level", table_name="shadow_materials")
    op.drop_table("shadow_materials")

    op.drop_index("ix_user_corpus_mastery_scene", table_name="user_corpus_mastery")
    op.drop_table("user_corpus_mastery")

    op.drop_index("ix_user_mastery_user_status", table_name="user_mastery")
    op.drop_table("user_mastery")

    op.drop_index("ix_material_difficulty_source", table_name="material_difficulty")
    op.drop_table("material_difficulty")

    op.drop_table("user_skill_state")
