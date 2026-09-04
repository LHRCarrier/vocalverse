"""SSE 回合事件协议（docs/14 §3.3 定格；前端手写同名类型，不进 gen:api）。

事件边界语法：`\n\n` 分隔、单事件单 `data:` 行（JSON 序列化后无换行）。
心跳：服务端每 ≤30s 推 `: ping` 注释行（本节不做，由路由层实现）。
"""

from __future__ import annotations

import json
from typing import Any, Literal

import pydantic


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
