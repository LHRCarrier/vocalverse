"""媒体资产域（社区 S3 · docs/47 §3.1）：图片 / 视频 / 头像。

**Python 唯一写方**（docs/10 §3.1 写方矩阵）；Java 侧只在 ``posts.media`` jsonb 里存 URL，
不读写本表（跨服务读表会破坏写方矩阵，docs/48 §3-A）。

设计要点（v2，依据 docs/48 拷问）：

- ``public_id`` 是对外唯一标识（``secrets.token_hex(16)``）：**URL 只用它**，
  自增 ``id`` 不外露 —— 否则逐号 curl 即可枚举全站媒体（docs/48 B2）；
- ``sha256`` 是**物理文件**去重键（内容寻址，同内容只落一份盘）；
  但**行级唯一键是 ``(owner_id, sha256) WHERE status='ready'``**：全局唯一 + 软删
  会让「A 传 X → 删 X → 再传 X」永远回读到已删行、他人也永久传不上同一内容（docs/48 B1）；
- 软删（``status='deleted'``）只标记，**不动物理文件**：物理回收的三条件
  （无任何 ready 行 / 宽限期 / advisory lock）登记 S4，本期不做（docs/48 B19）。
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, bigint_pk


class MediaAsset(TimestampMixin, Base):
    """媒体资产行（图片/视频/头像）。"""

    __tablename__ = "media_assets"

    id: Mapped[int] = bigint_pk()
    #: 对外标识（URL 路径段）；不可猜、唯一
    public_id: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    #: image | video | avatar（Java 侧 kind 与之对齐；avatar 供 user_profiles.avatar_url）
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    #: 魔数嗅探得到的真实类型（不信任客户端 Content-Type / 文件名）
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: 物理文件内容寻址键（跨 owner 共享同一份文件）
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: 相对 media_dir 的路径（yyyy/mm/<sha256>.<ext>）
    storage_path: Mapped[str] = mapped_column(String(255), nullable=False)
    width: Mapped[int | None] = mapped_column(BigInteger)
    height: Mapped[int | None] = mapped_column(BigInteger)
    duration_s: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'ready'"))

    __table_args__ = (
        CheckConstraint("kind IN ('image', 'video', 'avatar')", name="kind"),
        # 隐藏≠删除（迁移 0013 · docs/50 §5.4）：审核处置可置 hidden（行保留、可恢复），
        # 与 posts/post_comments 的 visible|hidden|deleted 语义对齐
        CheckConstraint("status IN ('ready', 'hidden', 'deleted')", name="status"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        UniqueConstraint("public_id", name="uq_media_assets_public_id"),
        # 行级去重：同一 owner 的同内容只保留一条 ready 行；软删后可重新入库（docs/48 B1）
        Index(
            "uq_media_assets_owner_sha_ready",
            "owner_id",
            "sha256",
            unique=True,
            postgresql_where=text("status = 'ready'"),
            sqlite_where=text("status = 'ready'"),
        ),
        Index("ix_media_assets_owner_time", "owner_id", "created_at"),
        Index("ix_media_assets_status_time", "status", "created_at"),
    )


class MediaKinds:
    IMAGE = "image"
    VIDEO = "video"
    AVATAR = "avatar"


class MediaStatus:
    READY = "ready"
    HIDDEN = "hidden"  # 审核隐藏（迁移 0013 · docs/50 §5.4）
    DELETED = "deleted"
