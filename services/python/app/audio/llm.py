"""DeepSeek LLM 客户端（OpenAI 兼容 /chat/completions）。

- chat：非流式（知识包生成/报告生成等一次性 JSON）；
- stream：流式（回复文本 + 尾部 [-META-] 标记块，docs/14 §3.4）；
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

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
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
            return data["choices"][0]["message"]["content"]

    async def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.6,
        max_tokens: int = 512,
    ) -> AsyncIterator[str]:
        payload: dict = {
            "model": self._model,
            "stream": True,
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
                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                if delta:
                    yield delta
