"""用户水平动态评价：user_skill_state（**Python 写**；local/31 §2.1）。

连续能力估计（EWMA 窗口 + 定档分遗忘残余），供推荐匹配用；est_level 是"推荐用档"，
与 user_profiles.cefr_level（权威档，Java 写）并存、互不回写（local/26 §1.4，避免循环）。

字段来源 local/31 §2.1 + local/32 A-4.1/A-3.2 修订：
- est_score = 0.6·pron_est + 0.4·flu_est（统一尺度左端，与考试域两维同源）；
- est_level = 滞回(est_score)（local/30 §7 漏洞 2 修复：升档即时、降档需 <thr−h）；
- confidence = min(1, n/window)（local/30 漏洞 1 修复：两分支统一，单调）；
- downgrade_streak / slump_guard_until：低谷保护（local/32 A-3.2：连续降级 K 次冻结档位）。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Levels, TimestampMixin, bigint_pk


class UserSkillState(TimestampMixin, Base):
    __tablename__ = "user_skill_state"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    pron_est: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)  # 发音能力估计 0-100
    flu_est: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)  # 流利度能力估计 0-100
    est_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)  # 0.6·pron+0.4·flu
    est_level: Mapped[str] = mapped_column(String(8), nullable=False)  # 动态档（滞回后）
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, server_default=text("0")
    )
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_sample_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 低谷保护（local/32 A-3.2）：连续降级次数 + 冻结到期时刻（冻结期内 est_level 不动）
    downgrade_streak: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    slump_guard_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_version: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'win-v1'")
    )

    __table_args__ = (
        # 与 0003 迁移一致（DB 名为 uq_user_skill_state_user）；模型曾用 column unique=True
        # 生成 uq_user_skill_state_user_id 致 alembic check 漂移（2026-09-03 修复）。
        UniqueConstraint("user_id", name="uq_user_skill_state_user"),
        CheckConstraint(
            f"est_level IN ('{Levels.L1}', '{Levels.L2}', '{Levels.L3}', '{Levels.L4}')",
            name="est_level",
        ),
        CheckConstraint("est_score BETWEEN 0 AND 100", name="score_range"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="conf_range"),
        CheckConstraint("downgrade_streak >= 0", name="downgrade_streak"),
    )
