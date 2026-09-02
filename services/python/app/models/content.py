"""内容库：scenarios / scenario_messages / songs / lrc / song_pitch_refs / listening_materials。

写归属（docs/10 §3）：
- ``scenarios`` / ``songs`` / ``lrc`` / ``listening_materials`` —— **Java（内容 CRUD + 上下架）**；
- ``scenario_messages``（会话消息流水，对话运行时产生）—— **Python**；
- ``song_pitch_refs``（离线参考旋律提取结果，算法侧产出）—— **Python**；
  与 Java 主表 songs/lrc 的耦合靠「lrc_id 外键 + 内容下架/删除联动」解耦（见 docs/10 §3.2）。
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    Base,
    ContentStatus,
    CreatedAtMixin,
    MessageRoles,
    PitchRefStatus,
    TimestampMixin,
    bigint_pk,
    jsonb,
)

# 场景类型（docs/06 §9.6 定稿 4 类 + other 兜底）
SCENE_TYPES = ("cafe", "airport", "interview", "library", "other")

# 内容来源（商用音乐严禁入库，docs/06 §9.7）
CONTENT_SOURCES = ("public_domain", "original", "demo_only")


class Scenario(TimestampMixin, Base):
    """对话场景模板（Java 写）。内容：角色设定 / 开场白 / 目标语料 / 难度分级。

    - prompt_version：system_prompt 修订序号。会话中 LLM 每轮记快照，
      旧会话可在报告/复盘中按版本解释行为差异（不改历史）；
    - interest_tags 给推荐系统做匹配；status 仅 draft/published/archived（不物理删除）。
    """

    __tablename__ = "scenarios"

    id: Mapped[int] = bigint_pk()
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    scene_type: Mapped[str] = mapped_column(String(32), nullable=False)
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    description: Mapped[str | None] = mapped_column(String(512))
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)  # 角色设定
    opening_line: Mapped[str] = mapped_column(Text, nullable=False)  # 开场白
    target_corpus: Mapped[str | None] = mapped_column(Text)  # 目标语料/句式
    interest_tags: Mapped[dict] = mapped_column(
        jsonb(), nullable=False, server_default=text("'[]'")
    )
    prompt_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    estimated_turns: Mapped[int | None] = mapped_column(SmallInteger)
    estimated_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{ContentStatus.DRAFT}'")
    )

    __table_args__ = (
        CheckConstraint(
            "scene_type IN ('cafe', 'airport', 'interview', 'library', 'other')", name="scene_type"
        ),
        CheckConstraint("difficulty BETWEEN 1 AND 4", name="difficulty"),
        CheckConstraint(
            f"status IN ('{ContentStatus.DRAFT}', '{ContentStatus.PUBLISHED}', "
            f"'{ContentStatus.ARCHIVED}')",
            name="status",
        ),
        # 推荐/列表页常用过滤组合
        Index("ix_scenarios_status_diff", "status", "difficulty"),
        Index("ix_scenarios_scene_type", "scene_type"),
    )


class ScenarioMessage(CreatedAtMixin, Base):
    """会话消息流水（Python 写；不可变，只 INSERT）。

    字段设计支撑 docs/06 §9.1 指标口径：
    - ``origin``：user 消息区分「主动发起(proactive)/响应(respond)」——互动率分子分母；
    - ``action``：功能互动（点示范/纠错/二次录制）——互动率补充指标；
    - ``prompt_version``：该轮 LLM 使用 system prompt 版本快照；
    - ``meta``：轮次级流水线状态（ASR/评分/LLM/TTS 各步耗时与错误快照，排障用）。
    """

    __tablename__ = "scenario_messages"

    id: Mapped[int] = bigint_pk()
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 会话内序号，从 1
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    origin: Mapped[str | None] = mapped_column(String(24))
    action: Mapped[str | None] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    audio_url: Mapped[str | None] = mapped_column(String(512))
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    prompt_version: Mapped[int | None] = mapped_column(SmallInteger)
    meta: Mapped[dict] = mapped_column(jsonb(), nullable=False, server_default=text("'{}'"))

    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_scenario_messages_session_seq"),
        CheckConstraint(
            f"role IN ('{MessageRoles.SYSTEM}', '{MessageRoles.USER}', '{MessageRoles.ASSISTANT}')",
            name="role",
        ),
        CheckConstraint(
            "origin IS NULL OR (role = 'user' AND origin IN ('proactive', 'respond'))",
            name="origin",
        ),
        CheckConstraint(
            "action IN ('demo', 'correction', 'retry', 'hint') OR action IS NULL", name="action"
        ),
    )


class Song(TimestampMixin, Base):
    """歌曲库（Java 写）。demo 只用公有领域/自创曲，商用音乐不入库（docs/06 §9.7）。

    - duration_s/bpm/key 供节奏对齐粗校准（文档层面，实际以 song_pitch_refs 为准）；
    - lrc_url 仅存原始 LRC 文件引用（可选）；逐句数据在 lrc 表（逐句评分唯一真源）。
    """

    __tablename__ = "songs"

    id: Mapped[int] = bigint_pk()
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    artist: Mapped[str | None] = mapped_column(String(128))
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    duration_s: Mapped[int | None] = mapped_column(BigInteger)
    bpm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    musical_key: Mapped[str | None] = mapped_column(String(8))
    audio_url: Mapped[str] = mapped_column(String(512), nullable=False)
    lrc_url: Mapped[str | None] = mapped_column(String(512))
    cover_url: Mapped[str | None] = mapped_column(String(512))
    interest_tags: Mapped[dict] = mapped_column(
        jsonb(), nullable=False, server_default=text("'[]'")
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'public_domain'")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{ContentStatus.DRAFT}'")
    )
    # 参考旋律就绪状态（docs/11 Q-B11）：LRC 重写→song_pitch_refs 级联清→离线重提取期间
    # 跟唱请求见 status!='ready' 返回「生成中/缺词」，不静默算分；由 Python 离线任务翻转
    pitch_ref_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text(f"'{PitchRefStatus.MISSING}'")
    )

    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 4", name="level"),
        CheckConstraint(
            f"status IN ('{ContentStatus.DRAFT}', '{ContentStatus.PUBLISHED}', "
            f"'{ContentStatus.ARCHIVED}')",
            name="status",
        ),
        CheckConstraint("source IN ('public_domain', 'original', 'demo_only')", name="source"),
        CheckConstraint(
            f"pitch_ref_status IN ('{PitchRefStatus.MISSING}', '{PitchRefStatus.BUILDING}', "
            f"'{PitchRefStatus.READY}', '{PitchRefStatus.INVALID}')",
            name="pitch_ref_status",
        ),
        Index("ix_songs_status_level", "status", "level"),
    )


class Lrc(CreatedAtMixin, Base):
    """逐句歌词（Java 写）。逐句评分唯一真源。

    - offset_ms/end_offset_ms：句窗口（end 为 docs/10 设计补充，评分对齐用；
      若 Java 沿用纯 LRC 无 end，可空，由算法按下一句 offset 推断）；
    - 编辑方式为「整首重写」：改 LRC → 删旧插新（seq 1..n 重排），
      song_pitch_refs 随 lrc_id 级联删除并离线重提取（Python 侧）。
    """

    __tablename__ = "lrc"

    id: Mapped[int] = bigint_pk()
    song_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    offset_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_offset_ms: Mapped[int | None] = mapped_column(BigInteger)
    # 注意：属性名用 line_text（列名仍是 text）——若属性命名为 text 会遮蔽模块级
    # text() 函数，同 class body 内后续 server_default 全部崩（docs/11 Q-A19）
    line_text: Mapped[str] = mapped_column("text", Text, nullable=False)
    # 版权来源追踪（docs/11 Q-B19）：逐句歌词文本本身可含商用内容，
    # 冗余自 songs.source 便于逐句审计；Java 写须与 songs.source 保持一致
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'public_domain'")
    )

    __table_args__ = (
        UniqueConstraint("song_id", "seq", name="uq_lrc_song_seq"),
        CheckConstraint("source IN ('public_domain', 'original', 'demo_only')", name="source"),
    )


class SongPitchRef(CreatedAtMixin, Base):
    """参考旋律音高序列（Python 写；docs/06 §9.4 音准评分的「离线预提取」产物）。

    - 与 lrc 逐句 1:1（lrc_id 外键；LRC 重写 → 本表级联删除 → 触发重提取），
      这是「Java 内容库 vs Python 算法产物」耦合点的唯一交点；
    - pitch_ref：该句参考 F0 序列（float 数组，帧 hop 512@16k）；
    - extractor/version：可追溯（pyin 参数或算法升级后重新提取，避免同曲不同标定）。
    """

    __tablename__ = "song_pitch_refs"

    id: Mapped[int] = bigint_pk()
    lrc_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lrc.id", ondelete="CASCADE"), nullable=False
    )
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pitch_ref: Mapped[dict] = mapped_column(jsonb(), nullable=False)  # {"f0s":[...], "notes":[...]}
    extractor: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'pyin'")
    )
    version: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (UniqueConstraint("lrc_id", name="uq_song_pitch_refs_lrc_id"),)


class ListeningMaterial(TimestampMixin, Base):
    """听力素材（Java 写；docs/06 §9.6「1 个听力素材示例」，推荐候选池第三类）。

    说明：docs/06 §10 表清单未列本表，属设计补充（依据 §9.5/§9.6），待组长拍板；
    若砍掉，推荐候选池回退为「场景+歌曲」两类并在 docs/06 同步。
    """

    __tablename__ = "listening_materials"

    id: Mapped[int] = bigint_pk()
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    audio_url: Mapped[str] = mapped_column(String(512), nullable=False)
    duration_s: Mapped[int | None] = mapped_column(BigInteger)
    transcript: Mapped[str | None] = mapped_column(Text)  # ASR 字幕示例
    interest_tags: Mapped[dict] = mapped_column(
        jsonb(), nullable=False, server_default=text("'[]'")
    )
    # 版权来源（docs/11 Q-B19）：新闻/音频素材同样有版权，不默认 public_domain
    source: Mapped[str | None] = mapped_column(String(32))
    license: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{ContentStatus.DRAFT}'")
    )

    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 4", name="level"),
        CheckConstraint(
            "source IN ('public_domain', 'original', 'demo_only') OR source IS NULL",
            name="source",
        ),
        CheckConstraint(
            f"status IN ('{ContentStatus.DRAFT}', '{ContentStatus.PUBLISHED}', "
            f"'{ContentStatus.ARCHIVED}')",
            name="status",
        ),
        Index("ix_listening_materials_status_level", "status", "level"),
    )


class PlacementQuestion(TimestampMixin, Base):
    """入学测试题库（**Java 写**；docs/06 §9.2「admin 题库预置，保证可复现」）。

    - exam_revision：版本号（placements.exam_revision 引用本表版本；改题=新版本，不改历史）；
    - item_index：题序（UNIQUE(exam_revision, item_index)，即 1..n 顺序，不再单设 order_num）；
    - kind：read（固定朗读句）/ qa（1 轮 QA）；reference_answer 供 QA 参考/判定口径；
    - 新增表依据：docs/11 Q-B06（P0）——原设计只有 placements 结果表，题库无处存。
    """

    __tablename__ = "placement_questions"

    id: Mapped[int] = bigint_pk()
    exam_revision: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    item_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'read'"))
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    reference_answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{ContentStatus.PUBLISHED}'")
    )

    __table_args__ = (
        UniqueConstraint("exam_revision", "item_index", name="uq_placement_questions_rev_idx"),
        CheckConstraint("kind IN ('read', 'qa')", name="kind"),
        CheckConstraint(
            f"status IN ('{ContentStatus.PUBLISHED}', '{ContentStatus.ARCHIVED}')",
            name="status",
        ),
        Index("ix_placement_questions_revision", "exam_revision"),
    )


class ShadowMaterial(TimestampMixin, Base):
    """影子跟读素材内容库（**Java 写**；local/26 §6 / local/31 §2.4，2026-09-02 设计）。

    - 与 scenarios 并列的候选池第二类；难度先验由 Python 侧 material_difficulty 产出；
    - level：内容方初评 1-4（与 scenarios.difficulty 同语义，仅作难度兜底 FALLBACK_LEVEL）；
    - wpm：原声语速（流利度难度特征）；audio：示范音频（慢速由 TTS/变速派生，不另存大文件）；
    - source 版权红线同 songs（docs/06 §9.7：商用音乐/音频严禁入库）；
    - 人工标注审计（local/32 A-3.3）建议列，随 0003 评估（pending_review 走 material_difficulty）。
    """

    __tablename__ = "shadow_materials"

    id: Mapped[int] = bigint_pk()
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 内容方初评 1-4
    text_content: Mapped[str] = mapped_column(Text, nullable=False)  # 跟读文本（逐句，供特征/字幕）
    audio_url: Mapped[str] = mapped_column(String(512), nullable=False)
    wpm: Mapped[int | None] = mapped_column(SmallInteger)  # 原声语速（词/分）
    duration_s: Mapped[int | None] = mapped_column(BigInteger)
    interest_tags: Mapped[dict] = mapped_column(
        jsonb(), nullable=False, server_default=text("'[]'")
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'public_domain'")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{ContentStatus.DRAFT}'")
    )

    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 4", name="level"),
        CheckConstraint("source IN ('public_domain', 'original', 'demo_only')", name="source"),
        CheckConstraint(
            f"status IN ('{ContentStatus.DRAFT}', '{ContentStatus.PUBLISHED}', "
            f"'{ContentStatus.ARCHIVED}')",
            name="status",
        ),
        Index("ix_shadow_materials_status_level", "status", "level"),
    )
