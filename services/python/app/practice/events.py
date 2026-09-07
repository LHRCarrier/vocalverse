"""SSE 回合事件协议（docs/14 §3.3 定格；前端手写同名类型，不进 gen:api）。

事件边界语法：`\n\n` 分隔、单事件单 `data:` 行（JSON 序列化后无换行）。
心跳（R-18，2026-09-07 落地）：服务端每 ≤30s 推 `: ping` 注释行（docs/14 §3.3 /
审计 R-18：此前注释行协议已登记但**路由层零实现**，客户端也无 idle 超时）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

import pydantic

# 心跳注释行（协议：以 ':' 开头，前端解析器忽略但会重置 idle 计时）
PING_LINE = ": ping\n\n"


class TurnStart(pydantic.BaseModel):
    type: Literal["turn_start"] = "turn_start"
    turn_index: int
    reference_text: str | None = None
    question: str | None = None  # defense：本轮到 AI 提问


class UserTranscript(pydantic.BaseModel):
    """用户 ASR 转写回显（2026-09-08 新增：前端把用户说的话作为聊天气泡展示）。"""

    type: Literal["user_transcript"] = "user_transcript"
    turn_index: int
    text: str


class TextDelta(pydantic.BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class AudioChunk(pydantic.BaseModel):
    type: Literal["audio_chunk"] = "audio_chunk"
    url: str


class MetaBlock(pydantic.BaseModel):
    type: Literal["meta_block"] = "meta_block"
    grammar: dict | None = None
    coach_note: str | None = None
    corpus_hits: list[dict[str, Any]] = pydantic.Field(default_factory=list)
    difficulty_delta: int = 0
    conclude: bool = False
    content: dict | None = None  # ③ 语义子分：内容相关度 {score,note}（LLM 判定，不进总分）
    vocab: dict | None = None  # ③ 语义子分：词汇多样性 {score,note}（LLM 判定，不进总分）
    level: str | None = None  # defense：作答等级 green/yellow/red
    hits: dict | None = None  # defense：要点命中 {hits: [...], total: n}


class ScoreDelta(pydantic.BaseModel):
    type: Literal["score_delta"] = "score_delta"
    turn_index: int
    pronunciation: float | None = None
    fluency: float | None = None
    grammar: float | None = None


class StreamError(pydantic.BaseModel):
    type: Literal["error"] = "error"
    code: str
    recoverable: bool = True


class TurnEnd(pydantic.BaseModel):
    type: Literal["turn_end"] = "turn_end"
    turn_index: int
    score_status: Literal["ok", "pending", "unavailable"] = "ok"


class SessionEnd(pydantic.BaseModel):
    type: Literal["session_end"] = "session_end"
    summary: str | None = None
    report_id: int | None = None
    metrics: dict[str, Any] = pydantic.Field(default_factory=dict)


StreamEvent = (
    TurnStart
    | UserTranscript
    | TextDelta
    | AudioChunk
    | MetaBlock
    | ScoreDelta
    | StreamError
    | TurnEnd
    | SessionEnd
)


def sse_payload(event: StreamEvent) -> str:
    """序列化为 SSE data 行（事件为单行 JSON，无换行）。"""
    return f"data: {json.dumps(event.model_dump(exclude_none=True), ensure_ascii=False)}\n\n"


async def heartbeat_stream(inner, interval_s: float, serialize=sse_payload):
    """给异步事件生成器加心跳（R-18 / 审计 R-18）：静默 ≥ interval_s 时推 `: ping` 注释行。

    **关键设计（健壮性）**：决不用 `asyncio.wait_for(anext(...))` —— 超时会取消生成器
    内部正在等待的 LLM/ASR 协程（CancelledError 属 BaseException，直接杀死整个流）。
    改用 `asyncio.wait(FIRST_COMPLETED)` 竞争：
    - 事件先到 → 取消本轮 sleep、透传事件（顺序不变）；
    - sleep 先到（静默）→ **不取消** 仍挂起的 anext 任务（复用），只 yield 心跳行；
    生成器结束到（StopAsyncIteration）→ 正常返回。
    """
    it = inner.__aiter__()
    next_task: asyncio.Task | None = None
    while True:
        if next_task is None or next_task.done():
            next_task = asyncio.ensure_future(it.__anext__())
        sleep = asyncio.ensure_future(asyncio.sleep(interval_s))
        done, _ = await asyncio.wait({next_task, sleep}, return_when=asyncio.FIRST_COMPLETED)
        if next_task in done:
            sleep.cancel()
            try:
                event = next_task.result()
            except StopAsyncIteration:
                return
            next_task = None
            yield serialize(event)
        else:
            sleep.cancel()
            yield PING_LINE
