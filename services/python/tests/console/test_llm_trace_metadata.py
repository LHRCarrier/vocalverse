"""LLM 客户端 → trace 回填测试（P0-1：``ttft_ms`` / ``finish_reason`` 必须有真数据源）。

背景：``llm.ttft_ms.p95``、trace 的 ``ttft_ms`` 与内置预警规则 ``llm_ttft_slow``
此前**没有任何数据源** —— ``stream_rich`` 既不记首 token 时刻，也不读 ``finish_reason``。
一个"永远为空/恒 0"的指标比没有更糟：控制台会显示一条平线并被当成"健康"。

本文件锁定三件事：
1. 流式调用能测出 TTFT（首 delta 的时刻）并从末块解析 ``finish_reason``；
2. 非流式调用能拿到 ``finish_reason`` 与 token（TTFT 保持 None —— 非流式没有"首 token"语义，
   填 0 会把 p95 污染成假值）；
3. **事件形状不变**：仍然只有 ``("delta", …)`` / ``("usage", …)``
   （``turn_runner`` 与既有测试依赖该契约）。
"""

from __future__ import annotations

import json

import httpx
import pytest
from app.audio.llm import DeepSeekLLMClient
from app.console.ops.metrics import get_registry, reset_registry_for_tests
from app.console.trace.recorder import span


def _stream_body() -> str:
    chunks = [
        {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": " there"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 7}},
    ]
    lines = [f"data: {json.dumps(c)}" for c in chunks]
    lines.append("data: [DONE]")
    return "\n\n".join(lines) + "\n\n"


def _client(handler) -> DeepSeekLLMClient:
    llm = DeepSeekLLMClient(api_key="k", base_url="https://example.invalid")
    llm._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return llm


@pytest.mark.asyncio
async def test_stream_records_ttft_finish_reason_and_tokens() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=_stream_body().encode(), headers={"content-type": "text/event-stream"}
        )

    llm = _client(handler)
    events: list[tuple[str, object]] = []
    with span("LLM") as s:
        async for kind, payload in llm.stream_rich([{"role": "user", "content": "hi"}]):
            events.append((kind, payload))

    # 1) 事件形状不变（只有 delta / usage）
    assert [k for k, _ in events] == ["delta", "delta", "usage"]
    # 2) TTFT / finish_reason / token 全部落到了 span 上
    assert s is not None
    assert s.ttft_ms is not None and s.ttft_ms >= 0
    assert s.finish_reason == "stop"
    assert (s.prompt_tokens, s.completion_tokens) == (11, 7)
    assert s.model == "deepseek-chat"


@pytest.mark.asyncio
async def test_non_stream_records_finish_reason_but_no_ttft() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "deepseek-chat",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    llm = _client(handler)
    with span("LLM") as s:
        content, usage = await llm.chat_with_usage([{"role": "user", "content": "hi"}])

    assert content == "ok" and usage is not None
    assert s is not None
    assert s.finish_reason == "length"
    assert s.prompt_tokens == 3
    # 非流式没有首 token 语义：留 None，绝不能填 0（否则 p95 被污染）
    assert s.ttft_ms is None


@pytest.mark.asyncio
async def test_http_error_records_status_and_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    llm = _client(handler)
    with pytest.raises(httpx.HTTPStatusError), span("LLM") as s:
        await llm.chat([{"role": "user", "content": "hi"}])

    assert s is not None
    assert s.status == "error"
    assert s.error_code == "429"
    assert s.attrs.get("http_status") == 429
    assert "rate limited" in str(s.attrs.get("error_body"))


@pytest.mark.asyncio
async def test_trace_metrics_receive_ttft_histogram() -> None:
    """``llm.ttft_ms`` 直方图必须真的有样本（否则 llm.ttft_ms.p95 永远是空线）。"""
    from app.console.trace.recorder import trace

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_stream_body().encode())

    llm = _client(handler)
    reset_registry_for_tests()
    with trace(kind="turn"), span("LLM"):
        async for _ in llm.stream_rich([{"role": "user", "content": "hi"}]):
            pass

    drained = {item["metric"]: item["series"] for item in get_registry().drain()}
    assert "llm.ttft_ms" in drained
    assert drained["llm.ttft_ms"].count == 1
    assert drained["llm.call.count"].total == 1
    assert drained["llm.tokens.prompt"].total == 11
