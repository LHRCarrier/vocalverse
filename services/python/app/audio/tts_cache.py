"""TTS 预合成缓存 —— **全站唯一出入口**（docs/44 P1-B + docs/46 B-3 合并版）。

重构前这里有**两套并行实现**，且都不完整：

| 旧实现 | 命中判定 | 目录 | 扩展名 / Content-Type |
|---|---|---|---|
| ``tts.tts_synthesize_cached`` | TTL | ``cache/tts/<key>.tts.mp3`` | 硬编码 mp3 / audio-mpeg |
| ``reading.tts_cache.reading_tts_cached`` | TTL | ``cache/tts/<provider>/…`` | 按 provider |

于是「练习热路径 + ``/tts`` 裸端点」用前者、「听书」用后者：本地 WAV 引擎一旦被
热路径选中，音频会被写成 ``.mp3`` 且回放标 ``audio/mpeg`` —— 这正是 docs/46 B-3
已经踩过的「wav 被当 mp3 播坏」。本模块把两套合成一套，并保持两条调用语义：

- :func:`tts_synthesize_cached` → ``bytes``（热路径 / ``/tts``，失败上抛由调用方降级）；
- :func:`tts_synth_cached_detailed` → ``(bytes, media_type, from_cache)``（听书域需要
  媒体类型与「是否命中」来决定扣不扣配额）。

缓存键维度：``provider | engine_version | voice | rate | 文本``（docs/44 P1-B）——
换引擎/升版本/换音色/换语速/切 provider 都不命中陈旧音频。
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import logging
import os
import time as _time
from pathlib import Path

from app.audio.base import TTSClient
from app.audio.registry import tts_format

logger = logging.getLogger("vocalverse.tts.cache")

#: provider → 提供引擎实现的分发包名（进缓存键的「引擎版本」维度）
_ENGINE_PACKAGES: dict[str, str] = {
    "edge": "edge-tts",
    "azure": "azure-cognitiveservices-speech",
    "kitten": "kittentts",
    "omnivoice": "omnivoice",
}


@functools.lru_cache(maxsize=8)
def engine_version(provider: str) -> str:
    """引擎分发包版本（缓存：升级引擎后旧音频失效重取）；未知 → ``unknown``。"""
    pkg = _ENGINE_PACKAGES.get((provider or "").strip().lower())
    if not pkg:
        return "unknown"
    try:
        from importlib.metadata import version as _pkg_version

        return _pkg_version(pkg)
    except Exception:  # pragma: no cover - 环境未装（轻量测试走 Fake）
        return "unknown"


def provider_of(tts: object) -> str:
    """从客户端实例取 provider 名（**读属性，不 isinstance 反推**）。

    旧实现 ``"kitten" if isinstance(tts, KittenTTSClient) else "edge"`` 在新增引擎时
    必然漏判，并把缓存目录/扩展名一起带错。
    """
    name = getattr(tts, "provider_id", "") or ""
    return name.strip().lower() or "edge"


def tts_cache_key(
    voice: str,
    rate: str,
    text: str,
    *,
    provider: str = "edge",
    engine_version: str | None = None,
) -> str:
    """缓存键：provider / 引擎版本 / voice / rate / 文本（docs/44 P1-B）。

    任一维度变化 → 键变化 → 重取：换音色、升引擎版本、切 provider 都不命中陈旧音频；
    旧键缓存随 TTL/容量裁剪自然淘汰。
    """
    ver = engine_version or globals()["engine_version"](provider)
    return hashlib.sha1(f"{provider}|{ver}|{voice}|{rate}|{text.strip()}".encode()).hexdigest()[:24]


def tts_cache_path(provider: str, voice: str, rate: str, text: str) -> Path:
    """``<audio_dir>/cache/tts/<provider>/<key>.tts.<ext>``（按 provider 物理隔离）。"""
    from app.core.config import get_settings

    ext, _ = tts_format(provider)
    cache_dir = Path(get_settings().audio_dir) / "cache" / "tts" / provider
    return cache_dir / f"{tts_cache_key(voice, rate, text, provider=provider)}.tts.{ext}"


def cache_is_fresh(path: Path, ttl_s: int) -> bool:
    """缓存是否新鲜（存在且 mtime 距今 ≤ TTL；docs/44 P1-B）。"""
    if ttl_s <= 0 or not path.exists():
        return False
    try:
        return _time.time() - os.path.getmtime(path) <= ttl_s
    except OSError:  # pragma: no cover - 竞态删除
        return False


def atomic_write_cache(path: Path, data: bytes) -> None:
    """原子写缓存（tmp + os.replace）：并发同句合成/半文件都可防 —— 不产生脏缓存。

    Windows/Linux 均原子；同 key 同参数 → 内容一致，重复覆盖无副作用（docs/19 P0-5）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def prune_tts_cache(cache_dir: Path, max_bytes: int, *, min_keep: int = 16) -> int:
    """容量裁剪：总大小超限时按 mtime 从旧到新删除（docs/44 P1-B）。

    至少保留 ``min_keep`` 个新文件（防高频句被误删互踢）；删除失败静默继续；
    返回删除的文件数（0 = 未裁剪 / 无法统计）。
    """
    files: list[tuple[float, Path]] = []
    total = 0
    try:
        for p in cache_dir.iterdir():
            if not p.is_file():
                continue
            try:
                size = p.stat().st_size
            except OSError:  # pragma: no cover - 竞态删除
                continue
            files.append((_time.time() - p.stat().st_mtime, p))
            total += size
    except OSError:
        return 0
    if total <= max_bytes or len(files) <= min_keep:
        return 0
    removed = 0
    for _, p in sorted(files, key=lambda t: (-t[0], t[1])):  # 最旧在前
        if total <= max_bytes or len(files) - removed <= min_keep:
            break
        try:
            sz = p.stat().st_size
            p.unlink(missing_ok=True)
            total -= sz
            removed += 1
        except OSError:  # pragma: no cover - 竞态删除
            continue
    return removed


