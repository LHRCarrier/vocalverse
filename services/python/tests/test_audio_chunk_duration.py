"""TTS 拼接增强测试（docs/44 P1-C / vtts-04）。

覆盖三件事：
1. ``mp3_duration_seconds`` —— 从 MP3 帧头估算时长（纯函数、绝不抛错：非 MP3/空/坏数据 → None）；
2. ``_tts_url_from_bytes`` 失败分支 —— 返回 (None, None) + 结构化日志「sentence no audio」
   （把「缺句静默」改成「缺句上报」，docs/44 P1-C）；成功分支返回 (url, duration)；
3. ``AudioChunk`` 契约 —— ``duration`` 可选字段：None 时序列化剔除（旧端兼容），
   有值时正常透传。
"""

from __future__ import annotations

import logging

from app.audio.stubs import FakeTTSClient
from app.audio.tts import mp3_duration_seconds
from app.practice import events as ev
from app.practice.orchestrator import _tts_url_from_bytes

# ── 测试用 MP3 合成帧（非产品代码）───────────────────────────────────────────────
# MPEG-2 Layer III, 24000 Hz, 48 kbps, mono（对齐 edge-tts 'audio-24khz-48kbitrate-mono-mp3'）：
#   byte1 = sync(3)=111, version=0b10(MPEG2), layer=0b01(L3), protection=1(无CRC) → 0xF3；
#   byte2 = bitrate_idx=6(48kbps, MPEG2 L3 表), sr_idx=1(24000Hz), padding=0, private=0 → 0x64；
#   帧长 L3 = 144 * 48000 / 24000 = 288 字节（≈6ms/帧）。
_MP3_FRAME = bytes([0xFF, 0xF3, 0x64, 0xC0]) + b"\x00" * 284
_FRAME_BYTES = 288
_FRAME_S = _FRAME_BYTES * 8 / 48000.0


def _frames(n: int) -> bytes:
    return _MP3_FRAME * n


def _id3v2(payload: bytes) -> bytes:
    """构造 ID3v2 头（synchsafe 尺寸）+ payload，验证时长估算能跳过标签。"""
    size = len(payload)
    ss = bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F])
    return b"ID3\x04\x00\x00" + ss + payload


# ---------------------------------------------------------------------------
# mp3_duration_seconds：纯函数
# ---------------------------------------------------------------------------


def test_duration_estimate_matches_frame_count() -> None:
    n = 800  # 230400 B → 38.4 s
    d = mp3_duration_seconds(_frames(n))
    assert d is not None
    assert abs(d - n * _FRAME_S) < 0.05


def test_duration_skips_id3v2_tag() -> None:
    d = mp3_duration_seconds(_id3v2(b"TIT2\x00\x00\x00\x00\x00\x00") + _frames(100))
    assert d is not None
    assert abs(d - 100 * _FRAME_S) < 0.01


def test_duration_returns_none_for_invalid_input() -> None:
    assert mp3_duration_seconds(b"") is None
    assert mp3_duration_seconds(b"garbage-not-mp3") is None
    assert mp3_duration_seconds(b"RIFF\x00\x00\x00\x00WAVEfmt ") is None
    assert mp3_duration_seconds(b"ID3") is None  # 头不完整
    assert mp3_duration_seconds(_id3v2(b"tag-only-payload")) is None  # 只有标签无帧


def test_duration_never_raises_on_random_bytes() -> None:
    for blob in (b"\x00" * 512, bytes(range(256)) * 2, b"\xff" * 64 + b"\x27"):
        assert mp3_duration_seconds(blob) is None


# ---------------------------------------------------------------------------
# AudioChunk 契约：duration 可选 + exclude_none 兼容
# ---------------------------------------------------------------------------


def test_audio_chunk_without_duration_serializes_backward_compatible() -> None:
    payload = ev.AudioChunk(url="/api/v1/audio/x.mp3").model_dump(exclude_none=True)
    assert payload == {"type": "audio_chunk", "url": "/api/v1/audio/x.mp3"}


def test_audio_chunk_with_duration_serializes_field() -> None:
    payload = ev.AudioChunk(url="/api/v1/audio/x.mp3", duration=1.25).model_dump(exclude_none=True)
    assert payload["duration"] == 1.25


# ---------------------------------------------------------------------------
# _tts_url_from_bytes：缺句上报 + 时长回传
# ---------------------------------------------------------------------------


class _RaisingTTS(FakeTTSClient):
    async def synthesize(
        self, text: str, voice: str = "en-US-JennyNeural", rate: str = "+0%"
    ) -> bytes:
        raise RuntimeError("edge-tts boom")


class _FramesTTS(FakeTTSClient):
    async def synthesize(
        self, text: str, voice: str = "en-US-JennyNeural", rate: str = "+0%"
    ) -> bytes:
        return _frames(100)


async def test_synthesis_failure_reports_and_returns_none_pair(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="vocalverse"):
        url, duration = await _tts_url_from_bytes(
            _RaisingTTS(), "Hello there.", "en-US-JennyNeural", "+0%"
        )
    assert url is None
    assert duration is None
    assert any("sentence no audio" in r.message for r in caplog.records)
    assert any("Hello there." in r.message for r in caplog.records)


async def test_synthesis_success_returns_url_and_duration() -> None:
    url, duration = await _tts_url_from_bytes(_FramesTTS(), "Hi.", "en-US-JennyNeural", "+0%")
    assert url is not None and url.startswith("/api/v1/audio/tts/")  # TTS 输出走 tts/ 前缀
    assert duration is not None
    assert abs(duration - 100 * _FRAME_S) < 0.01


# ---------------------------------------------------------------------------
# get_audio：tts/ 前缀免归属校验（2026-09-07 用户实测 403 回归锁）
# ---------------------------------------------------------------------------


def test_get_audio_tts_prefix_skips_ownership(client, monkeypatch) -> None:
    """AI TTS 输出（tts/ 前缀）：登录+未过期即放行，无需 attempt/message 引用。"""
    from pathlib import Path as _P

    from app.core.config import get_settings

    settings = get_settings()
    tts_dir = _P(settings.audio_dir) / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    name = "a" * 32 + ".mp3"
    (tts_dir / name).write_bytes(b"ID3fakemp3payload")

    resp = client.get(f"/api/v1/audio/tts/{name}", headers={"X-Test-User-Id": "1"})
    assert resp.status_code == 200, resp.text
    assert resp.content == b"ID3fakemp3payload"


def test_get_audio_plain_name_still_requires_ownership(client) -> None:
    """用户录音路径（无 tts/ 前缀）：无归属引用 → 40301（归属校验保持）。"""
    from pathlib import Path as _P

    from app.core.config import get_settings

    settings = get_settings()
    _P(settings.audio_dir).mkdir(parents=True, exist_ok=True)
    name = "b" * 32 + ".mp3"
    (_P(settings.audio_dir) / name).write_bytes(b"useraudio")
    resp = client.get(f"/api/v1/audio/{name}", headers={"X-Test-User-Id": "1"})
    assert resp.status_code == 403
