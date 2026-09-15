"""TTS 引擎生命周期测试（docs/44 P0-B；app/audio/base.py + app/audio/tts.py）。

覆盖：is_available 探测 / synthesize 单发重试后明确失败 / 超时不挂死 /
AzureNotWiredClient 显式未接线 / 工厂按 provider 分派。
"""

from __future__ import annotations

import asyncio
import types

import pytest
from app.audio.base import get_tts_client
from app.audio.tts import AzureNotWiredClient, EdgeTTSClient


async def test_edge_is_available_ready() -> None:
    ok, msg = EdgeTTSClient().is_available()
    assert ok is True
    assert msg == "ready"


async def test_synthesize_success(monkeypatch) -> None:
    c = EdgeTTSClient()

    async def ok(text, voice, rate):  # noqa: ARG001
        return b"RIFF__fake__"

    monkeypatch.setattr(c, "_stream_audio", ok)
    assert await c.synthesize("hi") == b"RIFF__fake__"


async def test_synthesize_retries_then_raises(monkeypatch) -> None:
    """失败一次重试一次，最终明确上抛（不再静默）。"""
    c = EdgeTTSClient()
    calls = 0

    async def boom(text, voice, rate):  # noqa: ARG001
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(c, "_stream_audio", boom)
    with pytest.raises(RuntimeError):
        await c.synthesize("hi")
    assert calls == 2  # 初试 + 单发重试


async def test_synthesize_timeout_then_raises(monkeypatch) -> None:
    """edge-tts 断网/挂死时按超时取消，不挂起整个事件循环。"""
    c = EdgeTTSClient(timeout_s=0.05)

    async def slow(text, voice, rate):  # noqa: ARG001
        await asyncio.sleep(60)
        return b"x"

    monkeypatch.setattr(c, "_stream_audio", slow)
    with pytest.raises(RuntimeError):
        await c.synthesize("hi")


async def test_azure_not_wired_is_available() -> None:
    ok, msg = AzureNotWiredClient().is_available()
    assert ok is False
    assert "未接线" in msg


async def test_azure_not_wired_synthesize_raises() -> None:
    with pytest.raises(RuntimeError):
        await AzureNotWiredClient().synthesize("hi")


def test_factory_default_edge(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.audio.base._settings",
        lambda: types.SimpleNamespace(
            testing=False, tts_provider="edge", tts_voice="v", tts_rate="+0%"
        ),
    )
    assert isinstance(get_tts_client(), EdgeTTSClient)


def test_factory_azure_unwired(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.audio.base._settings",
        lambda: types.SimpleNamespace(
            testing=False, tts_provider="azure", tts_voice="v", tts_rate="+0%"
        ),
    )
    c = get_tts_client()
    assert isinstance(c, AzureNotWiredClient)
    ok, _ = c.is_available()
    assert ok is False
