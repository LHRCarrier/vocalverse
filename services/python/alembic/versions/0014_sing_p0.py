"""唱歌 P0 数据：songs.vocal_ref_url / sing_attempts 版本列 / pitch_extract_jobs 新表（docs/10）

依据（2026-09-09 组长拍板 D1~D7，local/唱歌P0六项实施计划书）：
- D1：songs.vocal_ref_url（独立参考人声轨，可空；pyin 输入「vocal_ref 优先 → audio_url 回退」）；
- D10（可追溯）：sing_attempts.scoring_version（评分算法世代，默认 'v1'）+
  ref_version（本次评分所用参考旋律提取世代快照，替代 lrc.revision 方案——LRC 重写 →
  song_pitch_refs 级联重建 → version 变化即表达世代，Java 零改动）；
- D2/D6：新表 pitch_extract_jobs（Python 独有 · 提取任务事实源）——queued/running/done/failed
  全生命周期 + 重试计数；songs.pitch_ref_status 仅作读侧门禁（Java 写，经内部 REST 委托翻转）；
  部分唯一索引 uq_pitch_extract_jobs_lrc_active：同一 LRC 世代只允许一个进行中任务
  （PG/SQLite 双方言 sqlite_where/postgresql_where 表达式索引）。

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "pitch_extract_jobs",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("song_id", sa.BigInteger(), nullable=False),
        sa.Column("lrc_id", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')",
            name=op.f("ck_pitch_extract_jobs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["lrc_id"],
            ["lrc.id"],
            name=op.f("fk_pitch_extract_jobs_lrc_id_lrc"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["song_id"],
            ["songs.id"],
            name=op.f("fk_pitch_extract_jobs_song_id_songs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pitch_extract_jobs")),
    )
    with op.batch_alter_table("pitch_extract_jobs", schema=None) as batch_op:
        batch_op.create_index("ix_pitch_extract_jobs_song_id", ["song_id"], unique=False)
        batch_op.create_index("ix_pitch_extract_jobs_status", ["status"], unique=False)
        batch_op.create_index(
            "uq_pitch_extract_jobs_lrc_active",
            ["lrc_id"],
            unique=True,
            sqlite_where=sa.text("status IN ('queued', 'running')"),
            postgresql_where=sa.text("status IN ('queued', 'running')"),
        )

    with op.batch_alter_table("sing_attempts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "scoring_version",
                sa.String(length=16),
                server_default=sa.text("'v1'"),
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("ref_version", sa.String(length=16), nullable=True))

    with op.batch_alter_table("songs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("vocal_ref_url", sa.String(length=512), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("songs", schema=None) as batch_op:
        batch_op.drop_column("vocal_ref_url")

    with op.batch_alter_table("sing_attempts", schema=None) as batch_op:
        batch_op.drop_column("ref_version")
        batch_op.drop_column("scoring_version")

    with op.batch_alter_table("pitch_extract_jobs", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_pitch_extract_jobs_lrc_active",
            sqlite_where=sa.text("status IN ('queued', 'running')"),
            postgresql_where=sa.text("status IN ('queued', 'running')"),
        )
        batch_op.drop_index("ix_pitch_extract_jobs_status")
        batch_op.drop_index("ix_pitch_extract_jobs_song_id")

    op.drop_table("pitch_extract_jobs")
