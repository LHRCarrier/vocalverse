"""管理端控制台 · RBAC 与审计域（docs/50 §5.3.1~§5.3.7 · 迁移 0013）。

**写方矩阵**：7 张表全 **Java** 写（独立控制台 `services/java` 的 rbac/audit 模块，
docs/50 §5.1 归属表）；Python 侧只在本文件声明只读映射（alembic check 的 metadata 真源），
**禁止任何写路径**——越权写由 `scripts/check_single_writer.py` 硬门禁拦截。

设计要点（docs/50 §5.3，逐条对齐）：

- **临时锁定 ≠ 永久停用**（§5.3.1 决策 · 拷问 A-3）：``status`` 只表达「启用/停用」，
  临时锁定用 ``locked_until``，避免 ``status=locked`` 与 ``locked_until`` 双真源；
- **``token_epoch``**：停用/改权/改密时 +1 → 已签发令牌即刻失效（无需维护黑名单）；
- **``created_by`` 自引用 SET NULL**：建号人被删后账号仍存续（不连坐物理删）；
- **``admin_role_permissions`` 复合主键**：无代理 id（关系表），改权=整行增删；
- **审计日志 append-only**（§5.3.7 单一审计流原则 · 拷问 A-1）：只记 ``created_at``，
  审核决定的前后状态写进 ``detail``，**不再单独建 moderation_actions**；
- **``admin_login_attempts.admin_user_id`` 不加 FK**：登录尝试是安全流水，
  账号被删后仍须可追溯（弱引用，与 ``reporter_user_id`` 同法）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, TimestampMixin, bigint_pk, jsonb


class AdminUser(TimestampMixin, Base):
    """管理端账号（Java 写）。

    与 ``users`` 分离：控制台账号不复用 C 端账户（身份/审计/生命周期完全不同，docs/50 §4.1）。
    """

    __tablename__ = "admin_users"

    id: Mapped[int] = bigint_pk()
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)  # BCrypt
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("admin_roles.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    #: 连续失败计数（登录成功后清零）；锁定阈值与时长由 Java 服务层决定
    failed_attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    #: 临时锁定截止时刻（NULL=未锁定）；与 status 正交，避免双真源（§5.3.1 决策）
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: 令牌纪元：停用/改权/改密时 +1 → 旧 JWT 立即失效（claim 比对，无需黑名单）
    token_epoch: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_ip: Mapped[str | None] = mapped_column(String(45))  # IPv6 最长 45
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled')", name="status"),
        # 用户名大小写不敏感唯一（同 users 惯例：lower() 函数索引，PG/SQLite 通用）
        Index("uq_admin_users_username_lower", func.lower(username), unique=True),
        Index("ix_admin_users_role_status", "role_id", "status"),
    )


class AdminRole(TimestampMixin, Base):
    """控制台角色（Java 写；ops / content / moderation 三角色由 seed 播种，docs/50 §4.2）。

    ``builtin`` 标记内置角色（不可删除，只可改权限）；``rank`` 越小权限越高。
    """

    __tablename__ = "admin_roles"

    id: Mapped[int] = bigint_pk()
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("100"))

    __table_args__ = (UniqueConstraint("code", name="uq_admin_roles_code"),)


class AdminPermission(CreatedAtMixin, Base):
    """权限码目录（Java 写；``<domain>.<resource>.<action>``，docs/50 §4.2）。

    目录是**代码常量的落库快照**（启动时对账 upsert），故不改行——只记 ``created_at``。
    """

    __tablename__ = "admin_permissions"

    id: Mapped[int] = bigint_pk()
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    module: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    sort: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))

    __table_args__ = (
        UniqueConstraint("code", name="uq_admin_permissions_code"),
        Index("ix_admin_permissions_module", "module", "sort"),
    )


class AdminRolePermission(CreatedAtMixin, Base):
    """角色↔权限关系（Java 写；无代理 id，复合主键 ``pk_admin_role_permissions``）。"""

    __tablename__ = "admin_role_permissions"

    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("admin_roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("admin_permissions.id", ondelete="CASCADE"), primary_key=True
    )


class AdminSession(CreatedAtMixin, Base):
    """控制台刷新令牌会话（Java 写；可吊销，docs/50 §4.1）。

    只存 ``sha256`` 哈希（不存明文 token）；吊销语义靠 ``revoked_at`` + ``revoke_reason``，
    行永不物理删（审计可归因）。
    """

    __tablename__ = "admin_sessions"

    id: Mapped[int] = bigint_pk()
    admin_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False
    )
    #: sha256 hex（定长 64）；唯一约束名按 docs/50 §5.3.5 固定为 uq_admin_sessions_token_hash
    refresh_token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: logout | rotated | admin_revoked | role_changed（值集由服务层约束，不建 CHECK）
    revoke_reason: Mapped[str | None] = mapped_column(String(32))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(45))

    __table_args__ = (
        UniqueConstraint("refresh_token_hash", name="uq_admin_sessions_token_hash"),
        # 会话清理（过期扫描）主路径：按人 + 过期时刻倒序
        Index("ix_admin_sessions_user_expires", "admin_user_id", text("expires_at DESC")),
    )


class AdminLoginAttempt(CreatedAtMixin, Base):
    """登录尝试流水（Java 写；锁定与风控依据，docs/50 §5.3.6）。

    ``admin_user_id`` 为**弱引用**（不加 FK）：账号被删后安全流水仍需可追溯。
    """

    __tablename__ = "admin_login_attempts"

    id: Mapped[int] = bigint_pk()
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    admin_user_id: Mapped[int | None] = mapped_column(BigInteger)  # 弱引用，无 FK
    ip: Mapped[str | None] = mapped_column(String(45))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: bad_password | locked | disabled | unknown_user | ok（值集由服务层约束，不建 CHECK）
    reason: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (
        # 锁定判定：同用户名近期失败次数；风控：同 IP 撞库
        Index("ix_admin_login_attempts_username_created", "username", text("created_at DESC")),
        Index("ix_admin_login_attempts_ip_created", "ip", text("created_at DESC")),
    )


class AdminAuditLog(CreatedAtMixin, Base):
    """管理员写操作留痕（Java 写；**append-only**，无 ``updated_at``，docs/50 §5.3.7）。

    **单一审计流原则**（§5.3.7 · 拷问 A-1）：审核决定不另建 ``moderation_actions`` 表——
    决定的前后状态写进 ``detail``（``{prevStatus,nextStatus,reasonCode}``），一处查「谁做了什么」。

    - ``admin_username`` 快照：账号被删也归因得出来（``admin_user_id`` 为 SET NULL FK）；
    - **append-only 的边界**：本表业务列只增不改（不设 ``updated_at``）。``admin_user_id``
      的 ``ON DELETE SET NULL`` 是唯一例外——它由 DB 在**账号被物理删**时改写。管理端账号按
      §4.1 只停用（``status='disabled'``）不删除，故正常情况下该动作不会发生；保留 SET NULL
      是为了「万一真删账号，审计行与其归因快照都不丢」（比 CASCADE 删审计、RESTRICT 卡死删号
      都更符合审计语义）；
    - ``detail`` **字段白名单**：禁写 password/token（服务层保证，见 §9.3 日志纪律）。
    """

    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = bigint_pk()
    admin_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    admin_username: Mapped[str] = mapped_column(String(32), nullable=False)  # 快照
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # content.song.publish …
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))  # 字符串化（媒体用 public_id）
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[int | None] = mapped_column(Integer)  # 46xxx / 4xxxx
    summary: Mapped[str] = mapped_column(String(255), nullable=False)  # 人类可读一句话
    detail: Mapped[dict[str, Any] | None] = mapped_column(jsonb())  # before/after 白名单
    request_id: Mapped[str | None] = mapped_column(String(64))  # X-Request-Id 贯通
    ip: Mapped[str | None] = mapped_column(String(45))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("result IN ('ok', 'denied', 'failed')", name="result"),
        # 审计检索四条主路径（时间倒序；PG 反向扫描友好）
        Index("ix_admin_audit_logs_created", text("created_at DESC")),
        Index("ix_admin_audit_logs_admin_created", "admin_user_id", text("created_at DESC")),
        Index("ix_admin_audit_logs_target", "target_type", "target_id", text("created_at DESC")),
        # 只给 target_type、按时间倒序的「某类目标最近发生了什么」（§5.3.7 那条三列索引
        # 拿不到有序输出，故在此补一条两列版）
        Index("ix_admin_audit_logs_type_created", "target_type", text("created_at DESC")),
        Index("ix_admin_audit_logs_action_created", "action", text("created_at DESC")),
    )


class AdminUserStatus:
    """``admin_users.status`` 取值（只表达永久启用/停用；临时锁定看 ``locked_until``）。"""

    ACTIVE = "active"
    DISABLED = "disabled"


class AdminAuditResults:
    """``admin_audit_logs.result`` 取值。"""

    OK = "ok"
    DENIED = "denied"
    FAILED = "failed"


__all__ = [
    "AdminUser",
    "AdminRole",
    "AdminPermission",
    "AdminRolePermission",
    "AdminSession",
    "AdminLoginAttempt",
    "AdminAuditLog",
    "AdminUserStatus",
    "AdminAuditResults",
]
