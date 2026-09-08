"""py-08：非 testing 真实路径矩阵——mock 外部依赖（edge_tts 模块 / httpx transport），
直测真实客户端代码（_stream_audio / stream_rich / chat_with_usage），而非 Fake 打桩；
另加 /turns 编排真实路径一门（mock 引擎注入、真编排 run_turn）。

模板参照 tests/rec/test_recommend_redis_cache.py：依赖注入 + monkeypatch，测真实实现。
"""

from __future__ import annotations

import asyncio
import json
import sys
import types

import httpx
import pytest
from app.audio.base import ASRClient, ASRResult, LLMClient, ScorerClient, ScoreResult, TTSClient
from app.audio.llm import DeepSeekLLMClient
from app.audio.tts import EdgeTTSClient, synthesize_concurrent
from app.practice.meta import render_meta
from app.practice.orchestrator import PracticeOrchestrator

FAKE_AUDIO = b"fake-audio-bytes" * 128

# ---------------------------------------------------------------------------
# Part 1：EdgeTTSClient 真实路径（mock edge_tts 模块，直测 _stream_audio）
# ---------------------------------------------------------------------------


def _fake_edge_tts(stream_chunks: list[dict], record: list | None = None) -> types.ModuleType:
    mod = types.ModuleType("edge_tts")

    class Communicate:
        def __init__(self, text: str, voice: str = "", rate: str = ""):
            self.text = text
            self.voice = voice
            self.rate = rate
            if record is not None:
                record.append((text, voice, rate))

        async def stream(self):
            for c in stream_chunks:
                yield c

    mod.Communicate = Communicate
    return mod


async def test_edge_stream_audio_collects_chunks_and_passes_params(monkeypatch) -> None:
    """真实 _stream_audio：只收 audio 块、忽略元数据块；voice/rate 透传。"""
    mod = _fake_edge_tts(
        [
            {"type": "audio", "data": b"AAA"},
            {"type": "WordBoundary", "offset": 0, "duration": 10},
            {"type": "audio", "data": b"BBB"},
        ]
    )
    monkeypatch.setitem(sys.modules, "edge_tts", mod)
    c = EdgeTTSClient(voice="en-US-JennyNeural", rate="+5%")
    assert await c._stream_audio("hello", "en-US-AriaNeural", "-10%") == b"AAABBB"


async def test_edge_stream_empty_audio_raises(monkeypatch) -> None:
    """真实 _stream_audio：无 audio 块 → 明确上抛（不静默返回空）。"""
    mod = _fake_edge_tts([{"type": "WordBoundary", "offset": 0}])
    monkeypatch.setitem(sys.modules, "edge_tts", mod)
    with pytest.raises(RuntimeError):
        await EdgeTTSClient()._stream_audio("hi", "", "")


async def test_edge_stream_voice_rate_fallbacks(monkeypatch) -> None:
    """voice/rate 空值时回退到构造参数（真实 _stream_audio 的 or 链）。"""
    calls: list = []
    mod = _fake_edge_tts([{"type": "audio", "data": b"x"}], record=calls)
    monkeypatch.setitem(sys.modules, "edge_tts", mod)
    c = EdgeTTSClient(voice="en-US-JennyNeural", rate="+15%")
    await c._stream_audio("hi", "", "")
    assert calls[0][1:] == ("en-US-JennyNeural", "+15%")


async def test_edge_synthesize_concurrent(monkeypatch) -> None:
    """synthesize_concurrent：多句并发合成全部成功（真实客户端 + mock 引擎）。"""
    calls: list = []
    mod = _fake_edge_tts([{"type": "audio", "data": b"x"}], record=calls)
    monkeypatch.setitem(sys.modules, "edge_tts", mod)
    c = EdgeTTSClient()
    out = await synthesize_concurrent(c, ["a", "b", "c"])
    assert out == [b"x", b"x", b"x"]
    assert sorted(t for t, _, _ in calls) == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Part 2：DeepSeekLLMClient 真实路径（mock httpx transport，直测请求/解析）
# ---------------------------------------------------------------------------


def _mk_llm(handler) -> DeepSeekLLMClient:
    c = DeepSeekLLMClient(api_key="test-key", base_url="https://api.deepseek.com", model="mock")
    c._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), timeout=httpx.Timeout(5.0)
    )
    return c


