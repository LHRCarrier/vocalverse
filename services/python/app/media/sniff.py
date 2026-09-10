"""媒体类型嗅探（magic number，docs/47 §4.1）。

**不信任客户端**：`Content-Type` 与文件名都是用户可控的（`x.php.jpg`、`image/png` 配 `.mp4`），
一律按文件头字节判定真实类型；白名单外的类型直接 41501。

零新依赖：手写头部判定（引入 python-magic 需要 libmagic 动态库，容器/Windows 都要额外安装）。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 头部嗅探需要读取的字节数（WebM 的 DocType 出现在 EBML 头附近，4KB 足够）
SNIFF_BYTES = 4096

#: 允许的 (mime, ext) 组合（kind → 白名单）
IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
VIDEO_TYPES: dict[str, str] = {
    "video/mp4": "mp4",
    "video/webm": "webm",
}


@dataclass(frozen=True)
class SniffResult:
    mime: str
    ext: str


def _is_mp4(head: bytes) -> bool:
    """ISO BMFF：偏移 4..8 为 'ftyp'（mp4/m4v/mov 共用；brand 不一，统称 mp4）。"""
    return len(head) >= 12 and head[4:8] == b"ftyp"


def _is_webm(head: bytes) -> bool:
    """EBML 头 + DocType 含 'webm'（mkv 同样是 EBML，但 DocType 是 'matroska' → 拒绝）。"""
    return head[:4] == b"\x1a\x45\xdf\xa3" and b"webm" in head[:1024]


def sniff(head: bytes) -> SniffResult | None:
    """按头部字节判定媒体类型；未命中白名单返回 None。"""
    if head.startswith(b"\xff\xd8\xff"):
        return SniffResult("image/jpeg", "jpg")
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return SniffResult("image/png", "png")
    if head.startswith((b"GIF87a", b"GIF89a")):
        return SniffResult("image/gif", "gif")
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return SniffResult("image/webp", "webp")
    if _is_mp4(head):
        return SniffResult("video/mp4", "mp4")
    if _is_webm(head):
        return SniffResult("video/webm", "webm")
    return None


def allowed_mimes(kind: str) -> dict[str, str]:
    """该 kind 允许的 mime → 扩展名表。"""
    if kind == "video":
        return VIDEO_TYPES
    return IMAGE_TYPES  # image / avatar 共用图片白名单
