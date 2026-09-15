"""管理端控制台迁移：15 张新表（RBAC 7 + 审核 2 + 运维遥测 6）+ 3 处既有表联动。

依据 docs/50（管理端后台设计 · §5 数据模型 · 定稿）：

- **写方矩阵**（§5.1）：``admin_*`` / ``moderation_*`` 9 表全 **Java** 写（独立控制台 RBAC/
  审核域）；``ops_*`` / ``llm_*`` 6 表全 **Python** 写（采集器/预警器/trace sink）——
  本文件只是 schema 真源，Python 侧对 Java 表仅声明只读映射，写权由
  ``scripts/check_single_writer.py`` 硬门禁守护；
- **建表顺序 ≠ 文档编号顺序**：``admin_users.role_id`` 外键指向 ``admin_roles``，
  PG 要求被引用表先存在 → ``admin_roles`` 先建（或等价地按 FK 依赖拓扑排序）；
- **既有表联动**（§5.4）：
  1) ``media_assets.status`` CHECK 扩 ``'hidden'``（媒体治理：隐藏≠删除，行保留）；
  2) ``direct_messages.status`` CHECK 同法扩 ``'hidden'``（审核预留，本期只读列表）；
     两条沿用 0005/0006/0010 先例的 **NOT VALID + VALIDATE** 两段姿势（大表零长时间锁）；
  3) ``book_chapters`` 新增 ``status``（加列 + 默认值 + CHECK + 索引）——
     ``server_default='published'`` 保证既有章节行不破（§5.4 尾注），Python 读取路径零改动；
  4) **顺带修正 0011/0012 的 6 条 CHECK 命名漂移**（真库真名多一层前缀，
     详见文件中部 _MEDIA_STATUS_CHECK_LEGACY 处说明）：4 条 RENAME + 2 条 DROP/重建；
- **部分唯一索引**双方言声明（``postgresql_where`` + ``sqlite_where``，docs/47/0011 先例）：
  审核工单幂等建单与举报防刷在 SQLite 单测同样生效（不是「只在 PG 生效」的假约束）；
- **枚举一律 VARCHAR + 显式命名 CHECK**（§5.2）：本迁移不建任何 PG 原生 ENUM；
- **纯 DDL**（docs/10 §7.1-2：迁移内不得夹带业务代码/数据）：权限目录/角色/预警规则的 seed
  一律不进迁移——``admin_permissions``/``admin_roles`` 归 Java 写、``ops_alert_rules`` 归
  Python 侧初始化代码，且 ``check_single_writer`` 不扫 alembic/versions（无护栏兜底）。

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | None = None
depends_on: str | None = None


def _bigint_pk() -> sa.Column:
    return sa.Column(
        "id",
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.Identity(always=False),
        nullable=False,
        primary_key=True,  # 必须显式：PG 对 FK 引用列要求 UNIQUE/PK（0010 实跑复现）
    )


def _jsonb_col(name: str, *, nullable: bool = True, default: str | None = None) -> sa.Column:
    return sa.Column(
        name,
        sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
        nullable=nullable,
        server_default=sa.text(default) if default is not None else None,
    )


def _created_at() -> sa.Column:
    """不可变行（append-only：审计流水/指标样本/span）只记 created_at，无 updated_at。"""
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


def _timestamps() -> list[sa.Column]:
    return [
        _created_at(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


# 既有表 CHECK 取值（§5.4：只加 'hidden'，不外扩语义）
_MEDIA_STATUS_OLD = "'ready', 'deleted'"
_MEDIA_STATUS_NEW = "'ready', 'hidden', 'deleted'"
_DM_STATUS_OLD = "'visible', 'deleted'"
_DM_STATUS_NEW = "'visible', 'hidden', 'deleted'"
_CHAPTER_STATUS = "'draft', 'published', 'archived'"

# ⚠️ 既有 CHECK 的**真库名字**比模型口径多一层前缀——别照抄模型名去 drop/rename：
# 0011/0012 里写成 name="ck_media_assets_status"（自带完整前缀），而 op.create_table 的表挂在
# target_metadata 上（naming_convention 含 ck_%(table_name)s_%(constraint_name)s），于是约定
# 又套了一层 → 真库实际是 ck_media_assets_ck_media_assets_status。
# 2026-09-10 在 postgres:16-alpine 上 `SELECT conname FROM pg_constraint WHERE contype='c'`
# 实测：全库共 **6 条**这种双前缀名（media_assets ×3 / direct_messages ×2 / dm_read_state ×1），
# 其余表（0001/0007/0010 用了 op.f()）名字正确。模型侧声明的是 name="status" →
# ck_media_assets_status；alembic autogenerate **不比较 CHECK**，故 alembic check 一直零 diff、
# 漂移隐形。本迁移按真名 drop/rename、按约定正确名重建：既让 upgrade 在真库跑得通，
# 也把 6 条名字修回模型口径（downgrade 再还原原名，保证可重放）。
_MEDIA_STATUS_CHECK_LEGACY = "ck_media_assets_ck_media_assets_status"
_DM_STATUS_CHECK_LEGACY = "ck_direct_messages_ck_direct_messages_status"


def upgrade() -> None:
    _create_admin_tables()
    _create_moderation_tables()
    _create_telemetry_tables()
    _alter_existing_tables()


# ---------------------------------------------------------------------------
# RBAC 域（Java 写 · docs/50 §5.3.1~§5.3.7）
# ---------------------------------------------------------------------------
def _create_admin_tables() -> None:
    # admin_roles 先建：admin_users.role_id 外键指向它（PG 要求先存在）
    op.create_table(
        "admin_roles",
        _bigint_pk(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("rank", sa.SmallInteger(), nullable=False, server_default=sa.text("100")),
        *_timestamps(),
        sa.UniqueConstraint("code", name=op.f("uq_admin_roles_code")),
    )

    op.create_table(
        "admin_users",
        _bigint_pk(),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(100), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default=sa.text("'active'")
        ),  # 只表达永久启用/停用；临时锁定看 locked_until
        sa.Column(
            "failed_attempts", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_epoch", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_ip", sa.String(45), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["role_id"], ["admin_roles.id"], name=op.f("fk_admin_users_role_id_admin_roles")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["admin_users.id"],
            name=op.f("fk_admin_users_created_by_admin_users"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name=op.f("ck_admin_users_status")),
    )
    # 用户名大小写不敏感唯一（函数索引；PK 之外的第一道身份防线）
    op.create_index(
        "uq_admin_users_username_lower",
        "admin_users",
        [sa.text("lower(username)")],
        unique=True,
    )
    op.create_index("ix_admin_users_role_status", "admin_users", ["role_id", "status"])

    op.create_table(
        "admin_permissions",
        _bigint_pk(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("module", sa.String(24), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("sort", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        _created_at(),  # 权限目录是代码常量快照，启动对账 upsert，不改行
        sa.UniqueConstraint("code", name=op.f("uq_admin_permissions_code")),
    )
    op.create_index("ix_admin_permissions_module", "admin_permissions", ["module", "sort"])

    op.create_table(
        "admin_role_permissions",
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("permission_id", sa.BigInteger(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["admin_roles.id"],
            name=op.f("fk_admin_role_permissions_role_id_admin_roles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["admin_permissions.id"],
            name=op.f("fk_admin_role_permissions_permission_id_admin_permissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name=op.f("pk_admin_role_permissions")),
    )

    op.create_table(
        "admin_sessions",
        _bigint_pk(),
        sa.Column("admin_user_id", sa.BigInteger(), nullable=False),
        sa.Column("refresh_token_hash", sa.CHAR(64), nullable=False),  # sha256 hex
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(32), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["admin_users.id"],
            name=op.f("fk_admin_sessions_admin_user_id_admin_users"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("refresh_token_hash", name="uq_admin_sessions_token_hash"),
    )
    op.create_index(
        "ix_admin_sessions_user_expires",
        "admin_sessions",
        ["admin_user_id", sa.text("expires_at DESC")],
    )

    op.create_table(
        "admin_login_attempts",
        _bigint_pk(),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("admin_user_id", sa.BigInteger(), nullable=True),  # 弱引用，不加 FK
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(32), nullable=True),
        _created_at(),
    )
    op.create_index(
        "ix_admin_login_attempts_username_created",
        "admin_login_attempts",
        ["username", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_admin_login_attempts_ip_created",
        "admin_login_attempts",
        ["ip", sa.text("created_at DESC")],
    )

    # append-only：无 updated_at（§5.3.7 单一审计流原则，审核决定进 detail 不另建表）
    op.create_table(
        "admin_audit_logs",
        _bigint_pk(),
        sa.Column("admin_user_id", sa.BigInteger(), nullable=True),
        sa.Column("admin_username", sa.String(32), nullable=False),  # 快照：账号被删也归因得出
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("error_code", sa.Integer(), nullable=True),
        sa.Column("summary", sa.String(255), nullable=False),
        _jsonb_col("detail"),  # before/after 字段白名单（禁 password/token）
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["admin_users.id"],
            name=op.f("fk_admin_audit_logs_admin_user_id_admin_users"),
            # SET NULL 是 append-only 的唯一例外（账号被物理删时 DB 改写本列）：
            # 管理端账号按 §4.1 只停用不删，正常路径不会触发；真删时审计行与
            # admin_username 快照都要留下（CASCADE 会连审计一起删，违反审计语义）。
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "result IN ('ok', 'denied', 'failed')", name=op.f("ck_admin_audit_logs_result")
        ),
    )
    op.create_index("ix_admin_audit_logs_created", "admin_audit_logs", [sa.text("created_at DESC")])
    op.create_index(
        "ix_admin_audit_logs_admin_created",
        "admin_audit_logs",
        ["admin_user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_admin_audit_logs_target",
        "admin_audit_logs",
        ["target_type", "target_id", sa.text("created_at DESC")],
    )
    # §5.3.7 的 ix_admin_audit_logs_target 只服务「指定目标」的详情流（target_type+target_id）；
    # 「某类目标最近发生了什么」（只给 target_type、按时间倒序）用它拿不到有序输出，补一条。
    op.create_index(
        "ix_admin_audit_logs_type_created",
        "admin_audit_logs",
        ["target_type", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_admin_audit_logs_action_created",
        "admin_audit_logs",
        ["action", sa.text("created_at DESC")],
    )


# ---------------------------------------------------------------------------
# 审核域（Java 写 · docs/50 §5.3.8~§5.3.9 / §6.2）
# ---------------------------------------------------------------------------
def _create_moderation_tables() -> None:
    op.create_table(
        "moderation_cases",
        _bigint_pk(),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default=sa.text("2")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("snippet", sa.String(500), nullable=True),  # 截断快照，不存全文
        _jsonb_col("snapshot"),
        sa.Column("reporter_user_id", sa.BigInteger(), nullable=True),  # 跨域弱引用，不加 FK
        sa.Column("assignee_id", sa.BigInteger(), nullable=True),
        sa.Column("decided_by", sa.BigInteger(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["admin_users.id"],
            name=op.f("fk_moderation_cases_assignee_id_admin_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["admin_users.id"],
            name=op.f("fk_moderation_cases_decided_by_admin_users"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "target_type IN ('post', 'comment', 'media', 'direct_message')",
            name=op.f("ck_moderation_cases_target_type"),
        ),
        sa.CheckConstraint(
            "source IN ('auto', 'report', 'manual')", name=op.f("ck_moderation_cases_source")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'escalated', 'withdrawn')",
            name=op.f("ck_moderation_cases_status"),
        ),
    )
    # 幂等建单：同一目标在「待审/已升级」期间只允许一单（终态不占约束，历史可多条）
    op.create_index(
        "uq_moderation_cases_target_pending",
        "moderation_cases",
        ["target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'escalated')"),
        sqlite_where=sa.text("status IN ('pending', 'escalated')"),
    )
    op.create_index(
        "ix_moderation_cases_queue", "moderation_cases", ["status", "priority", "created_at"]
    )
    op.create_index("ix_moderation_cases_assignee", "moderation_cases", ["assignee_id", "status"])

    op.create_table(
        "moderation_reports",
        _bigint_pk(),
        sa.Column("reporter_user_id", sa.BigInteger(), nullable=False),  # users.id 弱引用
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("detail", sa.String(500), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("case_id", sa.BigInteger(), nullable=True),
        sa.Column("handled_by", sa.BigInteger(), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["moderation_cases.id"],
            name=op.f("fk_moderation_reports_case_id_moderation_cases"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["handled_by"],
            ["admin_users.id"],
            name=op.f("fk_moderation_reports_handled_by_admin_users"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "target_type IN ('post', 'comment', 'media', 'direct_message')",
            name=op.f("ck_moderation_reports_target_type"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'duplicate')",
            name=op.f("ck_moderation_reports_status"),
        ),
    )
    # 防刷：同一举报人对同一目标「待处理」期间只允许一条（终态可再次举报）
    op.create_index(
        "uq_moderation_reports_reporter_target",
        "moderation_reports",
        ["reporter_user_id", "target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_moderation_reports_pending", "moderation_reports", ["status", "created_at"])


# ---------------------------------------------------------------------------
# 运维遥测 + LLM Trace 域（Python 写 · docs/50 §5.3.10~§5.3.15）
# ---------------------------------------------------------------------------
def _create_telemetry_tables() -> None:
    # 仅 append 的 60s 桶样本：唯一键保证重复采集是 upsert 而非重复行（§5.3.10）
    op.create_table(
        "ops_metric_samples",
        _bigint_pk(),
        sa.Column("service", sa.String(16), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column(
            "labels_key", sa.String(160), nullable=False, server_default=sa.text("''")
        ),  # 标签规范化键（jsonb 无法直接比较，故另存）
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_s", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("value_avg", sa.Double(), nullable=False),
        sa.Column("value_max", sa.Double(), nullable=False),
        sa.Column("value_min", sa.Double(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        # 直方图桶（§8.4 指标目录含 p50/p95/p99）：[[上界, 计数], …]，上界由采集器固定给出。
        # 百分位必须由**跨桶求和后的直方图**插值得到——把 p95 写进 value_avg 再跨桶 avg()
        # 得到的是「分位数的均值」，不是任何分位数，§14.2 的「step 重聚合 == 直接聚合」会恒不成立。
        # value_avg/max/min 只服务**可加型**指标（count、token 求和、inflight 类瞬时值）；
        # 时长/队列等待等**分布型**指标只允许走 buckets，两类不得混进同一列。
        _jsonb_col("buckets", nullable=False, default="'[]'"),
        _jsonb_col("labels", nullable=False, default="'{}'"),
        _created_at(),
        sa.CheckConstraint(
            "service IN ('python', 'java')", name=op.f("ck_ops_metric_samples_service")
        ),
        sa.UniqueConstraint(
            "service",
            "metric",
            "labels_key",
            "bucket_start",
            "bucket_s",
            name="uq_ops_metric_samples_bucket",
        ),
    )
    # 控制台取数形状（§10.3 GET /ops/metrics?metric=&from=&to=&step=&labels=）：
    # 先按 (service, metric, labels_key) 定位**单条序列**，再按 bucket_start DESC 扫时间窗 →
    # 前缀必须带 labels_key（labels_key 才是区分序列的键），故不用 (metric, bucket_start)。
    op.create_index(
        "ix_ops_metric_samples_metric_bucket",
        "ops_metric_samples",
        ["service", "metric", "labels_key", sa.text("bucket_start DESC")],
    )

    op.create_table(
        "ops_alert_rules",
        _bigint_pk(),
        sa.Column("code", sa.String(48), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("service", sa.String(16), nullable=False, server_default=sa.text("'python'")),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("comparator", sa.String(8), nullable=False),
        sa.Column("threshold", sa.Double(), nullable=False),
        sa.Column("window_s", sa.Integer(), nullable=False, server_default=sa.text("300")),
        sa.Column("min_samples", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("cooldown_s", sa.Integer(), nullable=False, server_default=sa.text("900")),
        _jsonb_col("notify_channels", nullable=False, default="'[]'"),
        sa.Column("description", sa.String(255), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("code", name=op.f("uq_ops_alert_rules_code")),
        sa.CheckConstraint(
            "comparator IN ('gt', 'gte', 'lt', 'lte')", name=op.f("ck_ops_alert_rules_comparator")
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warn', 'critical')", name=op.f("ck_ops_alert_rules_severity")
        ),
    )

    op.create_table(
        "ops_alert_events",
        _bigint_pk(),
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("rule_code", sa.String(48), nullable=False),  # 冗余快照：规则删后事件仍可读
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'firing'")),
        sa.Column("value", sa.Double(), nullable=False),
        sa.Column("threshold", sa.Double(), nullable=False),
        sa.Column("window_s", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(255), nullable=False),
        _jsonb_col("detail"),
        sa.Column("dedup_key", sa.String(160), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_by", sa.String(32), nullable=True),  # 用户名快照，跨服务不加 FK
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_note", sa.String(255), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["ops_alert_rules.id"],
            name=op.f("fk_ops_alert_events_rule_id_ops_alert_rules"),
            # RESTRICT 而非 docs/50 §5.3.12 写的 CASCADE：`DELETE /ops/alerts/rules/{id}`
            # （§10.3）若级联，会把已 acknowledged/resolved 的预警历史一并抹掉，与
            # rule_code「冗余快照：规则删除后事件仍可读」的设计意图自相矛盾。
            # ⇒ 规则只停用（enabled=false），确需删除时先确认无事件。
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('firing', 'acknowledged', 'resolved')",
            name=op.f("ck_ops_alert_events_status"),
        ),
        sa.UniqueConstraint("dedup_key", name="uq_ops_alert_events_dedup_key"),
    )
    op.create_index(
        "ix_ops_alert_events_status_fired",
        "ops_alert_events",
        ["status", sa.text("fired_at DESC")],
    )

    op.create_table(
        "llm_traces",
        _bigint_pk(),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),  # 与 X-Request-Id 同源
        sa.Column("service", sa.String(16), nullable=False, server_default=sa.text("'python'")),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("ttft_ms", sa.Integer(), nullable=True),
        sa.Column("span_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("llm_call_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cache_hit_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column(
            "content_captured", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),  # 该 trace 是否落了内容（隐私声明用）
        _jsonb_col("attrs", nullable=False, default="'{}'"),
        _created_at(),
        sa.UniqueConstraint("trace_id", name=op.f("uq_llm_traces_trace_id")),
        sa.CheckConstraint(
            "status IN ('ok', 'error', 'aborted', 'incomplete')", name=op.f("ck_llm_traces_status")
        ),
    )
    op.create_index("ix_llm_traces_started", "llm_traces", [sa.text("started_at DESC")])
    op.create_index(
        "ix_llm_traces_kind_started", "llm_traces", ["kind", sa.text("started_at DESC")]
    )
    op.create_index(
        "ix_llm_traces_status_started", "llm_traces", ["status", sa.text("started_at DESC")]
    )
    op.create_index(
        "ix_llm_traces_session", "llm_traces", ["session_id", sa.text("started_at DESC")]
    )
    # 过期清理（§10.3 POST /ops/maintenance/purge；本仓无调度器，按需触发）：
    # 批量 DELETE 走 created_at 范围扫描，其它索引前缀都是 kind/status/session，服务不了它。
    op.create_index("ix_llm_traces_created", "llm_traces", ["created_at"])

    op.create_table(
        "llm_spans",
        _bigint_pk(),
        sa.Column("trace_id", sa.String(64), nullable=False),  # 逻辑外键，批量写不加 FK
        sa.Column("span_id", sa.String(32), nullable=False),
        sa.Column("parent_span_id", sa.String(32), nullable=True),
        sa.Column("name", sa.String(48), nullable=False),
        sa.Column("span_kind", sa.String(16), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("ttft_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("retry_index", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("finish_reason", sa.String(32), nullable=True),
        sa.Column("tool_name", sa.String(64), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        _jsonb_col("attrs", nullable=False, default="'{}'"),
        _created_at(),
        sa.UniqueConstraint("span_id", name=op.f("uq_llm_spans_span_id")),
        sa.CheckConstraint(
            "span_kind IN ('internal', 'client', 'server')", name=op.f("ck_llm_spans_span_kind")
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'error', 'aborted', 'incomplete')", name=op.f("ck_llm_spans_status")
        ),
    )
    op.create_index("ix_llm_spans_trace_seq", "llm_spans", ["trace_id", "seq"])
    # 保留这两条（docs/50 §5.3.14 原始设计）：`name` 服务 §12.2 图表的按 span 类型聚合
    # （TOOL/LLM 延迟与失败率排行），`status` 服务错误率趋势；两者都带 started_at DESC
    # 以直接吃时间窗，**不删**——删除会让 §12 图表退化为全表扫。
    op.create_index("ix_llm_spans_name_started", "llm_spans", ["name", sa.text("started_at DESC")])
    op.create_index(
        "ix_llm_spans_status_started", "llm_spans", ["status", sa.text("started_at DESC")]
    )
    # span 与 trace 同期保留（30 天），批量清理同样只认 created_at
    op.create_index("ix_llm_spans_created", "llm_spans", ["created_at"])

    # 内容捕获独立表：内容体积大、保留期短、默认不采集（§7.5），故与结构表分开 TTL
    op.create_table(
        "llm_span_contents",
        _bigint_pk(),
        sa.Column("trace_id", sa.String(64), nullable=False),  # 逻辑外键，不加 FK
        sa.Column("span_id", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("role", sa.String(16), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_chars", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("redacted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _created_at(),
        sa.CheckConstraint(
            "direction IN ('input', 'output')", name=op.f("ck_llm_span_contents_direction")
        ),
        sa.UniqueConstraint(
            "span_id", "direction", "seq", name="uq_llm_span_contents_span_dir_seq"
        ),
    )
    # span 详情/内容流（§10.3 GET /ops/traces/{trace_id}[/contents]）是最热读路径：
    # 原来只有 (span_id, direction, seq) 唯一键，按 trace_id 取内容只能全表扫。
    op.create_index("ix_llm_span_contents_trace", "llm_span_contents", ["trace_id", "span_id"])
    # TTL 72h 清理（§7.5：内容保留期短于结构表，维护任务按 created_at 批量扫描删除）
    op.create_index("ix_llm_span_contents_created", "llm_span_contents", ["created_at"])


# ---------------------------------------------------------------------------
# 既有表联动（docs/50 §5.4）
# ---------------------------------------------------------------------------
def _drop_check_if_exists(name: str, table: str) -> None:
    """按**真库实际名字**删 CHECK；IF EXISTS 让「裸名/双前缀名」两种历史状态都能过。

    用原生 SQL 而非 op.drop_constraint 的原因：后者会把名字交给命名约定再套一层
    （见 LEGACY 常量处说明），而这里的名字就是要在库里精确匹配的字符串。
    """
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")


def _rename_check(table: str, old: str, new: str) -> None:
    """把约定被套两层的既有 CHECK 改回模型口径的正确名（PG 原生 ALTER … RENAME）。"""
    op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}")


def _alter_existing_tables() -> None:
    # ---- 先修命名漂移：0011/0012 的 6 条 CHECK 真名都多一层前缀 ----
    # 两条 status 待会儿要 drop+重建，故此处只处理**另外四条**（重命名，语义零变化）。
    _rename_check(
        "media_assets",
        "ck_media_assets_ck_media_assets_kind",
        op.f("ck_media_assets_kind"),
    )
    _rename_check(
        "media_assets",
        "ck_media_assets_ck_media_assets_size_positive",
        op.f("ck_media_assets_size_positive"),
    )
    _rename_check(
        "direct_messages",
        "ck_direct_messages_ck_direct_messages_no_self_message",
        op.f("ck_direct_messages_no_self_message"),
    )
    _rename_check(
        "dm_read_state",
        "ck_dm_read_state_ck_dm_read_state_no_self_peer",
        op.f("ck_dm_read_state_no_self_peer"),
    )

    # (a) media_assets.status：ready|deleted → ready|hidden|deleted（媒体治理隐藏≠删除）
    # NOT VALID + VALIDATE 两段（0005/0006/0010 先例）：先挂约束不扫描存量，再单独校验，
    # 避免大表被排他锁住整个校验时长。
    # 两个名字都 IF EXISTS：真库是双前缀名（0011 造成），从 metadata create_all 出来的库是裸名。
    _drop_check_if_exists(_MEDIA_STATUS_CHECK_LEGACY, "media_assets")
    _drop_check_if_exists(op.f("ck_media_assets_status"), "media_assets")
    op.execute(
        f"ALTER TABLE media_assets ADD CONSTRAINT {op.f('ck_media_assets_status')} "
        f"CHECK (status IN ({_MEDIA_STATUS_NEW})) NOT VALID"
    )
    op.execute(f"ALTER TABLE media_assets VALIDATE CONSTRAINT {op.f('ck_media_assets_status')}")

    # (b) direct_messages.status：visible|deleted → visible|hidden|deleted（审核预留，本期只读）
    _drop_check_if_exists(_DM_STATUS_CHECK_LEGACY, "direct_messages")
    _drop_check_if_exists(op.f("ck_direct_messages_status"), "direct_messages")
    op.execute(
        f"ALTER TABLE direct_messages ADD CONSTRAINT {op.f('ck_direct_messages_status')} "
        f"CHECK (status IN ({_DM_STATUS_NEW})) NOT VALID"
    )
    op.execute(
        f"ALTER TABLE direct_messages VALIDATE CONSTRAINT {op.f('ck_direct_messages_status')}"
    )

    # (c) book_chapters 新增 status（§5.4：本设计唯一加列）：server_default 保证既有行不破，
    # Python 既有读取路径无需改；CHECK + 索引支撑「上架校验」与运营列表过滤（§6.1）。
    op.add_column(
        "book_chapters",
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'published'")),
    )
    op.create_check_constraint(
        op.f("ck_book_chapters_status"), "book_chapters", f"status IN ({_CHAPTER_STATUS})"
    )
    op.create_index(op.f("ix_book_chapters_status"), "book_chapters", ["status"])


def downgrade() -> None:
    # 既有表还原：先撤新列，再把两条 CHECK 收窄回原取值，并还原被修的约束名。
    # 注意（数据前提）：若存量行已落 status='hidden'，收窄会失败——需先人工确认无隐藏行，
    # 这是「回退不静默丢数据」的刻意取舍（与 0010 反向收紧 events CHECK 同口径）。
    op.drop_index(op.f("ix_book_chapters_status"), table_name="book_chapters")
    op.drop_constraint(op.f("ck_book_chapters_status"), "book_chapters", type_="check")
    op.drop_column("book_chapters", "status")

    # 还原为 upgrade 之后的**原始状态**（双前缀名），保证 downgrade→upgrade 可重放：
    # 否则再次 upgrade 时 IF EXISTS 找不到旧名、语义虽对但状态不可复现。
    op.drop_constraint(op.f("ck_direct_messages_status"), "direct_messages", type_="check")
    op.execute(
        f"ALTER TABLE direct_messages ADD CONSTRAINT {_DM_STATUS_CHECK_LEGACY} "
        f"CHECK (status IN ({_DM_STATUS_OLD}))"
    )
    op.drop_constraint(op.f("ck_media_assets_status"), "media_assets", type_="check")
    op.execute(
        f"ALTER TABLE media_assets ADD CONSTRAINT {_MEDIA_STATUS_CHECK_LEGACY} "
        f"CHECK (status IN ({_MEDIA_STATUS_OLD}))"
    )
    # 四条被改名的 CHECK 改回 0011/0012 的双前缀名（与上面同口径：回退=回到 0012 原状）
    _rename_check(
        "dm_read_state",
        op.f("ck_dm_read_state_no_self_peer"),
        "ck_dm_read_state_ck_dm_read_state_no_self_peer",
    )
    _rename_check(
        "direct_messages",
        op.f("ck_direct_messages_no_self_message"),
        "ck_direct_messages_ck_direct_messages_no_self_message",
    )
    _rename_check(
        "media_assets",
        op.f("ck_media_assets_size_positive"),
        "ck_media_assets_ck_media_assets_size_positive",
    )
    _rename_check(
        "media_assets",
        op.f("ck_media_assets_kind"),
        "ck_media_assets_ck_media_assets_kind",
    )

    # 15 张新表逆依赖序删除（子表先删；FK 为 RESTRICT/SET NULL/CASCADE，逆序即可安全）
    op.drop_table("llm_span_contents")
    op.drop_table("llm_spans")
    op.drop_table("llm_traces")
    op.drop_table("ops_alert_events")
    op.drop_table("ops_alert_rules")
    op.drop_table("ops_metric_samples")
    op.drop_table("moderation_reports")
    op.drop_table("moderation_cases")
    op.drop_table("admin_audit_logs")
    op.drop_table("admin_login_attempts")
    op.drop_table("admin_sessions")
    op.drop_table("admin_role_permissions")
    op.drop_table("admin_permissions")
    op.drop_table("admin_users")
    op.drop_table("admin_roles")