def _chat_handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    assert payload["model"] == "mock"
    if any("json" in (m.get("content") or "").lower() for m in payload["messages"]):
        assert payload.get("response_format") == {"type": "json_object"}
    return httpx.Response(
        200,
        json={
            "model": "mock",
            "choices": [{"message": {"content": "Hello!"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


def _stream_handler(request: httpx.Request) -> httpx.Response:
    body = (
        'data: {"choices":[{"delta":{"content":"Hello "}}]}\n'
        'data: {"choices":[{"delta":{"content":"world"}}]}\n'
        'data: {"usage":{"prompt_tokens":5,"completion_tokens":3}}\n'
        "data: [DONE]\n"
    )
    return httpx.Response(200, text=body)


async def test_llm_chat_with_usage_parses() -> None:
    c = _mk_llm(_chat_handler)
    content, usage = await c.chat_with_usage(
        [{"role": "user", "content": "hi"}], temperature=0.3, max_tokens=32
    )
    assert content == "Hello!"
    assert usage == {"model": "mock", "prompt_tokens": 10, "completion_tokens": 5}


async def test_llm_chat_json_format_when_prompt_has_json() -> None:
    c = _mk_llm(_chat_handler)
    await c.chat_with_usage([{"role": "user", "content": "Return json for the report"}])
    # 断言在 handler 内完成（response_format 存在）


async def test_llm_stream_rich_deltas_and_usage() -> None:
    c = _mk_llm(_stream_handler)
    events = [e async for e in c.stream_rich([{"role": "user", "content": "hi"}])]
    deltas = "".join(p for k, p in events if k == "delta")
    usage = [p for k, p in events if k == "usage"]
    assert deltas == "Hello world"
    assert usage and usage[0]["prompt_tokens"] == 5


async def test_llm_stream_rich_concurrent() -> None:
    c = _mk_llm(_stream_handler)

    async def collect() -> str:
        events = [e async for e in c.stream_rich([{"role": "user", "content": "hi"}])]
        return "".join(p for k, p in events if k == "delta")

    r1, r2 = await asyncio.gather(collect(), collect())
    assert r1 == r2 == "Hello world"


def _stream_bad_handler(request: httpx.Request) -> httpx.Response:
    body = 'data: not-json\ndata: {"choices":[{"delta":{"content":"ok"}}]}\ndata: [DONE]\n'
    return httpx.Response(200, text=body)


async def test_llm_stream_skips_malformed_lines() -> None:
    c = _mk_llm(_stream_bad_handler)
    deltas = "".join(p for k, p in [e async for e in c.stream_rich([])] if k == "delta")
    assert deltas == "ok"


# ---------------------------------------------------------------------------
# Part 3：/turns 编排真实路径一门（mock 引擎注入，真编排 run_turn）
# ---------------------------------------------------------------------------


class MockASR(ASRClient):
    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> ASRResult:
        return ASRResult(
            text="I'd like a coffee, please.",
            language=language,
            confidence=0.99,
            words=[
                {"word": w, "start": 0.1 * i, "end": 0.1 * i + 0.2, "probability": 0.99}
                for i, w in enumerate(["I'd", "like", "a", "coffee", "please"])
            ],
            duration=3.2,
        )


class MockLLM(LLMClient):
    async def chat(self, messages, temperature=0.7, max_tokens=512) -> str:  # noqa: ARG002
        return "Here is your coffee!"

    async def stream(self, messages, temperature=0.6, max_tokens=512):
        async for kind, payload in self.stream_rich(messages, temperature, max_tokens):
            if kind == "delta":
                yield payload

    async def stream_rich(self, messages, temperature=0.6, max_tokens=512):
        for chunk in ["Sure! Here is ", "your coffee, please. "]:
            yield ("delta", chunk)
        yield ("usage", {"model": "mock", "prompt_tokens": 10, "completion_tokens": 6})
        yield (
            "delta",
            render_meta(
                grammar={"score": 90, "errors": []},
                coach_note="Nice and clear!",
                corpus_hits=[{"phrase": "I'd like a coffee, please", "state": "ok"}],
                difficulty_delta=0,
                conclude=False,
            ),
        )


class MockTTS(TTSClient):
    async def synthesize(self, text, voice="en-US-JennyNeural", rate="+0%") -> bytes:  # noqa: ARG002
        return b"RIFF__mock_tts__"


class MockScorer(ScorerClient):
    async def score(self, audio_bytes, reference, language="en") -> ScoreResult:  # noqa: ARG002
        return ScoreResult(overall=88.0, pronunciation=90.0, fluency=86.0, grammar=85.0)


def test_turns_orchestration_real_path_mock_engines(client, auth_headers, monkeypatch) -> None:
    """mock 引擎注入 + 真编排（run_turn：DB/state/SSE/命中/TTS/turn_end 全真）。"""
    from app.db import get_session_factory
    from app.models import Scenario

    db = get_session_factory()()
    scenario = Scenario(
        title="py08-cafe",
        scene_type="cafe",
        difficulty=1,
        system_prompt="You are Bella, a friendly barista. Keep sentences short.",
        opening_line="Hi there! Welcome to Moonbean.",
        target_corpus="I'd like a coffee, please.|请给我来杯咖啡\nHow much is it?|多少钱",
        interest_tags=[],
        status="published",
    )
    db.add(scenario)
    db.commit()
    sid = scenario.id
    db.close()

    monkeypatch.setattr(
        "app.api.routes.practice.get_orchestrator",
        lambda: PracticeOrchestrator(
            asr=MockASR(), scorer=MockScorer(), llm=MockLLM(), tts=MockTTS()
        ),
    )

    resp = client.post(
        "/api/v1/sessions", json={"kind": "dialog", "scenario_id": sid}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["data"]["id"]

    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    evs = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
    types = [e["type"] for e in evs]

    # 编排事件序列：mock ASR 转写 → 流式字幕 → 音频块 → meta → turn_end
    assert "user_transcript" in types
    assert "turn_start" in types
    assert "text_delta" in types
    assert "audio_chunk" in types
    assert "meta_block" in types
    assert "turn_end" in types

    ut = [e for e in evs if e["type"] == "user_transcript"][0]
    assert "I'd like a coffee" in ut["text"]
    meta = [e for e in evs if e["type"] == "meta_block"][0]
    assert meta.get("coach_note") == "Nice and clear!"
    assert meta.get("corpus_hits")  # 规则命中（transcript 含语料句）
    end = [e for e in evs if e["type"] == "turn_end"][0]
    assert end["expected_turn"] == 1
