"""社区内容域：posts / post_comments / post_likes / post_interactions / follows。

**全部 Java 写**（docs/37 §4 写方矩阵：社区 5 表单写方 = Java；Python 只读——画像/推荐
后续消费；本文件是 alembic check 的 metadata 真源，读侧模型的唯一例外：
声明映射 ≠ 写，禁止在本包出现任何 Session.add / update 社区表）。

- ``posts``：内容帖（article/video）+ 打卡卡（checkin，domain=NULL，仅「为你推荐」混排）；
  媒体为 jsonb 占位（字段集对齐 docs/38 MediaItem：type/url/coverUrl/duration_s/width/height/
  size/mimeType）；打卡卡公开面 {overall, practice_count}（其余子分仅记录不展示）；
- ``post_likes``：帖子点赞（2026-09-06 键改造：旧「打卡点赞」liker/author/practice_date 废弃）；
- ``post_interactions``：互动时序单（like/coin/share），画像/通知数据源；无软删列——
  取消表态=物理删行，幂等由 (actor, post, action) 唯一键保证；
- ``follows``：关注关系（S1 建表、S2 接口）。

字段口径与登记见 docs/37 §3.1、docs/10（表清单 19→24 待 P4 登记）。
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
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, TimestampMixin, bigint_pk, jsonb


class Post(TimestampMixin, Base):
    """内容帖 + 打卡卡（Java 写；kind/domain/status 枚举见 CheckConstraint）。"""

    __tablename__ = "posts"

    id: Mapped[int] = bigint_pk()
    author_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    # 种子稳定键（内容帖；checkin 用 (author_id, checkin_date) 幂等键）
    slug: Mapped[str | None] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # 三领域知识轴；checkin 为 NULL（仅「为你推荐」混排）
    domain: Mapped[str | None] = mapped_column(String(16))
    title: Mapped[str | None] = mapped_column(String(200))  # 发帖可选；空则前端隐藏标题行
    body: Mapped[str | None] = mapped_column(Text)  # 纯文本；≤8000 由应用层校验
    tags: Mapped[dict | None] = mapped_column(jsonb())  # 话题占位（S2 热度再拆 post_tag）
    # 媒体元数据占位（S2 拆 media 表）；字段集对齐 MediaItem——duration 存秒
    media: Mapped[dict | None] = mapped_column(jsonb())
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'visible'")
    )  # visible / hidden（管理员下架位）/ deleted（软删）
    checkin_date: Mapped[date | None] = mapped_column(Date)  # 仅 checkin：打卡日（幂等键）
    # 仅 checkin：分数快照；公开面 {overall, practice_count}，其余仅记录（C-08/C-10）；
    # 禁止 transcript/audio_url 等练习明细入库
    checkin_snapshot: Mapped[dict | None] = mapped_column(jsonb())
    # 打卡↔会话可溯源（SET NULL，不破坏内容表边界）
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sessions.id", ondelete="SET NULL")
    )
    like_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    coin_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    comment_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    share_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))

    __table_args__ = (
        CheckConstraint("kind IN ('article', 'video', 'checkin')", name="kind"),
        CheckConstraint(
            "domain IS NULL OR domain IN ('news', 'teaching', 'overseas')", name="domain"
        ),
        CheckConstraint("status IN ('visible', 'hidden', 'deleted')", name="status"),
        # 混排（为你推荐）keyset 主路径：status 前缀防漏过滤；PG 反向扫描即 DESC 序
        Index("ix_posts_feed_time", "status", "created_at", "id"),
        # 领域 Tab：status+domain 前缀
        Index("ix_posts_domain_time", "status", "domain", "created_at", "id"),
        Index("ix_posts_author", "author_id", "created_at"),
        # 每日一卡：部分唯一（仅 kind='checkin'）；双方言声明（SQLite 单测也建得出）
        Index(
            "uq_posts_checkin",
            "author_id",
            "checkin_date",
            unique=True,
            postgresql_where=text("kind = 'checkin'"),
            sqlite_where=text("kind = 'checkin'"),
        ),
    )


class PostComment(TimestampMixin, Base):
    """帖子评论（平铺二级：root_id 预热，S1 恒 NULL；parent_id 为直接回复目标）。"""

    __tablename__ = "post_comments"

    id: Mapped[int] = bigint_pk()
    post_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("posts.id"), nullable=False)
    author_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    # 嵌套楼 P1 预热（D-Q9：免 S2 ALTER；S1 恒 NULL）
    root_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("post_comments.id"))
    parent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("post_comments.id"))
    reply_to_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    reply_to_nickname: Mapped[str | None] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'visible'")
    )

    __table_args__ = (
        CheckConstraint("status IN ('visible', 'hidden', 'deleted')", name="status"),
        Index("ix_post_comments_status_post", "status", "post_id", "created_at", "id"),
    )


class PostLike(CreatedAtMixin, Base):
    """帖子点赞（Java 写；2026-09-06 键改造：(post_id, liker_id) 唯一）。

    旧语义（liker/author/practice_date「打卡点赞」）废弃——点赞对象随内容化社区
    升级为帖子；改造在迁移 0007（0 行断言）。
    """

    __tablename__ = "post_likes"

    id: Mapped[int] = bigint_pk()
    post_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("posts.id"), nullable=False)
    liker_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("post_id", "liker_id", name="uq_post_likes_post_liker"),
        Index("ix_post_likes_post", "post_id"),
    )


class PostInteraction(CreatedAtMixin, Base):
    """互动时序单（like/coin/share；画像/通知数据源）。无软删列：取消表态=物理删行，
    幂等由 (actor_id, post_id, action) 唯一键保证（docs/37 §3.2）。"""

    __tablename__ = "post_interactions"

    id: Mapped[int] = bigint_pk()
    actor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    post_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("posts.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        CheckConstraint("action IN ('like', 'coin', 'share')", name="action"),
        UniqueConstraint(
            "actor_id", "post_id", "action", name="uq_post_interactions_actor_post_action"
        ),
        Index("ix_post_interactions_post_action", "post_id", "action", "created_at"),
    )


class Follow(CreatedAtMixin, Base):
    """关注关系（S1 建表、S2 接口；checkin 关注流预置 followee 索引）。"""

    __tablename__ = "follows"

    id: Mapped[int] = bigint_pk()
    follower_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    followee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        CheckConstraint("follower_id <> followee_id", name="no_self_follow"),
        UniqueConstraint("follower_id", "followee_id", name="uq_follows_follower_followee"),
        Index("ix_follows_followee", "followee_id"),
    )


class DirectMessage(CreatedAtMixin, Base):
    """一对一私信消息（Java 写；docs/49 §1.1，迁移 0012）。

    只记 created_at（不可变行，无 updated_at）；会话= (sender, recipient) 对，不建会话表。
    ``status`` 为治理预留（本轮恒 'visible'，无删除入口）；迁移 0013 起 CHECK 另含
    ``'hidden'``（审核隐藏，docs/50 §5.4）。
    """

    __tablename__ = "direct_messages"

    id: Mapped[int] = bigint_pk()
    sender_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    recipient_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)  # 上限由应用层校验（42203）
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'visible'")
    )

    __table_args__ = (
        CheckConstraint("sender_id <> recipient_id", name="no_self_message"),
        # 审核隐藏（迁移 0013 · docs/50 §5.4）：本期只读列表不提供处置，约束先就位
        CheckConstraint("status IN ('visible', 'hidden', 'deleted')", name="status"),
        Index("ix_dm_pair_time", "sender_id", "recipient_id", "created_at", "id"),
        Index("ix_dm_recipient_time", "recipient_id", "created_at", "id"),
        Index("ix_dm_sender_time", "sender_id", "created_at", "id"),
    )


class DmReadState(Base):
    """私信已读水位（Java 写；docs/49 §1.2，迁移 0012）。

    **水位是 ``last_read_id`` 而非时间戳**：时间戳水位在并发提交下会跨过尚未渲染的消息，
    造成永久漏未读；消息 id 单调，取 ``max(现有, upTo)`` 无此问题（docs/49 §4.3 B2）。
    未读定义 = 对端 visible 消息中 ``id > last_read_id`` 的条数（缺行视作 0）。
    """

    __tablename__ = "dm_read_state"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    peer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    last_read_id: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint("user_id <> peer_id", name="no_self_peer"),
        # 代理主键 + 业务唯一键（本仓 Java/JPA 侧全实体统一 `@Id Long id` 形态；
        # 业务唯一语义由本约束保证，`(user_id, peer_id)` 仍是「一会话一行」的真键）
        UniqueConstraint("user_id", "peer_id", name="uq_dm_read_state_user_peer"),
        Index("ix_dm_read_state_user", "user_id"),
    )
