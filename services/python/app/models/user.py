"""账户与学习档案：users / user_profiles / placements / refresh_tokens。

写归属（docs/10 §3）：
- ``users`` / ``user_profiles`` / ``refresh_tokens`` —— **Java（管理端 + JWT 签发）**，Python 只读；
- ``placements`` —— **Python（入学测试评分管线）**；档位回写 user_profiles 由 Python 经
  内部 REST（service-token）委托 Java 完成，Java 仍是 user_profiles 唯一 DB 写者。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    AgeGroups,
    Base,
    Levels,
    Roles,
    TimestampMixin,
    UserStatus,
    bigint_pk,
    jsonb,
)

# ---------------------------------------------------------------------------
# 账户（Java 写）
# ---------------------------------------------------------------------------


class User(TimestampMixin, Base):
    """登录账户（Java 管理端注册/签发 JWT/禁用；Python 仅验签后读取）。

    - 用户名/邮箱大小写不敏感唯一（functional unique index，两库通用）；
    - role 只有 user/admin 两档（简单角色，docs/06 §9.6）；
    - 禁用走 status 字段，**禁止物理删除**（历史表全部引用 user_id）。
    """

    __tablename__ = "users"

    id: Mapped[int] = bigint_pk()
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # BCrypt
    nickname: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{Roles.USER}'")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{UserStatus.ACTIVE}'")
    )

    __table_args__ = (
        CheckConstraint(f"role IN ('{Roles.USER}', '{Roles.ADMIN}')", name="role"),
        CheckConstraint(
            f"status IN ('{UserStatus.ACTIVE}', '{UserStatus.DISABLED}')", name="status"
        ),
        # 大小写不敏感唯一：lower() 函数索引（PG 与 SQLite 均支持；
        # NULL 在两种方言的唯一索引中互不冲突，email 可空不需部分索引）
        Index("uq_users_username_lower", func.lower(username), unique=True),
        Index("uq_users_email_lower", func.lower(email), unique=True),
    )


class UserProfile(TimestampMixin, Base):
    """学习档案（Java 写；1:1 用户，注册后按年龄初始化默认音色/语速预选）。

    - cefr_level 是「最近一次入学测试/人工校正」的快照，随 placements 更新（经 Java 内部 API）；
    - age_group 只驱动 TTS 语速/音色/默认难度档（docs/06 §9.2），不参与内容过滤；
    - interest_tags 为推荐兴趣标签数组（推荐候选池过滤，docs/06 §9.5）。
    """

    __tablename__ = "user_profiles"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, unique=True
    )
    age_group: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{AgeGroups.ADULT}'")
    )
    cefr_level: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text(f"'{Levels.L1}'")
    )
    learning_goal: Mapped[str | None] = mapped_column(String(255))
    interest_tags: Mapped[dict] = mapped_column(
        jsonb(), nullable=False, server_default=text("'[]'")
    )
    voice_rate: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'normal'")
    )
    voice_type: Mapped[str | None] = mapped_column(String(32))  # 3 音色预设 key
    preferred_difficulty: Mapped[int | None] = mapped_column(SmallInteger)
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    # 档位来源审计（docs/11 Q-B07）：placement=入学测试委托写入，manual=管理员改档；
    # cefr_level_at 用于对账（Python 读档前发现最新 completed placement 更新则重试委托）
    cefr_level_source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'manual'")
    )
    cefr_level_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            f"age_group IN ('{AgeGroups.CHILD}', '{AgeGroups.TEEN}', "
            f"'{AgeGroups.ADULT}', '{AgeGroups.SENIOR}')",
            name="age_group",
        ),
        CheckConstraint(
            f"cefr_level IN ('{Levels.L1}', '{Levels.L2}', '{Levels.L3}', '{Levels.L4}')",
            name="cefr_level",
        ),
        CheckConstraint("voice_rate IN ('slow', 'normal', 'fast')", name="voice_rate"),
        CheckConstraint("preferred_difficulty BETWEEN 1 AND 4", name="preferred_difficulty"),
        CheckConstraint("cefr_level_source IN ('placement', 'manual')", name="cefr_level_source"),
    )


class RefreshToken(TimestampMixin, Base):
    """refresh JWT 登记（Java 写；仅存 SHA-256 哈希，不存明文 Token）。

    - rotation：刷新时旧行置 revoked_at，写入新行（演示期单用户多设备不做限制，见 docs/10 开放项）；
    - expires_at 由 Java 实现定时清理或惰性判定。
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    family_id: Mapped[str | None] = mapped_column(String(36))  # rotation 同族，可整族吊销
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(45))

    __table_args__ = (
        Index("uq_refresh_tokens_token_hash", "token_hash", unique=True),
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )


# ---------------------------------------------------------------------------
# 入学测试（Python 写）
# ---------------------------------------------------------------------------


class Placement(TimestampMixin, Base):
    """入学测试记录（Python 评分管线写；1 用户可多次，取最新 completed 判档）。

    - exam_revision：固定朗读题版本（docs/06 §9.2 可复现要求；题库版本变更时递增）；
    - 综合分 S = 0.4·发音 + 0.3·语法 + 0.3·流利度（docs/06 §9.2，阈值写配置）；
    - level 为按 S 折算的快照（写配置可调档位映射）；
    - details 存每题明细 [{item_index, transcript, pron/gram/flu, errors}]。
    """

    __tablename__ = "placements"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    exam_revision: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'in_progress'")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 评分/档位列：Numeric(5,2) 在 SQLAlchemy 运行时返回 Decimal（勿用 float 注解，
    # 见 docs/11 Q-A02；API 层负责 Decimal→int/float 序列化口径）
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    pron_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    flu_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    gram_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    level: Mapped[str | None] = mapped_column(String(8))
    details: Mapped[dict] = mapped_column(jsonb(), nullable=False, server_default=text("'{}'"))

    __table_args__ = (
        CheckConstraint("status IN ('in_progress', 'completed', 'abandoned')", name="status"),
        CheckConstraint(
            f"level IN ('{Levels.L1}', '{Levels.L2}', '{Levels.L3}', '{Levels.L4}')",
            name="level",
        ),
        Index("ix_placements_user_started", "user_id", "started_at"),
    )
