"""管理端控制台 · 运维遥测与 LLM Trace 域（docs/50 §5.3.10~§5.3.15 · 迁移 0013）。

**写方矩阵**：6 张表全 **Python** 写（采集器/预警器/trace sink，docs/50 §5.1）；
Java 控制台只读聚合展示，**不得写入**（写路径经 §10.3 的 Python 端点）。

设计要点（docs/50 §5.3 / §7 / §8）：

- **指标仅 append**（§5.3.10）：60s 一桶，``(service, metric, labels_key, bucket_start,
  bucket_s)`` 唯一 → 重复采集是 upsert 覆盖而非重复行；只增不改，无行锁竞争；
- **预警与账号解耦**（§5.3.12 · 拷问 A-7）：``acked_by`` 存**管理员用户名快照**而非
  ``admin_users.id`` FK——``ops_alert_events`` 归 Python 写、``admin_users`` 归 Java 写，
  跨服务 FK 会绑死两个服务的生命周期；
- **``dedup_key`` 防抖**：``rule_code + floor(fired_at/window_s)``，同窗口同规则只出一条；
  恢复**不自动 resolve**（人工 resolve 留痕，避免闪断刷屏，§6.3）；
- **trace 对齐 DSH GenAI span 树**（§7.1）：一次 turn = 一个 trace；每次 LLM 尝试独立 span
  （``retry_index`` 让重试可见）；``llm_spans.trace_id`` 是**逻辑外键**（批量写入不加 FK）；
- **内容捕获独立表 + 默认空**（§7.5）：``llm_span_contents`` 与结构与 TTL 都独立——
  默认不落内容，开启后独立保留期清理（``ix_llm_span_contents_created`` 供 TTL 扫描），
  并记 ``truncated`` / ``redacted`` 让「这份内容被处理过」可自证。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, TimestampMixin, bigint_pk, jsonb


class OpsMetricSample(CreatedAtMixin, Base):
    """指标 60s 桶样本（Python 写；保留 7 天，仅 append，docs/50 §5.3.10 / §8.4）。"""

    __tablename__ = "ops_metric_samples"

    id: Mapped[int] = bigint_pk()
    service: Mapped[str] = mapped_column(String(16), nullable=False)  # python | java
    metric: Mapped[str] = mapped_column(String(64), nullable=False)  # 指标目录见 §8.4
    #: 标签规范化键（标签字典序列化后排序拼接）——参与唯一键，避免 jsonb 无法直接比较
    labels_key: Mapped[str] = mapped_column(String(160), nullable=False, server_default=text("''"))
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket_s: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("60"))
    value_avg: Mapped[float] = mapped_column(Double, nullable=False)
    value_max: Mapped[float] = mapped_column(Double, nullable=False)
    value_min: Mapped[float] = mapped_column(Double, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    #: 直方图桶 ``[[上界, 计数], …]``（上界由采集器固定给出；指标目录 §8.4 含 p50/p95/p99）。
    #: 百分位必须由**跨桶求和后的直方图**插值得到——把分位数写进 value_avg 再跨桶 avg()，
    #: 得到的是「分位数的均值」，不是任何分位数（§14.2「step 重聚合 == 直接聚合」恒不成立）。
    #: value_avg/max/min 只服务**可加型**指标（count、token 求和、inflight 类瞬时值）；
    #: 时长/队列等待等**分布型**指标只走 buckets，两类不得混进同一列。
    buckets: Mapped[list] = mapped_column(jsonb(), nullable=False, server_default=text("'[]'"))
    labels: Mapped[dict[str, Any]] = mapped_column(
        jsonb(), nullable=False, server_default=text("'{}'")
    )

    __table_args__ = (
        CheckConstraint("service IN ('python', 'java')", name="service"),
        # 幂等写入：同桶同指标同标签重复采集 = upsert 覆盖（不产生重复行）
        UniqueConstraint(
            "service",
            "metric",
            "labels_key",
            "bucket_start",
            "bucket_s",
            name="uq_ops_metric_samples_bucket",
        ),
        # 控制台取数形状（§10.3 GET /ops/metrics）：先按 (service, metric, labels_key) 定位
        # 单条序列，再按 bucket_start 扫时间窗 → 前缀必须含 labels_key（它才是区分序列的键）。
        Index(
            "ix_ops_metric_samples_metric_bucket",
            "service",
            "metric",
            "labels_key",
            text("bucket_start DESC"),
        ),
    )


class OpsAlertRule(TimestampMixin, Base):
    """预警规则（Python 写；内置 6 条 seed，阈值可改，docs/50 §5.3.11 / §6.3）。"""

    __tablename__ = "ops_alert_rules"

    id: Mapped[int] = bigint_pk()
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    service: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'python'")
    )
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    comparator: Mapped[str] = mapped_column(String(8), nullable=False)  # gt | gte | lt | lte
    threshold: Mapped[float] = mapped_column(Double, nullable=False)
    window_s: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("300"))
    #: 窗口内最少样本数（样本不足不判定，避免冷启动误报）
    min_samples: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # info | warn | critical
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    #: 同规则冷却窗口：窗口内不重复出事件（§6.3 预警不是闹钟）
    cooldown_s: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("900"))
    #: 预留：["inbox","webhook"]（本期只做控制台角标）。
    #: **形状 = 字符串数组**（与 server_default ``'[]'`` 一致）：注解原为 ``dict[str, Any]``，
    #: 与默认值/预留值/控制台类型三处矛盾 —— 已改齐；写侧由
    #: ``app/console/api/routes/ops.py::_validate_notify_channels`` 白名单校验。
    notify_channels: Mapped[list[str]] = mapped_column(
        jsonb(), nullable=False, server_default=text("'[]'")
    )
    description: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        UniqueConstraint("code", name="uq_ops_alert_rules_code"),
        # 两个枚举都落 CHECK（§5.3.11 的 ``ck ∈``）：SQLite 单测也拦得住脏值，
        # 名字用短名，由命名约定展开成 ck_ops_alert_rules_comparator / _severity（与迁移一致）
        CheckConstraint("comparator IN ('gt', 'gte', 'lt', 'lte')", name="comparator"),
        CheckConstraint("severity IN ('info', 'warn', 'critical')", name="severity"),
    )


class OpsAlertEvent(CreatedAtMixin, Base):
    """预警事件（Python 写；firing → acknowledged → resolved，docs/50 §5.3.12 / §6.3）。"""

    __tablename__ = "ops_alert_events"

    id: Mapped[int] = bigint_pk()
    rule_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ops_alert_rules.id", ondelete="RESTRICT"), nullable=False
    )
    #: 冗余快照：规则删除后事件仍可读——正因为如此，FK 用 **RESTRICT** 而非 §5.3.12 写的
    #: CASCADE（级联会连 acknowledged/resolved 的历史一起抹掉，快照也就白存了）；
    #: 规则只停用（enabled=false），确需物理删除时先确认无事件。
    rule_code: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # 规则快照，无 CHECK
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'firing'"))
    value: Mapped[float] = mapped_column(Double, nullable=False)
    threshold: Mapped[float] = mapped_column(Double, nullable=False)
    window_s: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(jsonb())
    #: rule_code + floor(fired_at/window_s)：同窗口同规则只出一条
    dedup_key: Mapped[str] = mapped_column(String(160), nullable=False)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: 管理员用户名**快照**（跨服务不加 FK：admin_users 归 Java 写，§5.3.12 拷问 A-7）
    acked_by: Mapped[str | None] = mapped_column(String(32))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_note: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        CheckConstraint("status IN ('firing', 'acknowledged', 'resolved')", name="status"),
        UniqueConstraint("dedup_key", name="uq_ops_alert_events_dedup_key"),
        Index("ix_ops_alert_events_status_fired", "status", text("fired_at DESC")),
    )


class LlmTrace(CreatedAtMixin, Base):
    """一次调用链（Python 写；1 turn = 1 trace，docs/50 §5.3.13 / §7.2）。

    与 ``usage_log`` **双轨不合并**（§7.4）：本表是观测/调优口径（延迟、TTFT、重试），
    ``usage_log`` 是配额/账单口径——口径不同，合并会让两边都失真。
    """

    __tablename__ = "llm_traces"

    id: Mapped[int] = bigint_pk()
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: 与 HTTP X-Request-Id 同源（在请求上下文内时继承，后台任务为空）
    request_id: Mapped[str | None] = mapped_column(String(64))
    service: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'python'")
    )
    #: turn|free_chat|defense|summary|conclude|reading_tts|score|meta（值集由采集侧约束）
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(64))  # 逻辑引用，不加 FK
    user_id: Mapped[int | None] = mapped_column(BigInteger)  # 逻辑引用，不加 FK
    #: 主模型（多模型时取首次 LLM span 的 model）
    model: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    ttft_ms: Mapped[int | None] = mapped_column(Integer)  # 首 token 延迟（木桶最慢一次）
    span_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    llm_call_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cache_hit_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    #: 该 trace 是否落了内容（隐私声明用：默认 false，§7.5）
    content_captured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    #: 采样率/版本/prompt 模板 id/git sha
    attrs: Mapped[dict[str, Any]] = mapped_column(
        jsonb(), nullable=False, server_default=text("'{}'")
    )

    __table_args__ = (
        CheckConstraint("status IN ('ok', 'error', 'aborted', 'incomplete')", name="status"),
        UniqueConstraint("trace_id", name="uq_llm_traces_trace_id"),
        Index("ix_llm_traces_started", text("started_at DESC")),
        Index("ix_llm_traces_kind_started", "kind", text("started_at DESC")),
        Index("ix_llm_traces_status_started", "status", text("started_at DESC")),
        Index("ix_llm_traces_session", "session_id", text("started_at DESC")),
        # 过期清理（§10.3 POST /ops/maintenance/purge，保留 30 天；本仓无调度器、按需触发）：
        # 批量 DELETE 走 created_at 范围扫，上面几条索引前缀是 kind/status/session，服务不了它
        Index("ix_llm_traces_created", "created_at"),
    )


class LlmSpan(CreatedAtMixin, Base):
    """span 树结构元数据（Python 写；ENTRY→AGENT→STEP→LLM/TOOL，docs/50 §5.3.14 / §7.2）。

    ``trace_id`` 是**逻辑外键**（批量写入，不加 FK 约束）；``retry_index`` 让同一 STEP 下的
    重试可见（DSH 五条设计原则之二）。
    """

    __tablename__ = "llm_spans"

    id: Mapped[int] = bigint_pk()
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)  # 逻辑外键，不加 FK
    span_id: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(String(32))
    #: ENTRY|AGENT|STEP|LLM|TOOL|ASR|TTS|SCORE|RETRIEVE（值集由采集侧约束）
    name: Mapped[str] = mapped_column(String(48), nullable=False)
    span_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # internal|client|server
    seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    ttft_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    #: 同一 STEP 下第几次 LLM 尝试（重试可见）
    retry_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    model: Mapped[str | None] = mapped_column(String(64))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    #: stop|length|tool_calls|content_filter|error（值集由采集侧约束）
    finish_reason: Mapped[str | None] = mapped_column(String(32))
    tool_name: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    attrs: Mapped[dict[str, Any]] = mapped_column(
        jsonb(), nullable=False, server_default=text("'{}'")
    )

    __table_args__ = (
        CheckConstraint("span_kind IN ('internal', 'client', 'server')", name="span_kind"),
        CheckConstraint("status IN ('ok', 'error', 'aborted', 'incomplete')", name="status"),
        UniqueConstraint("span_id", name="uq_llm_spans_span_id"),
        # 瀑布图渲染主路径：同 trace 内按 seq 顺序取
        Index("ix_llm_spans_trace_seq", "trace_id", "seq"),
        # 这两条保留（§5.3.14 原始设计）：name 服务 §12.2 图表的按 span 类型聚合
        # （TOOL/LLM 延迟与失败率排行），status 服务错误率趋势；都带 started_at DESC
        # 直接吃时间窗——删掉会让 §12 图表退化成全表扫
        Index("ix_llm_spans_name_started", "name", text("started_at DESC")),
        Index("ix_llm_spans_status_started", "status", text("started_at DESC")),
        # span 与 trace 同期保留（30 天），批量清理同样只认 created_at
        Index("ix_llm_spans_created", "created_at"),
    )


class LlmSpanContent(CreatedAtMixin, Base):
    """span 内容捕获（Python 写；**独立表 + 独立 TTL + 默认空**，docs/50 §5.3.15 / §7.5）。

    独立成表而非在 ``llm_spans`` 加列：内容体积大、保留期短、默认不采集——
    混进结构表会让「关掉内容捕获」变成删列级改造，也让 TTL 清理误伤调用链元数据。
    """

    __tablename__ = "llm_span_contents"

    id: Mapped[int] = bigint_pk()
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)  # 逻辑外键，不加 FK
    span_id: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # input | output
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    role: Mapped[str | None] = mapped_column(String(16))  # system|user|assistant|tool
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 正文一律 TEXT（VARCHAR 长度坑）
    content_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    #: 超过 content_max_chars 被截断
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    #: 命中脱敏规则（手机号/邮箱/密钥样式）
    redacted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        CheckConstraint("direction IN ('input', 'output')", name="direction"),
        UniqueConstraint("span_id", "direction", "seq", name="uq_llm_span_contents_span_dir_seq"),
        # trace 详情/内容流（§10.3 GET /ops/traces/{trace_id}[/contents]）是最热读路径：
        # 只有 (span_id,direction,seq) 唯一键的话，按 trace_id 取内容只能全表扫
        Index("ix_llm_span_contents_trace", "trace_id", "span_id"),
        # TTL 72h 清理用（内容保留期短于结构表，维护任务按 created_at 批量扫描删除）
        Index("ix_llm_span_contents_created", "created_at"),
    )


class OpsServices:
    """``ops_metric_samples.service`` 取值（Python 采集端自报 + Java 侧上报）。"""

    PYTHON = "python"
    JAVA = "java"


class OpsAlertSeverities:
    """``ops_alert_rules.severity`` / ``ops_alert_events.severity`` 取值。"""

    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


class OpsAlertEventStatus:
    """``ops_alert_events.status`` 取值（恢复**不自动**转 resolved，人工留痕，§6.3）。"""

    FIRING = "firing"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class TraceStatus:
    """``llm_traces.status`` / ``llm_spans.status`` 取值。"""

    OK = "ok"
    ERROR = "error"
    ABORTED = "aborted"
    INCOMPLETE = "incomplete"


class SpanKinds:
    """``llm_spans.span_kind`` 取值（OpenTelemetry 口径）。"""

    INTERNAL = "internal"
    CLIENT = "client"
    SERVER = "server"


class SpanNames:
    """``llm_spans.name`` 取值（DSH span 树迁移，docs/50 §7.2）。"""

    ENTRY = "ENTRY"
    AGENT = "AGENT"
    STEP = "STEP"
    LLM = "LLM"
    TOOL = "TOOL"
    ASR = "ASR"
    TTS = "TTS"
    SCORE = "SCORE"
    RETRIEVE = "RETRIEVE"


class SpanContentDirections:
    """``llm_span_contents.direction`` 取值。"""

    INPUT = "input"
    OUTPUT = "output"


__all__ = [
    "OpsMetricSample",
    "OpsAlertRule",
    "OpsAlertEvent",
    "LlmTrace",
    "LlmSpan",
    "LlmSpanContent",
    "OpsServices",
    "OpsAlertSeverities",
    "OpsAlertEventStatus",
    "TraceStatus",
    "SpanKinds",
    "SpanNames",
    "SpanContentDirections",
]
