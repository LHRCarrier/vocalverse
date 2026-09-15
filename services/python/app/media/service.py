"""媒体服务（社区 S3 · docs/47 §4.1）。

职责：校验（体积/类型/元数据）→ 内容寻址落盘 → 落库；读取与软删。

写方：本模块是 ``media_assets`` 的**唯一写方**（docs/10 §3.1）。
错误码：41301（超限，拓宽既有码语义）/ 41501（类型不在白名单）/ 42205（元数据非法）/
40403（不存在或已删除）/ 40302（非 owner）—— 均先登记 ``docs/api/error-codes.md``。
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.media import sniff, storage
from app.models import MediaAsset, MediaKinds, MediaStatus

logger = get_logger("app.media.service")

KINDS = (MediaKinds.IMAGE, MediaKinds.VIDEO, MediaKinds.AVATAR)


class MediaError(Exception):
    """媒体域业务异常（由路由转成 BizError，避免 service 依赖 HTTP 层）。"""

    def __init__(self, http_status: int, code: int, message: str, reason: str):
        self.http_status = http_status
        self.code = code
        self.message = message
        self.reason = reason  # 日志枚举：too_large / bad_type / bad_meta / not_found / forbidden
        super().__init__(message)


def media_dir() -> Path:
    return Path(get_settings().media_dir)


def validate_kind(kind: str) -> str:
    if kind not in KINDS:
        raise MediaError(422, 42205, "kind invalid", "bad_meta")
    return kind


def validate_size(kind: str, size: int) -> None:
    s = get_settings()
    limit = s.media_max_video_bytes if kind == MediaKinds.VIDEO else s.max_upload_bytes
    if size <= 0:
        raise MediaError(400, 40002, "file empty", "too_small")
    if size > limit:
        raise MediaError(413, 41301, f"file too large (max {limit} bytes)", "too_large")


def validate_meta(
    width: Any, height: Any, duration_s: Any
) -> tuple[int | None, int | None, Decimal | None]:
    """宽/高/时长只做上界与正数校验（真实值由客户端上报，服务端不解析容器）。"""
    s = get_settings()

    def _int(v: Any, name: str) -> int | None:
        if v in (None, "", "null"):
            return None
        try:
            n = int(v)
        except (TypeError, ValueError) as exc:
            raise MediaError(422, 42205, f"{name} invalid", "bad_meta") from exc
        if n <= 0 or n > s.media_max_dimension:
            raise MediaError(422, 42205, f"{name} out of range", "bad_meta")
        return n

    w = _int(width, "width")
    h = _int(height, "height")
    dur: Decimal | None = None
    if duration_s not in (None, "", "null"):
        try:
            dur = Decimal(str(duration_s))
        except Exception as exc:  # noqa: BLE001 - 任意非法输入统一 42205
            raise MediaError(422, 42205, "duration_s invalid", "bad_meta") from exc
        if dur <= 0 or dur > s.media_max_duration_s:
            raise MediaError(422, 42205, "duration_s out of range", "bad_meta")
    return w, h, dur


def create(
    db: Session,
    *,
    user_id: int,
    kind: str,
    chunks: Any,
    width: Any = None,
    height: Any = None,
    duration_s: Any = None,
) -> tuple[MediaAsset, bool]:
    """写入媒体：返回 (行, dedup)。dedup=True 表示同 owner 同内容已存在（复用既有行）。

    先落盘（内容寻址）→ 再插行：落盘失败不会留下 DB 脏行；
    行唯一键冲突（并发同内容）→ 回读既有 ready 行。
    """
    kind = validate_kind(kind)
    w, h, dur = validate_meta(width, height, duration_s)

    # 分块写盘 + 嗅探：先读第一块判定类型（白名单外立即拒绝，不落盘）
    stream = iter(chunks)
    head = b""
    buffered: list[bytes] = []
    for chunk in stream:
        if not chunk:
            continue
        buffered.append(chunk)
        head = b"".join(buffered)[: sniff.SNIFF_BYTES]
        if len(head) >= sniff.SNIFF_BYTES:
            break
    detected = sniff.sniff(head) if head else None
    if detected is None:
        raise MediaError(415, 41501, "unsupported media type", "bad_type")
    if detected.mime not in sniff.allowed_mimes(kind):
        raise MediaError(
            415, 41501, f"mime {detected.mime} not allowed for kind={kind}", "bad_type"
        )

    def _all_chunks():
        yield from buffered
        yield from stream

    stored = storage.store(media_dir(), _all_chunks(), detected.ext, datetime.now(UTC))
    validate_size(kind, stored.size)

    existing = db.execute(
        select(MediaAsset).where(
            MediaAsset.owner_id == user_id,
            MediaAsset.sha256 == stored.sha256,
            MediaAsset.status == MediaStatus.READY,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, True

    row = MediaAsset(
        public_id=secrets.token_hex(16),
        owner_id=user_id,
        kind=kind,
        mime_type=detected.mime,
        size_bytes=stored.size,
        sha256=stored.sha256,
        storage_path=stored.rel_path,
        width=w,
        height=h,
        duration_s=dur,
        status=MediaStatus.READY,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        # 并发同 owner 同内容：回读既有 ready 行（唯一键原子兜底）
        db.rollback()
        again = db.execute(
            select(MediaAsset).where(
                MediaAsset.owner_id == user_id,
                MediaAsset.sha256 == stored.sha256,
                MediaAsset.status == MediaStatus.READY,
            )
        ).scalar_one_or_none()
        if again is None:
            raise
        return again, True
    return row, False


def get_ready(db: Session, public_id: str) -> MediaAsset | None:
    return db.execute(
        select(MediaAsset).where(
            MediaAsset.public_id == public_id, MediaAsset.status == MediaStatus.READY
        )
    ).scalar_one_or_none()


def soft_delete(db: Session, *, user_id: int, public_id: str) -> bool:
    """软删（仅 owner）。物理文件**不动**——回收的三条件设计见 docs/48 B19（S4）。"""
    row = get_ready(db, public_id)
    if row is None:
        return False
    if row.owner_id != user_id:
        raise MediaError(403, 40302, "not the owner", "forbidden")
    db.execute(
        update(MediaAsset)
        .where(MediaAsset.id == row.id)
        .values(status=MediaStatus.DELETED, updated_at=datetime.now(UTC))
    )
    return True


def to_view(row: MediaAsset) -> dict[str, Any]:
    prefix = get_settings().media_url_prefix
    return {
        "id": row.public_id,
        "url": f"{prefix}{row.public_id}",
        "kind": row.kind,
        "mimeType": row.mime_type,
        "size": row.size_bytes,
        "width": row.width,
        "height": row.height,
        "durationS": float(row.duration_s) if row.duration_s is not None else None,
    }


def abs_path(row: MediaAsset) -> Path:
    return storage.resolve(media_dir(), row.storage_path)
