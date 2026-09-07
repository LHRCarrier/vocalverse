"""TTS 预合成缓存测试（docs/44 P1-B：键扩容 / TTL / 容量裁剪 / 统一出入口）。"""

from __future__ import annotations

import os
import time

from app.audio.stubs import FakeTTSClient
from app.audio.tts import (
    cache_is_fresh,
    prune_tts_cache,
    tts_cache_key,
    tts_synthesize_cached,
)


class _CountingTTS(FakeTTSClient):
    def __init__(self) -> None:
        self.calls = 0

    async def synthesize(
        self, text: str, voice: str = "en-US-JennyNeural", rate: str = "+0%"
    ) -> bytes:
        self.calls += 1
        return f"audio:{text}".encode()


# ---------------------------------------------------------------------------
# 缓存键（docs/44 P1-B：provider/引擎版本/voice/rate/文本 任一变化 → 键变化）
# ---------------------------------------------------------------------------


def test_cache_key_folds_all_dimensions() -> None:
    base = tts_cache_key("v1", "+0%", "Hello.")
    assert base != tts_cache_key("v2", "+0%", "Hello.")  # voice
    assert base != tts_cache_key("v1", "+10%", "Hello.")  # rate
    assert base != tts_cache_key("v1", "+0%", "Hello!")  # text
    assert base != tts_cache_key("v1", "+0%", "Hello.", provider="azure")  # provider
    assert base != tts_cache_key("v1", "+0%", "Hello.", engine_version="9.9.9")  # 引擎版本


def test_cache_key_is_deterministic() -> None:
    assert tts_cache_key("v1", "+0%", "Hi.") == tts_cache_key("v1", "+0%", "Hi.")


# ---------------------------------------------------------------------------
# TTL / 裁剪
# ---------------------------------------------------------------------------


def test_cache_is_fresh_by_mtime(tmp_path) -> None:
    p = tmp_path / "a.tts.mp3"
    p.write_bytes(b"x")
    assert cache_is_fresh(p, ttl_s=3600) is True
    assert cache_is_fresh(p, ttl_s=-1) is False
    assert cache_is_fresh(tmp_path / "missing.mp3", ttl_s=3600) is False
    # 过期：mtime 拨回 2 秒前
    old = time.time() - 2
    os.utime(p, (old, old))
    assert cache_is_fresh(p, ttl_s=1) is False
    assert cache_is_fresh(p, ttl_s=10) is True


def test_prune_removes_oldest_beyond_cap(tmp_path) -> None:
    for name, age in [("old.mp3", 100), ("mid.mp3", 50), ("new.mp3", 0)]:
        p = tmp_path / name
        p.write_bytes(b"x" * 100)
        t = time.time() - age
        os.utime(p, (t, t))
    # 300B > cap 150 → 从旧到新删至 ≤150（删 2 个剩 100B）；min_keep=1 允许裁剪
    removed = prune_tts_cache(tmp_path, max_bytes=150, min_keep=1)
    assert removed == 2
    assert not (tmp_path / "old.mp3").exists()
    assert not (tmp_path / "mid.mp3").exists()
    assert (tmp_path / "new.mp3").exists()


def test_prune_keeps_min_floor(tmp_path) -> None:
    for i in range(5):
        (tmp_path / f"{i}.mp3").write_bytes(b"x" * 100)
    # 300B 总数据、cap=1B，但 min_keep=5 → 全保留
    assert prune_tts_cache(tmp_path, max_bytes=1, min_keep=5) == 0


# ---------------------------------------------------------------------------
# 统一出入口 tts_synthesize_cached（docs/44 P1-B：热路径与 /tts 共用）
# ---------------------------------------------------------------------------


async def test_synthesize_cached_hit_does_not_touch_engine(tmp_path, monkeypatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "audio_dir", str(tmp_path))
    tts = _CountingTTS()
    first = await tts_synthesize_cached(tts, "Hi.", "v", "+0%", provider="edge")
    assert first == b"audio:Hi."
    assert tts.calls == 1
    second = await tts_synthesize_cached(tts, "Hi.", "v", "+0%", provider="edge")
    assert second == first
    assert tts.calls == 1  # 命中缓存，不触引擎


async def test_synthesize_cached_expires_by_ttl(tmp_path, monkeypatch) -> None:
    import os as _os

    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "audio_dir", str(tmp_path))
    tts = _CountingTTS()
    await tts_synthesize_cached(tts, "Hi.", "v", "+0%")
    # 拨旧 mtime 越过 TTL → 重新合成
    cache_dir = tmp_path / "cache" / "tts"
    for p in cache_dir.glob("*.mp3"):
        old = time.time() - settings.tts_cache_ttl_s - 1
        _os.utime(p, (old, old))
    await tts_synthesize_cached(tts, "Hi.", "v", "+0%")
    assert tts.calls == 2
