"""酒馆 SSE 事件协议（前端手写同名类型 apps/web/src/audio/trpg-sse-types.ts；不进 gen:api）。

与练习域 ``app/practice/events.py`` 的关系：**不复用其 9 类事件**（那套带 turn_index/
评分语义，被 dialog/defense/shadow/free-chat 四方共用，golden 语料锁定）；本协议只见
酒馆，序列化复用其 :func:`sse_payload` 与 :func:`heartbeat_stream`（通用工具）。
"""

from __future__ import annotations

from typing import Any, Literal

import pydantic


class TrpgReady(pydantic.BaseModel):
    """回合开始（会话 ensure 后立刻下发；前端据此对齐 campaign/首回合语义）。"""

    type: Literal["trpg_ready"] = "trpg_ready"
    campaign_id: int
    campaign_name: str
    is_first: bool


class UserTranscript(pydantic.BaseModel):
    """玩家语音 ASR 转写回显（打字轮不下发）。"""

    type: Literal["user_transcript"] = "user_transcript"
    text: str
    audio_url: str | None = None
    words: list[dict[str, Any]] | None = None


class TextDelta(pydantic.BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class TrpgStatus(pydantic.BaseModel):
    """工具执行状态（rolling=掷骰中 / scene=切场景中）。"""

    type: Literal["status"] = "status"
    stage: str


class AudioChunk(pydantic.BaseModel):
    """DM 回复逐句 TTS 音频（前端排队播放 + 卡拉OK式逐词高亮）。

    ``text``/``offset``（2026-09-21 加）：本句原文与它在 DM 整段 content 里的字符偏移——
    前端据此把播放进度映射到具体词（``text`` 长度 + ``offset`` 定界，避免前端二次分句漂移）。
    """

    type: Literal["audio_chunk"] = "audio_chunk"
    url: str
    duration: float | None = None
    text: str | None = None
    offset: int | None = None


class SystemCard(pydantic.BaseModel):
    """系统卡（开场/过场/判定）——与 trpg_messages.kind=system 同协议。"""

    type: Literal["system"] = "system"
    trpg_sys: Literal["open", "scene", "dice"]
    payload: dict[str, Any]


class TurnEnd(pydantic.BaseModel):
    type: Literal["turn_end"] = "turn_end"
    message_id: int
    usage: dict[str, Any] | None = None


class StreamError(pydantic.BaseModel):
    type: Literal["error"] = "error"
    code: str
    recoverable: bool = True


TrpgEvent = (
    TrpgReady
    | UserTranscript
    | TextDelta
    | TrpgStatus
    | AudioChunk
    | SystemCard
    | TurnEnd
    | StreamError
)
