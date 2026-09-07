"""语音链路加固回归（性能拷问×审查 剩余队列：vasr-01/05/07/09/10 · va-01/03/08 · py-05/10）。

覆盖：ffmpeg 时长解析纯函数 / ASR VAD+no_speech 判别 / 模型单次加载锁 / ISE 收帧超时 /
LLM 客户端缓存复用 / 评分客户端生产 fail-fast 分级。
"""

from __future__ import annotations

import asyncio
import sys
import threading
import types

import pytest
from app.audio import asr as asr_mod
from app.audio.ffmpeg_utils import parse_duration_from_stderr
from app.audio.stubs import FakeScorerClient, UnavailableScorerClient

# ---------------------------------------------------------------------------
# va-01 · ffmpeg 时长解析（纯函数）
# ---------------------------------------------------------------------------


def test_parse_duration_from_stderr_hhmmss() -> None:
    assert parse_duration_from_stderr("  Duration: 00:01:23.45, start: 0.000000") == pytest.approx(
        83.45
    )
    assert parse_duration_from_stderr("  Duration: 00:00:15.00") == pytest.approx(15.0)
    assert parse_duration_from_stderr("garbage output") is None
    assert parse_duration_from_stderr("") is None


# ---------------------------------------------------------------------------
# vasr-07 / vasr-10 · ASR：VAD 参数 + no_speech 判别
# ---------------------------------------------------------------------------


def _install_fake_whisper(monkeypatch, model_factory) -> None:
    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = model_factory
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)


def test_transcribe_enables_vad_and_flags_no_speech(monkeypatch) -> None:
    captured: dict = {}

    class _Info:
        language = "en"
        language_probability = 0.9
        duration = 1.5
        no_speech_prob = 0.95

    class _Seg:
        text = ""
        words = None
        start = 0.0
        end = 1.0

    class _Model:
        def __init__(self, *a, **k):
            pass

        def transcribe(
            self, path, language=None, beam_size=None, word_timestamps=None, vad_filter=None
        ):
            captured["vad"] = vad_filter
            captured["word_ts"] = word_timestamps
            return iter([_Seg()]), _Info()

    _install_fake_whisper(monkeypatch, _Model)
    res = asr_mod.FasterWhisperClient().transcribe_sync("x.wav")
    assert captured["vad"] is True  # Silero VAD 一行兑现（docs/06 §8:116 承诺）
    assert captured["word_ts"] is True  # 词级时间戳保留
    assert res.no_speech is True  # no_speech_prob>0.7 且空转写 → 判别位


def test_transcribe_no_speech_false_when_confident_speech(monkeypatch) -> None:
    class _Info:
        language = "en"
        language_probability = 0.9
        duration = 1.5
        no_speech_prob = 0.05

    class _Seg:
        text = "Hello there"
        words = None
        start = 0.0
        end = 1.0

    class _Model:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, path, **kw):
            return iter([_Seg()]), _Info()

    _install_fake_whisper(monkeypatch, _Model)
    res = asr_mod.FasterWhisperClient().transcribe_sync("x.wav")
    assert res.no_speech is False


# ---------------------------------------------------------------------------
# vasr-09 · 模型单次加载锁（并发首请求只加载一次）
# ---------------------------------------------------------------------------


def test_warm_single_load_under_concurrency(monkeypatch) -> None:
    instantiations = 0

    class _Model:
        def __init__(self, *a, **k):
            nonlocal instantiations
            instantiations += 1

    _install_fake_whisper(monkeypatch, _Model)
    client = asr_mod.FasterWhisperClient()
    errors: list[Exception] = []

    def run():
        try:
            client.warm()
        except Exception as exc:  # pragma: no cover - 失败即测试失败
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert instantiations == 1  # 双重检查锁：并发首次只有一次加载


# ---------------------------------------------------------------------------
# va-03 · ISE 收帧超时（挂起 → 及早失败，不挂流）
# ---------------------------------------------------------------------------


async def test_ise_recv_result_times_out_on_hung_ws() -> None:
    from app.audio.ise import _recv_result

    class _HungWS:
        async def recv(self):
            await asyncio.sleep(60)  # 模拟服务端不回帧

    with pytest.raises(RuntimeError, match="收帧超时"):
        await _recv_result(_HungWS(), recv_timeout_s=0.05)


async def test_ise_recv_result_parses_status_2_frame() -> None:
    import base64
    import json

    from app.audio.ise import _recv_result

    class _OKWS:
        async def recv(self):
            return json.dumps(
                {"code": 0, "data": {"status": 2, "data": base64.b64encode(b"<xml/>").decode()}}
            )

    payload = await _recv_result(_OKWS())
    assert payload == b"<xml/>"


# ---------------------------------------------------------------------------
# py-05 · LLM 客户端缓存（连接池常驻前提：同配置同实例）
# ---------------------------------------------------------------------------


async def test_get_llm_client_cached_by_config(monkeypatch) -> None:
    from app.audio import base as base_mod

    settings = base_mod._settings()
    monkeypatch.setattr(settings, "testing", False)
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    a = base_mod.get_llm_client()
    b = base_mod.get_llm_client()
    assert a is b  # 同配置 → 同一实例（httpx 连接池复用）
    from app.audio.base import _LLM_CLIENT_CACHE

    c = base_mod.get_llm_client()
    assert c is a
    assert _LLM_CLIENT_CACHE is not None


# ---------------------------------------------------------------------------
# va-08 · 评分客户端：生产缺 Key fail-fast / 开发演示 Fake+标识
# ---------------------------------------------------------------------------


def test_get_scorer_client_production_missing_keys_fails_fast(monkeypatch) -> None:
    from app.audio import base as base_mod

    settings = base_mod._settings()
    monkeypatch.setattr(settings, "testing", False)
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "ise_app_id", "")
    monkeypatch.setattr(settings, "ise_api_key", "")
    client = base_mod.get_scorer_client()
    assert isinstance(client, UnavailableScorerClient)


async def test_unavailable_scorer_raises_clear_message() -> None:
    c = UnavailableScorerClient("ISE not configured (app_env=production)")
    with pytest.raises(RuntimeError, match="scorer unavailable"):
        await c.score(b"x", "reference")


def test_get_scorer_client_development_missing_keys_uses_fake_with_marker(monkeypatch) -> None:
    from app.audio import base as base_mod

    settings = base_mod._settings()
    monkeypatch.setattr(settings, "testing", False)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "ise_app_id", "")
    monkeypatch.setattr(settings, "ise_api_key", "")
    client = base_mod.get_scorer_client()
    assert isinstance(client, FakeScorerClient)
    assert client.is_fake is True  # va-08 显式标识：假分在链路可被识别
