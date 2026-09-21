"""酒馆 DM 工具循环（迁移自 ai4u turn-runner 的跑团分支）。

- 最多 :data:`TOOL_MAX_ROUNDS` 轮可调工具，最后一轮 ``tool_choice="none"`` 强制正文
  （保证回合一定以叙述收尾）；
- 工具调用轮 ``max_tokens`` 放大到 :data:`TOOL_ROUND_MAX_TOKENS`（工具参数 JSON 较长）；
- 正文逐轮累积为一条 DM 消息；工具文本回填后继续生成（模型只拿文本讲故事）；
- 无工具能力的 LLM（Fake/降级）→ 退化为纯文本流式（不调工具，回合仍可玩）。

产出事件：``{"type": "delta", "text": ...}`` / ``{"type": "status", "stage": ...}``；
结果经 :attr:`DmTurnRunner.result` 领取（单次使用；与练习域 TurnRunner 同姿势）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.audio.base import LLMClient
from app.trpg.constants import DM_MAX_TOKENS, DM_TEMPERATURE, TOOL_MAX_ROUNDS, TOOL_ROUND_MAX_TOKENS
from app.trpg.tools import build_trpg_tools, execute_tool

logger = logging.getLogger("vocalverse")


@dataclass
class DmTurnResult:
    content: str
    usage: dict[str, Any] | None = None
    tool_rounds: int = 0
    statuses: list[str] = field(default_factory=list)


class DmTurnRunner:
    """单次 DM 回合：LLM 流式 + 工具回放（roll_dice / set_scene）。"""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm
        self.result: DmTurnResult | None = None

    async def run(
        self,
        messages: list[dict],
        campaign_id: int,
        *,
        temperature: float = DM_TEMPERATURE,
        max_tokens: int = DM_MAX_TOKENS,
    ):
        stream_with_tools = getattr(self._llm, "stream_with_tools", None)
        if stream_with_tools is None:
            # 降级：纯文本流（工具面关闭；回合仍可玩）
            parts: list[str] = []
            usage: dict[str, Any] | None = None
            async for kind, payload in _stream_rich(self._llm, messages, temperature, max_tokens):
                if kind == "usage":
                    usage = payload if isinstance(payload, dict) else None
                elif kind == "delta":
                    parts.append(str(payload))
                    yield {"type": "delta", "text": str(payload)}
            self.result = DmTurnResult(content="".join(parts), usage=usage, tool_rounds=0)
            return

        full_content = ""
        usage_total: dict[str, Any] | None = None
        tool_rounds = 0
        statuses: list[str] = []
        tools = build_trpg_tools()

        for round_index in range(TOOL_MAX_ROUNDS + 1):
            force_answer = round_index == TOOL_MAX_ROUNDS
            round_max = max_tokens if force_answer else max(max_tokens, TOOL_ROUND_MAX_TOKENS)
            tool_calls: list[dict[str, Any]] = []
            async for kind, payload in stream_with_tools(
                messages,
                tools=tools,
                tool_choice="none" if force_answer else "auto",
                temperature=temperature,
                max_tokens=round_max,
            ):
                if kind == "usage":
                    usage_total = _merge_usage(usage_total, payload)
                elif kind == "delta":
                    full_content += str(payload)
                    yield {"type": "delta", "text": str(payload)}
                elif kind == "tool_calls":
                    tool_calls = list(payload) if isinstance(payload, list) else []

            if not tool_calls:
                break

            tool_rounds += 1
            # 回放 assistant 工具调用消息（content 为空时不留占位文本污染上下文）
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call.get("id") or f"call_{tool_rounds}_{i}",
                            "type": "function",
                            "function": {
                                "name": call.get("name") or "",
                                "arguments": call.get("arguments") or "{}",
                            },
                        }
                        for i, call in enumerate(tool_calls)
                    ],
                }
            )
            for i, call in enumerate(tool_calls):
                call_id = call.get("id") or f"call_{tool_rounds}_{i}"
                outcome = await execute_tool(
                    str(call.get("name") or ""), str(call.get("arguments") or "{}"), campaign_id
                )
                if outcome.get("status_stage"):
                    statuses.append(str(outcome["status_stage"]))
                    yield {"type": "status", "stage": str(outcome["status_stage"])}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": str(outcome.get("text") or ""),
                    }
                )

        self.result = DmTurnResult(
            content=full_content, usage=usage_total, tool_rounds=tool_rounds, statuses=statuses
        )


async def _stream_rich(llm: LLMClient, messages: list[dict], temperature: float, max_tokens: int):
    """降级流式：优先 stream_rich（带 usage），否则 stream（仅正文）。"""
    rich = getattr(llm, "stream_rich", None)
    if rich is not None:
        async for item in rich(messages, temperature, max_tokens):
            yield item
        return
    async for chunk in llm.stream(messages, temperature, max_tokens):
        yield ("delta", chunk)


def _merge_usage(total: dict[str, Any] | None, usage: Any) -> dict[str, Any] | None:
    if not isinstance(usage, dict):
        return total
    if total is None:
        return dict(usage)
    merged = dict(total)
    merged["prompt_tokens"] = int(total.get("prompt_tokens") or 0) + int(
        usage.get("prompt_tokens") or 0
    )
    merged["completion_tokens"] = int(total.get("completion_tokens") or 0) + int(
        usage.get("completion_tokens") or 0
    )
    if usage.get("model"):
        merged["model"] = usage["model"]
    return merged
