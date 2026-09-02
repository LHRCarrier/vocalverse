"""素材难度评价：material_difficulty（**Python 写**；local/31 §2.2）。

算法产物的次生表（仿 song_pitch_refs 先例，docs/10 §3.2-2）：以 content_type+content_id
多态引用 Java 内容库（无 FK，同 reports.scope_id 先例，docs/10 开放项 D-1）。
- diff_score/diff_level 是**统一尺度最终生效值**（local/26 §2：0-100，档界 85/70/55）；
- difficulty_source 三态（expert/blend/calibrated）仅作审计，推荐侧不区分（local/32 §8）；
- features JSONB 存维度明细/锚定/审计（local/32 A-1.1/A-3.3）；version 可追溯可回滚。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, DifficultySources, Levels, TimestampMixin, bigint_pk, jsonb


class MaterialDifficulty(TimestampMixin, Base):
    __tablename__ = "material_difficulty"

    id: Mapped[int] = bigint_pk()
    content_type: Mapped[str] = mapped_column(String(16), nullable=False)  # 'scene' | 'shadow'
    content_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 多态引用（无 FK）
    diff_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)  # 统一 0-100 难度分
    diff_level: Mapped[str] = mapped_column(String(8), nullable=False)  # 派生档位 L1~L4
    difficulty_source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{DifficultySources.EXPERT}'")
    )
    prior_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # 阶段一专家先验
    calibrated_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # 阶段二行为分量
    calibration_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    distinct_users: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_calibrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    features: Mapped[dict] = mapped_column(jsonb(), nullable=False, server_default=text("'{}'"))
    version: Mapped[str] = mapped_column(String(16), nullable=False)  # 难度模型/标定版本

    __table_args__ = (
        UniqueConstraint("content_type", "content_id", name="uq_material_difficulty_item"),
        CheckConstraint("content_type IN ('scene', 'shadow')", name="content_type"),
        CheckConstraint(
            f"diff_level IN ('{Levels.L1}', '{Levels.L2}', '{Levels.L3}', '{Levels.L4}')",
            name="diff_level",
        ),
        CheckConstraint("diff_score BETWEEN 0 AND 100", name="diff_score"),
        CheckConstraint(
            f"difficulty_source IN ('{DifficultySources.EXPERT}', '{DifficultySources.BLEND}', "
            f"'{DifficultySources.CALIBRATED}')",
            name="difficulty_source",
        ),
        Index("ix_material_difficulty_source", "difficulty_source", "version"),
    )
