"""DeepSeek LLM 客户端（OpenAI 兼容 /chat/completions）。

- chat：非流式（知识包生成/报告生成等一次性 JSON）；
- chat_with_usage：同 chat，额外返回 usage（用量记账 docs/26 §10.3②）；
- stream：流式（回复文本 + 尾部 [-META-] 标记块，docs/14 §3.4）；
- stream_rich：流式并产出 ("delta", text) / ("usage", usage) 事件（turn_runner 用量累积）；
- json 输出用 response_format=json_object（prompt 必须含 "json" 字样，POC-2 验证项）。

**trace 回填（docs/50 §7.2 的 P0-1）**：本文件是 ``ttft_ms`` 与 ``finish_reason`` 的**唯一
真实数据源**——首 token 时刻只有流式消费方能测到，finish_reason 只出现在最后一块 chunk 里。
两者通过 ``recorder.note_llm_result()`` **回填当前 LLM span**，而**不改动**
``("delta"|"usage", payload)`` 的事件形状（``turn_runner`` 与既有测试依赖该契约；
新增事件种类会让 dict payload 走进 ``MetaStreamSplitter.push()`` 拼接字符串 → TypeError）。
"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import AsyncIterator

import httpx

from app.audio.base import LLMClient

try:  # 观测层缺失（理论不可能）也不得让 LLM 客户端 import 失败
    from app.console.trace import recorder as _recorder
except Exception:  # pragma: no cover
    _recorder = None  # type: ignore[assignment]


def _note_request(model: str, messages: list[dict[str, str]]) -> None:
    if _recorder is not None:
        _recorder.note_llm_request(model, messages)


def _note_result(**kwargs) -> None:
    if _recorder is not None:
        _recorder.note_llm_result(**kwargs)


def _note_error(exc: BaseException) -> None:
    if _recorder is not None:
        _recorder.note_error(exc)


class DeepSeekLLMClient(LLMClient):
    def __init__(
        self, api_key: str, base_url: str = "https://api.deepseek.com", model: str = "deepseek-chat"
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        # py-05：连接池常驻（实例由 base.get_llm_client 缓存复用）——每次调用新建
        # AsyncClient = 每回合 2~3 次 TCP+TLS 握手重建；池化后 keep-alive 复用。
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(90.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

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

    @staticmethod
    def _finish_reason(chunk: dict) -> str | None:
        """从 chunk 里取 finish_reason（OpenAI 兼容：末块 choices[0].finish_reason）。"""
        choices = chunk.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            return None
        reason = choices[0].get("finish_reason")
        return str(reason) if reason else None

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
        _note_request(self._model, messages)
        started = time.perf_counter()
        try:
            resp = await self._client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
        except BaseException as exc:  # noqa: BLE001 - 记录后原样抛出（业务语义不变）
            _note_error(exc)
            raise
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = self._usage_of(data, self._model)
        reason = self._finish_reason(data)
        # 非流式没有"首 token 延迟"概念：ttft_ms 传 None，由 trace 侧留空而不是填 0
        # （填 0 会让 llm.ttft_ms 的 p95 被非流式调用污染成假值）。
        _note_result(
            finish_reason=reason,
            model=(usage or {}).get("model") or self._model,
            prompt_tokens=(usage or {}).get("prompt_tokens"),
            completion_tokens=(usage or {}).get("completion_tokens"),
            output_text=content,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return content, usage

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
        _note_request(self._model, messages)
        started = time.perf_counter()
        ttft_ms: int | None = None
        finish_reason: str | None = None
        acc: list[str] = []
        usage: dict | None = None
        try:
            async with self._client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as resp:
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    await _drain_error_body(exc)
                    raise
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
                    reason = self._finish_reason(chunk)
                    if reason:
                        finish_reason = reason
                    if chunk.get("usage"):  # 尾块：流式用量（DeepSeek 在 include_usage 时返回）
                        usage = self._usage_of(chunk, self._model)
                        yield ("usage", usage)
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        if ttft_ms is None:
                            # P0-1：首 token 时刻只能在这里测到（此前完全没记）
                            ttft_ms = int((time.perf_counter() - started) * 1000)
                        acc.append(delta)
                        yield ("delta", delta)
        except BaseException as exc:  # noqa: BLE001 - 含 CancelledError：先留痕再抛
            _note_error(exc)
            raise
        finally:
            # 正常结束 / 提前中断 / 取消 三种路径都要回填已测到的部分（不留半截数据）
            _note_result(
                ttft_ms=ttft_ms,
                finish_reason=finish_reason,
                model=(usage or {}).get("model") or self._model,
                prompt_tokens=(usage or {}).get("prompt_tokens"),
                completion_tokens=(usage or {}).get("completion_tokens"),
                output_text="".join(acc) if acc else None,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )


async def _drain_error_body(exc: httpx.HTTPStatusError) -> None:
    """流式响应在 raise_for_status 时正文尚未读取 → 主动读完，供错误详情落 trace。

    （``resp.text`` 对未读的流式响应会抛 ResponseNotRead；不读就没有"响应体"这个
    docs/50 §7.3 要求的错误详情。）
    """
    with contextlib.suppress(Exception):
        await exc.response.aread()  # 读不到就算了，状态码仍然有效
