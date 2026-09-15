"""读书域 · 听书 TTS 缓存与 provider 链（docs/45 §5 · docs/46 B-3：按 provider 分目录）。

- 缓存目录：``data/audio/cache/tts/<provider>/<key>.tts.<mp3|wav>`` —— kitten 的 wav 与
  edge 的 mp3 **物理隔离**（同目录同名 .mp3 + 统一 audio/mpeg 会把 wav 播坏，B-3）；
- 内容寻址键复用 ``tts_cache_key``（provider|engine_version|voice|rate|text，docs/44 P1-B）；
- ``reading_tts_cached``：命中（新鲜）直接返回 (bytes, media_type, from_cache=True)，
  未命中 → 合成 + 原子写 + 容量裁剪（TTL/容量同 config 既有口径）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.audio.base import TTSClient
from app.audio.tts import (
    atomic_write_cache,
    cache_is_fresh,
    prune_tts_cache,
    tts_cache_key,
)
from app.core.config import get_settings

logger = logging.getLogger("vocalverse.reading.tts")

#: provider → (文件后缀, media_type)；未知 provider 按 mp3/mpeg 处理
_PROVIDER_FORMATS: dict[str, tuple[str, str]] = {
    "edge": ("mp3", "audio/mpeg"),
    "azure": ("mp3", "audio/mpeg"),
    "kitten": ("wav", "audio/wav"),
}


def provider_format(provider: str) -> tuple[str, str]:
    ext, media = _PROVIDER_FORMATS.get(provider, ("mp3", "audio/mpeg"))
    return ext, media


def reading_tts_cache_path(provider: str, voice: str, rate: str, text: str) -> Path:
    settings = get_settings()
    ext, _ = provider_format(provider)
    cache_dir = Path(settings.audio_dir) / "cache" / "tts" / provider
    key = tts_cache_key(voice, rate, text, provider=provider)
    return cache_dir / f"{key}.tts.{ext}"


async def reading_tts_cached(
    tts: TTSClient, text: str, voice: str, rate: str, *, provider: str
) -> tuple[bytes, str, bool]:
    """听书句合成统一出入口：命中缓存 (bytes, media_type, True)；否则合成并写缓存。

    调用方（路由）决定配额：**命中不扣 reading_tts 桶**（docs/46 B-4：只扣真实合成）。
    """
    settings = get_settings()
    path = reading_tts_cache_path(provider, voice, rate, text)
    if path.exists() and cache_is_fresh(path, settings.tts_cache_ttl_s):
        return path.read_bytes(), provider_format(provider)[1], True
    data = await tts.synthesize(text, voice=voice, rate=rate)
    atomic_write_cache(path, data)
    prune_tts_cache(path.parent, settings.tts_cache_max_mb * 1024 * 1024)
    return data, provider_format(provider)[1], False


__all__ = ["reading_tts_cached", "reading_tts_cache_path", "provider_format"]
