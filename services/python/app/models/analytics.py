"""数据分析域：events（埋点）/ reports（看板聚合）——均 **Python 写**。

- ``events``：前端上报事件原文落库（docs/06 §9.1 9 类事件 + 维度快照 + 会话去重键）；
- ``reports``：指标聚合结果（docs/06 §9.1 四指标），Python 定时/按需计算，
  Java「评价看板」只读本表，避免 Java 重复实现口径（口径 = Python 唯一实现）。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, Channels, CreatedAtMixin, TimestampMixin, bigint_pk, jsonb


class Event(CreatedAtMixin, Base):
    """行为埋点（Python 写；仅追加不修改）。

    - client_event_id：前端幂等键（UUID，重传去重）——唯一索引；
    - occurred_at（客户端时间，UTC）与 created_at（服务端接收时间）分离，
      server_offset_ms=created_at-occurred_at 记录时钟偏差（|偏差|>1h 的指标窗口按
      created_at 判定，docs/11 Q-B22）；
    - 浏览会话键（docs/11 Q-B01/05，四指标可计算性关键）：
      * browse_session_id：前端每次 App 会话生成，贯穿 page_view/impression/click，
        作 CTR/跳出率的「会话」去重键（与训练 session_id 正交）；
      * recommend_group_id：每次推荐流渲染生成，impression 与 click 共享，
        用于「曝光后 30min」窗口关联；
      * page/target_type/target_id：结构化页面入口（page_view 定位 场景/歌曲页）；
    - 维度快照：age_group/level/scene_id/song_id/channel（docs/01 六维），
      快照而非实时 join（口径可复算，画像变更不污染历史）；
    - FK 改 RESTRICT（不写 ondelete）：内容归档不删，历史事件不该被静默改写
      （docs/11 Q-B20「只追加」语义）。
    """

    __tablename__ = "events"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )  # 允许 NULL：未登录 page_view
    session_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sessions.id"))
    browse_session_id: Mapped[str | None] = mapped_column(String(36))
    recommend_group_id: Mapped[str | None] = mapped_column(String(36))
    client_event_id: Mapped[str | None] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    server_offset_ms: Mapped[int | None] = mapped_column(BigInteger)
    page: Mapped[str | None] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(16))
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    age_group: Mapped[str | None] = mapped_column(String(16))
    level: Mapped[str | None] = mapped_column(String(8))
    scene_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("scenarios.id"))
    song_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("songs.id"))
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{Channels.WEB}'")
    )
    payload: Mapped[dict] = mapped_column(jsonb(), nullable=False, server_default=text("'{}'"))

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('page_view', 'scene_start', 'recording_start', "
            "'recording_complete', 'score_event', 'recommend_impression', "
            "'recommend_click', 'practice_complete', 'fun_action')",
            name="event_type",
        ),
        CheckConstraint(
            "age_group IN ('child', 'teen', 'adult', 'senior') OR age_group IS NULL",
            name="age_group",
        ),
        CheckConstraint("level IN ('L1', 'L2', 'L3', 'L4') OR level IS NULL", name="level"),
        CheckConstraint(
            f"channel IN ('{Channels.WEB}', '{Channels.PWA}', '{Channels.IOS}', "
            f"'{Channels.ANDROID}', '{Channels.OTHER}')",
            name="channel",
        ),
        CheckConstraint(
            "target_type IN ('scene', 'song', 'home') OR target_type IS NULL",
            name="target_type",
        ),
        # 幂等去重：client_event_id 可空；NULL 在唯一索引中互不冲突，无需部分索引
        Index("uq_events_client_event_id", "client_event_id", unique=True),
        # 指标口径查询（docs/06 §9.1 六维聚合；docs/11 Q-B01/B15）
        Index("ix_events_type_occurred", "event_type", "occurred_at"),
        Index("ix_events_user_occurred", "user_id", "occurred_at"),
        Index("ix_events_session_id", "session_id"),
        Index("ix_events_browse_session", "browse_session_id", "occurred_at"),
        Index("ix_events_scene_type_occurred", "event_type", "scene_id", "occurred_at"),
        Index("ix_events_song_type_occurred", "event_type", "song_id", "occurred_at"),
        Index("ix_events_age_type_occurred", "event_type", "age_group", "occurred_at"),
        Index("ix_events_level_type_occurred", "event_type", "level", "occurred_at"),
    )


class Report(TimestampMixin, Base):
    """指标聚合结果（Python 写；Java 看板只读）。

    - scope/scope_id：global(0)/user/scene/song 四级（多态引用，无 FK——见 docs/10 开放项 D-1）；
    - period_start/period_end：UTC 日期闭区间 [start, end]；
    - metrics：{ctr:{numerator,denominator,rate}, completion_rate:{...},
      interaction_rate:{...}, bounce_rate:{...}} 分子分母与比率同存，口径可审计；
    - 同 (type, scope, scope_id, period) 唯一：重复计算=整行覆盖写（upsert），不产生重复行。
    """

    __tablename__ = "reports"

    id: Mapped[int] = bigint_pk()
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    metrics: Mapped[dict] = mapped_column(jsonb(), nullable=False, server_default=text("'{}'"))
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "report_type",
            "scope",
            "scope_id",
            "period_start",
            "period_end",
            name="uq_reports_scope_period",
        ),
        CheckConstraint("scope IN ('global', 'user', 'scene', 'song')", name="scope"),
        CheckConstraint("period_end >= period_start", name="period_order"),
        Index("ix_reports_scope_period", "scope", "scope_id", "period_start"),
    )