async def tts_synth_cached_detailed(
    tts: TTSClient,
    text: str,
    voice: str,
    rate: str,
    *,
    provider: str | None = None,
) -> tuple[bytes, str, bool]:
    """统一出入口（详细版）：``(音频字节, media_type, 是否命中缓存)``。

    - provider 默认取 ``tts.provider_id``（不再由调用方传 ``settings`` 里那个可能
      与实际客户端不一致的值）；
    - 命中（新鲜）→ 不触碰引擎；未命中 → 合成 + 原子写 + 容量裁剪；
    - 失败上抛（调用方决定降级：热路径记「sentence no audio」、``/tts`` 返回 502、
      听书逐句容忍并计数）。
    """
    from app.core.config import get_settings

    settings = get_settings()
    name = (provider or provider_of(tts)).strip().lower()
    _, media_type = tts_format(name)
    path = tts_cache_path(name, voice, rate, text)
    if path.exists() and cache_is_fresh(path, settings.tts_cache_ttl_s):
        return path.read_bytes(), media_type, True
    data = await tts.synthesize(text, voice=voice, rate=rate)
    atomic_write_cache(path, data)
    prune_tts_cache(path.parent, settings.tts_cache_max_mb * 1024 * 1024)
    return data, media_type, False


async def tts_synthesize_cached(
    tts: TTSClient,
    text: str,
    voice: str,
    rate: str,
    *,
    provider: str | None = None,
) -> bytes:
    """统一出入口（热路径/``/tts`` 用）：只返回音频字节。"""
    data, _, _ = await tts_synth_cached_detailed(tts, text, voice, rate, provider=provider)
    return data


async def warm_tts_cache(
    tts: TTSClient,
    texts: list[str],
    voice: str,
    rate: str,
    *,
    provider: str | None = None,
    max_concurrency: int = 4,
) -> int:
    """预合成预热（docs/06 §8「开场/常用句预合成」兑现，2026-09-09）。

    - 只补缓存：命中（已预热/已请求过）直接跳过，不触碰引擎；
    - 文本去重（同 key 只预热一次）+ 并发限速（edge-tts 网络往返 ~1.3s/句，
      串行 35 句 ≈45s —— 限速 4 并发 ≈11s 完成）；
    - 单句失败仅日志（预热不阻塞调用方、不上抛）；
    - 返回成功句数（含已命中跳过——调用方只关心「缓存就绪数」）。
    """
    name = (provider or provider_of(tts)).strip().lower()
    seen: set[str] = set()
    unique: list[str] = []
    for text in texts:
        if not text or not text.strip():
            continue
        key = tts_cache_key(voice, rate, text, provider=name)
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)

    sem = asyncio.Semaphore(max_concurrency)

    async def _one(text: str) -> bool:
        async with sem:
            try:
                await tts_synthesize_cached(tts, text, voice, rate, provider=name)
                return True
            except Exception:
                logger.warning("tts warm failed: %r", text[:40], exc_info=True)
                return False

    results = await asyncio.gather(*(_one(t) for t in unique))
    return sum(1 for ok in results if ok)


__all__ = [
    "atomic_write_cache",
    "cache_is_fresh",
    "engine_version",
    "provider_of",
    "prune_tts_cache",
    "tts_cache_key",
    "tts_cache_path",
    "tts_synth_cached_detailed",
    "tts_synthesize_cached",
    "warm_tts_cache",
]
