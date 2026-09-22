"""酒馆（TRPG 跑团）域：剧本 / 事实 / 任务 / 线索 / 实体 / 事件日志 / 消息（均 **Python 写**）。

迁移来源：ai4u 跑团三件套（docs/52 §3），按 VocalVerse 多用户口径补 ``user_id`` 归属与
级联删除；表名统一 ``trpg_`` 前缀避免与社区/练习域混淆。

结构（对齐 ai4u P2-22/24/28/29/42）：
- ``trpg_campaigns``：一次冒险（跨会话续跑的同步单元），narrative_summary 由状态渲染；
- ``trpg_facts``：事实表（唯一写入口见 app/trpg/state.py；``user_deleted_at`` 墓碑防复活）；
- ``trpg_tasks`` / ``trpg_clues``：任务/线索结构化行（快照注入与主持台消费）；
- ``trpg_entities``：实体注册表（LLM 发现未知实体 → pending 懒确认，P2-42）；
- ``trpg_events``：append-only 事件日志（骰子/状态变化，判定卡数据源）；
- ``trpg_messages``：对话流水（user/assistant + kind=system 系统卡，刷新不丢）。

写归属：全部 Python 写（docs/10 §3 矩阵新增行，Java 只读映射）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    TrpgCardSources,
    TrpgCardStatuses,
    TrpgEntityKinds,
    TrpgFactKinds,
    TrpgFactModalities,
    TrpgLangs,
    TrpgMessageKinds,
    TrpgMessageRoles,
    TrpgTaskStatuses,
    bigint_pk,
    jsonb,
)


class TrpgCampaign(TimestampMixin, Base):
    """冒险剧本实例（用户私有；name 建卡时 trim + 截断 60）。"""

    __tablename__ = "trpg_campaigns"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    # 叙事摘要（P2-45：由结构化状态渲染，非对话压缩）——事实表写入后由后台/收尾增量刷新
    narrative_summary: Mapped[str | None] = mapped_column(Text)
    # 最近活跃时间（列表排序 / 断线恢复默认剧本；回合落库时刷新）
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 一局收尾标记（docs/56 §G：complete_quest 结算后置位；NULL=尚在冒险中）
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("length(name) > 0", name="name_not_empty"),
        Index("ix_trpg_campaigns_user_active", "user_id", "last_active_at"),
    )


class TrpgFact(TimestampMixin, Base):
    """剧情事实表（唯一写入口 app/trpg/state.py；``(campaign_id, fact_key)`` 为 upsert 锚点）。

    - kind：state（pc/scene，系统直写，LLM 提取拒写）/ fact（rel/quest/clue，LLM 提取）；
    - modality：fact=系统确认真相 / claim=NPC 声称 / rumor=传闻（防剧透）；
    - user_touched_at：用户手改标记（此后 LLM 提取拒写，P2-26 user 优先）；
    - user_deleted_at：用户删除墓碑（行保留供溯源，读路径过滤，防提取复活，P2-35）。
    """

    __tablename__ = "trpg_facts"

    id: Mapped[int] = bigint_pk()
    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trpg_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    modality: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text(f"'{TrpgFactModalities.FACT}'")
    )
    speaker: Mapped[str | None] = mapped_column(String(60))
    importance: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.5"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    user_touched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 来源消息（溯源；消息删除不影响事实，无 FK）
    source_message_id: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        CheckConstraint(
            f"kind IN ('{TrpgFactKinds.STATE}', '{TrpgFactKinds.FACT}')",
            name="kind",
        ),
        CheckConstraint(
            f"modality IN ('{TrpgFactModalities.FACT}', '{TrpgFactModalities.CLAIM}', "
            f"'{TrpgFactModalities.RUMOR}')",
            name="modality",
        ),
        CheckConstraint("importance >= 0 AND importance <= 1", name="importance"),
        CheckConstraint("version >= 1", name="version"),
        UniqueConstraint("campaign_id", "fact_key", name="uq_trpg_facts_campaign_key"),
        Index("ix_trpg_facts_campaign_kind", "campaign_id", "kind"),
    )


class TrpgTask(TimestampMixin, Base):
    """任务行（active/done/failed；快照注入活动任务全量 + 折叠计数）。"""

    __tablename__ = "trpg_tasks"

    id: Mapped[int] = bigint_pk()
    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trpg_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text(f"'{TrpgTaskStatuses.ACTIVE}'")
    )
    scene: Mapped[str | None] = mapped_column(String(40))
    last_mentioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_message_id: Mapped[int | None] = mapped_column(BigInteger)
    user_touched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            f"status IN ('{TrpgTaskStatuses.ACTIVE}', '{TrpgTaskStatuses.DONE}', "
            f"'{TrpgTaskStatuses.FAILED}')",
            name="status",
        ),
        Index("ix_trpg_tasks_campaign_status", "campaign_id", "status"),
    )


class TrpgClue(TimestampMixin, Base):
    """线索行（found/recovered；快照只注入「当前场景 + 未回收」，上限 8）。"""

    __tablename__ = "trpg_clues"

    id: Mapped[int] = bigint_pk()
    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trpg_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(60), nullable=False)
    content: Mapped[str | None] = mapped_column(String(300))
    scene: Mapped[str | None] = mapped_column(String(40))
    found: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    recovered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    last_mentioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_message_id: Mapped[int | None] = mapped_column(BigInteger)
    user_touched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_trpg_clues_campaign_found", "campaign_id", "found", "recovered"),)


class TrpgEntity(TimestampMixin, Base):
    """实体注册表（``(campaign_id, kind, name)`` 幂等键）。

    pending=True 为 LLM 发现的懒确认实体（默认可用；超窗未提及 → status=cleared）；
    **在场映射**（docs/56 §B，不加新枚举/约束）：arriving↔pending=true、departed↔status=cleared。
    """

    __tablename__ = "trpg_entities"

    id: Mapped[int] = bigint_pk()
    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trpg_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'active'"))
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # 立绘媒体（docs/56 §4：media_assets.public_id；NULL=前端按实体名命中内置素材）
    portrait_media_id: Mapped[str | None] = mapped_column(String(64))
    last_mentioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            f"kind IN ('{TrpgEntityKinds.NPC}', '{TrpgEntityKinds.PC}', "
            f"'{TrpgEntityKinds.TASK}', '{TrpgEntityKinds.CLUE}', '{TrpgEntityKinds.SCENE}')",
            name="kind",
        ),
        CheckConstraint("status IN ('active', 'pending', 'cleared')", name="status"),
        UniqueConstraint("campaign_id", "kind", "name", name="uq_trpg_entities_campaign_kind_name"),
    )


class TrpgEvent(CreatedAtMixin, Base):
    """事件日志（append-only，永不回写；判定卡与叙事摘要尾部数据源）。"""

    __tablename__ = "trpg_events"

    id: Mapped[int] = bigint_pk()
    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trpg_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    round: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)

    __table_args__ = (Index("ix_trpg_events_campaign_round", "campaign_id", "round"),)


class TrpgMessage(CreatedAtMixin, Base):
    """对话流水（user/assistant；kind=system 为开卡/过场/判定系统卡，刷新不丢）。

    - ``payload``：系统卡结构（trpgSys=open|scene|dice，前端按协议渲染）；
    - ``meta``：扩展元数据（ASR 词级时间戳等）；
    - ``usage``：LLM 用量（用量对账，非账单真源）。
    """

    __tablename__ = "trpg_messages"

    id: Mapped[int] = bigint_pk()
    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trpg_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text(f"'{TrpgMessageKinds.TEXT}'")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    payload: Mapped[dict | None] = mapped_column(jsonb())
    meta: Mapped[dict | None] = mapped_column(jsonb())
    usage: Mapped[dict | None] = mapped_column(jsonb())
    audio_url: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        CheckConstraint(
            f"role IN ('{TrpgMessageRoles.USER}', '{TrpgMessageRoles.ASSISTANT}')", name="role"
        ),
        CheckConstraint(
            f"kind IN ('{TrpgMessageKinds.TEXT}', '{TrpgMessageKinds.SYSTEM}')", name="kind"
        ),
        Index("ix_trpg_messages_campaign_id", "campaign_id", "id"),
    )


class TrpgScenarioCard(TimestampMixin, Base):
    """场景卡（开局模板；docs/52 §12）。

    - ``owner_user_id`` NULL = 平台固定卡（管理端维护、上架后所有用户可选）；非 NULL = 用户私有卡
      （按关键词 LLM 生成，仅本人可见/管理）；
    - ``template``（JSONB）：开局应用的初始模板 ``{pc:{hp,location,inventory}, facts:[…],
      tasks:[…], clues:[…]}``；应用时经服务器白名单校验后落 campaign 事实/任务/线索；
    - ``status``：draft（仅管理端）/ published（可用）/ archived（归档，不再可选）；
    - ``keywords``：用户卡的生成输入（留痕）；``generated_by``：llm / manual。
    """

    __tablename__ = "trpg_scenario_cards"

    id: Mapped[int] = bigint_pk()
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text(f"'{TrpgCardSources.ADMIN}'")
    )
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text(f"'{TrpgCardStatuses.DRAFT}'")
    )
    title: Mapped[str] = mapped_column(String(60), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(300))
    language: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text(f"'{TrpgLangs.ZH}'")
    )
    tags: Mapped[list | None] = mapped_column(jsonb())
    scene: Mapped[str | None] = mapped_column(String(40))
    opening_line: Mapped[str | None] = mapped_column(Text)
    template: Mapped[dict | None] = mapped_column(jsonb())
    keywords: Mapped[str | None] = mapped_column(String(200))
    generated_by: Mapped[str | None] = mapped_column(String(12))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            f"source IN ('{TrpgCardSources.ADMIN}', '{TrpgCardSources.USER}')", name="source"
        ),
        CheckConstraint(
            f"status IN ('{TrpgCardStatuses.DRAFT}', '{TrpgCardStatuses.PUBLISHED}', "
            f"'{TrpgCardStatuses.ARCHIVED}')",
            name="status",
        ),
        CheckConstraint(
            f"language IN ('{TrpgLangs.ZH}', '{TrpgLangs.EN}')",
            name="language",
        ),
        CheckConstraint("length(title) > 0", name="title_not_empty"),
        Index("ix_trpg_scenario_cards_owner_status", "owner_user_id", "status"),
        Index("ix_trpg_scenario_cards_status_id", "status", "id"),
    )


class TrpgUserPref(TimestampMixin, Base):
    """酒馆用户偏好（跨设备；docs/52 §12.2）。

    - ``lang``：DM 输出语言（zh/en；只影响 DM 叙述，不切界面文案）；
    - ``voice_enabled``：是否自动朗读 DM 回复（关 = 服务端不再逐句 TTS，省配额）；
    - ``voice_name``：TTS 音色（预留；NULL = 跟随服务端默认 `APP_TTS_VOICE`）。
    """

    __tablename__ = "trpg_user_prefs"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, unique=True
    )
    lang: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text(f"'{TrpgLangs.ZH}'")
    )
    voice_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    voice_name: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        CheckConstraint(
            f"lang IN ('{TrpgLangs.ZH}', '{TrpgLangs.EN}')",
            name="lang",
        ),
    )


__all__ = [
    "TrpgCampaign",
    "TrpgClue",
    "TrpgEntity",
    "TrpgEvent",
    "TrpgFact",
    "TrpgMessage",
    "TrpgScenarioCard",
    "TrpgTask",
    "TrpgUserPref",
]
