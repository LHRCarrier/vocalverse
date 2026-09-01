"""练习域：sessions / attempts / scores / sing_attempts（均 **Python 写**）。

- ``sessions``：一次练习会话头（对话/唱歌），承载「完成率/互动率」等的会话级事实；
  只存原始事实（turn_count、duration_s），口径判定（5 轮或 2min）在报表层算，口径可重算；
- ``attempts``：一次录音评分的完整结果（口语）；``scores`` 为其音素级明细；
- ``sing_attempts``：一次跟唱评分的逐句结果（音准/节奏/发音 + 对齐信息，docs/06 §9.4）。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    AttemptKinds,
    Base,
    CreatedAtMixin,
    SessionKinds,
    SessionStatus,
    TimestampMixin,
    bigint_pk,
    jsonb,
)


class Session(TimestampMixin, Base):
    """练习会话头（Python 写）。

    - kind：dialog（场景对话）/ sing（跟唱）——入学测试(placement)不复用本表，
      独立状态机在 placements（避免重复状态源，见 docs/10 开放项 B-2）；
    - scenario_id/song_id：内容快照引用；内容归档/删除不影响历史（SET NULL）；
    - 完成事实：turn_count（含系统消息总轮）/ duration_s 以会话关闭时刻为准；
      完成率口径（5 轮或 2min / 整首逐句评分结束）由报表层按事件重算，不写死。
    """

    __tablename__ = "sessions"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    scenario_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("scenarios.id", ondelete="SET NULL")
    )
    song_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("songs.id", ondelete="SET NULL")
    )
    # 答辩档案引用（docs/14 §6.1）：defense 会话指向 defense_profiles；
    # 档案删除（软删）不影响历史；SET NULL 与 scenario_id/song_id 语义一致
    profile_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("defense_profiles.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{SessionStatus.ACTIVE}'")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    turn_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    # 口径计数（docs/11 Q-B03/04）：user_turn_count=用户轮数（完成率「5 轮」口径）；
    # assigned_turns=会话开始时的目标分配轮数（互动率分母）；turn_count 保留为总消息数（审计）
    user_turn_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    assigned_turns: Mapped[int | None] = mapped_column(SmallInteger)
    duration_s: Mapped[int | None] = mapped_column(BigInteger)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'web'"))

    __table_args__ = (
        CheckConstraint(
            f"kind IN ('{SessionKinds.DIALOG}', '{SessionKinds.SING}', '{SessionKinds.DEFENSE}')",
            name="kind",
        ),
        CheckConstraint(
            f"status IN ('{SessionStatus.ACTIVE}', '{SessionStatus.COMPLETED}', "
            f"'{SessionStatus.ABANDONED}')",
            name="status",
        ),
        CheckConstraint("turn_count >= 0", name="turn_count"),
        CheckConstraint("user_turn_count >= 0", name="user_turn_count"),
        Index("ix_sessions_user_started", "user_id", "started_at"),
        Index("ix_sessions_status_kind", "status", "kind"),
    )


class Attempt(TimestampMixin, Base):
    """一次口语录音的评分结果（Python 写；attempts = 评分快照，一次录音一条）。

    - 评分字段可空：管线降级/失败时落 error 而不伪造分数（报告口径「完成度」区分）；
    - transcript 为 ASR 转写（仅存文本，原始音频默认 24h 清理，docs/06 §9.7）；
    - details：词级错误明细 [{word, word_index, error_type, suggestion, demo_audio_url}]
      （单词级定位，docs/06 §9.3）；音素级明细在 scores 表。
    """

    __tablename__ = "attempts"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sessions.id", ondelete="SET NULL")
    )
    # 与对话流的绑定（docs/11 Q-B09）：scenario_messages.content=该轮定稿文本，
    # attempts.transcript=评分用 ASR 原文，二者可不同，靠本外键对齐（重录/改轮不崩）
    scenario_message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("scenario_messages.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text(f"'{AttemptKinds.DIALOG_SPEECH}'")
    )
    audio_url: Mapped[str | None] = mapped_column(String(512))
    # 降级路径（docs/11 Q-B08）：ASR 失败（无转写）或未测时长达标时仍须落 error 快照，
    # 故 duration_s/transcript 允许 NULL（分数系列本就 NULL 允许）
    duration_s: Mapped[int | None] = mapped_column(SmallInteger)
    transcript: Mapped[str | None] = mapped_column(Text)
    # 评分列：Numeric(5,2) 运行时返回 Decimal（勿用 float 注解，docs/11 Q-A02）
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    pron_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    flu_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    gram_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    completeness: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2)
    )  # 回退口径备用（docs/06 §9.3）
    wpm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))  # 语速辅助指标（docs/07 流利度）
    details: Mapped[dict] = mapped_column(jsonb(), nullable=False, server_default=text("'{}'"))
    error: Mapped[dict] = mapped_column(jsonb(), nullable=False, server_default=text("'{}'"))

    __table_args__ = (
        CheckConstraint(
            f"kind IN ('{AttemptKinds.DIALOG_SPEECH}', '{AttemptKinds.FREE_PRACTICE}', "
            f"'{AttemptKinds.PLACEMENT_ITEM}', '{AttemptKinds.DEFENSE_ANSWER}')",
            name="kind",
        ),
        Index("ix_attempts_user_created", "user_id", "created_at"),
        Index("ix_attempts_session_id", "session_id"),
        Index("ix_attempts_scenario_message_id", "scenario_message_id"),
    )


class Score(CreatedAtMixin, Base):
    """音素级评分明细（Python 写；仅重难点词出音素级，ADR 9.3 单词级为默认粒度）。

    - word_index/start_ms/end_ms：与 attempt 的对齐锚点；
    - error_type：替换/省略/插入/重音/语调等错误定位；
    - is_key_word：重难点词标记（触发音素级提示 + 正确示范 TTS）。
    """

    __tablename__ = "scores"

    id: Mapped[int] = bigint_pk()
    attempt_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("attempts.id", ondelete="CASCADE"), nullable=False
    )
    word_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    phoneme: Mapped[str] = mapped_column(String(64), nullable=False)
    start_ms: Mapped[int | None] = mapped_column(BigInteger)
    end_ms: Mapped[int | None] = mapped_column(BigInteger)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(32))
    is_key_word: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))

    __table_args__ = (
        UniqueConstraint(
            "attempt_id", "word_index", "phoneme", name="uq_scores_attempt_word_phoneme"
        ),
        CheckConstraint(
            "error_type IN ('substitution', 'omission', 'insertion', "
            "'mispronunciation', 'stress', 'intonation', 'other') OR error_type IS NULL",
            name="error_type",
        ),
    )


class SingAttempt(CreatedAtMixin, Base):
    """一次跟唱评分（Python 写；一首歌整条：逐句结果 + 对齐信息）。

    - lines：逐句 [{seq, start_ms, end_ms, pitch_score, rhythm_score, pron_score,
      synced, skipped}]（docs/06 §9.4 逐句音准/节奏/发音）；
    - alignment：整体对齐摘要 {bpm_ratio, offset_ms, method, version}——
      DTW 参数/算法升级后可解释同曲分数变化；
    - pron 复用口语评分引擎（docs/06 §9.4 发音=复用口语评分）。
    """

    __tablename__ = "sing_attempts"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sessions.id", ondelete="SET NULL")
    )
    song_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("songs.id"), nullable=False)
    # 评分所用 LRC 版本（docs/11 Q-B10）：lrc 可整首重写，历史 sang 结果按本列对锚；
    # lrc 行删除时 SET NULL（不毁历史评分）
    lrc_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("lrc.id", ondelete="SET NULL")
    )
    audio_url: Mapped[str | None] = mapped_column(String(512))
    duration_s: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    pitch_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    rhythm_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    pron_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # 完成判定（docs/11 Q-B02）：唱歌完成率=整首逐句评分结束；
    # is_complete=true 且 scored 且 not skipped 的句数==expected_lines（评分时 lrc 行数快照）
    is_complete: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    expected_lines: Mapped[int | None] = mapped_column(SmallInteger)
    lines: Mapped[dict] = mapped_column(jsonb(), nullable=False, server_default=text("'[]'"))
    alignment: Mapped[dict] = mapped_column(jsonb(), nullable=False, server_default=text("'{}'"))

    __table_args__ = (
        Index("ix_sing_attempts_user_created", "user_id", "created_at"),
        Index("ix_sing_attempts_song_id", "song_id"),
        Index("ix_sing_attempts_lrc_id", "lrc_id"),
    )


class PostLike(CreatedAtMixin, Base):
    """社区点赞（**Python 写**；docs/06 §9.6 社区最小版「点赞」唯一必须持久化的数据）。

    - 打卡与只读动态流**不建表**：单日≥1 次口语练习由 sessions 按日派生；
      跨用户动态流由 sessions/attempts/users JOIN 派生；唯有点赞是多对多；
    - 自然键 = (liker_id, author_id, practice_date)（一天最多 1 打卡）；
    - 成绩卡片由前端 canvas 用 session/attempt 数据重生成，不落库。
    """

    __tablename__ = "post_likes"

    id: Mapped[int] = bigint_pk()
    liker_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    author_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    practice_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "liker_id", "author_id", "practice_date", name="uq_post_likes_liker_author_date"
        ),
        Index("ix_post_likes_author_date", "author_id", "practice_date"),
    )
