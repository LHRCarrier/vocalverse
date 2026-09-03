"""DeepSeek LLM 客户端（OpenAI 兼容 /chat/completions）。

- chat：非流式（知识包生成/报告生成等一次性 JSON）；
- chat_with_usage：同 chat，额外返回 usage（用量记账 docs/26 §10.3②）；
- stream：流式（回复文本 + 尾部 [-META-] 标记块，docs/14 §3.4）；
- stream_rich：流式并产出 ("delta", text) / ("usage", usage) 事件（turn_runner 用量累积）；
- json 输出用 response_format=json_object（prompt 必须含 "json" 字样，POC-2 验证项）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.audio.base import LLMClient


class DeepSeekLLMClient(LLMClient):
    def __init__(
        self, api_key: str, base_url: str = "https://api.deepseek.com", model: str = "deepseek-chat"
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _usage_of(data: dict, model: str) -> dict | None:
        u = data.get("usage")
        if not u:
            return None
        return {
            "model": data.get("model") or model,
            "prompt_tokens": int(u.get("prompt_tokens") or 0),
            "completion_tokens": int(u.get("completion_tokens") or 0),
        }

    async def chat_with_usage(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> tuple[str, dict | None]:
        """非流式调用，返回 (content, usage)；usage 可能为 None（字段缺失）。"""
        payload: dict = {
            "model": self._model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if any("json" in (m.get("content") or "").lower() for m in messages):
            payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return (
                data["choices"][0]["message"]["content"],
                self._usage_of(data, self._model),
            )

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        content, _ = await self.chat_with_usage(messages, temperature, max_tokens)
        return content

    async def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.6,
        max_tokens: int = 512,
    ) -> AsyncIterator[str]:
        async for kind, payload in self.stream_rich(messages, temperature, max_tokens):
            if kind == "delta":
                yield payload

    async def stream_rich(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.6,
        max_tokens: int = 512,
    ) -> AsyncIterator[tuple[str, object]]:
        """流式事件：("delta", text) / ("usage", usage)；usage 于尾部（stream_options 请求）。"""
        payload: dict = {
            "model": self._model,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        async with (
            httpx.AsyncClient(timeout=90) as client,
            client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    chunk = json.loads(body)
                except json.JSONDecodeError:
                    continue
                if chunk.get("usage"):  # 尾块：流式用量（DeepSeek 在 include_usage 时返回）
                    yield ("usage", self._usage_of(chunk, self._model))
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                if delta:
                    yield ("delta", delta)
