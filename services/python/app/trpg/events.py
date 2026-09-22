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


class PortraitShow(pydantic.BaseModel):
    """角色立绘展示（关键节点信号）。

    ``media_id``/``url``：docs/56 §4 起由 ``trpg_entities.portrait_media_id`` 回填
    （``/api/v1/media/{public_id}``）；未挂图 → null，前端按实体名命中内置素材。
    """

    type: Literal["portrait"] = "portrait"
    entity: str
    kind: str
    mood: str | None = None
    media_id: str | None = None
    url: str | None = None


class QuestUpdate(pydantic.BaseModel):
    """进度钟更新（docs/56 §5；``name`` 为工具 outcome 的键名别名）。

    ``progress`` 是 ``"3/6"`` 显示串；``segments`` 是总格数；``full`` = 已满格（可结算）。
    """

    type: Literal["quest"] = "quest"
    quest: str = pydantic.Field(validation_alias=pydantic.AliasChoices("quest", "name"))
    progress: str
    segments: int
    kind: Literal["positive", "threat"] = "positive"
    reason: str | None = None
    full: bool


class Ending(pydantic.BaseModel):
    """任务结算尾声（模板渲染，零 LLM；同一局可再开新篇章）。"""

    type: Literal["ending"] = "ending"
    quest: str
    outcome: Literal["strong", "weak", "miss"]
    title: str
    text: str
    epilogue: str


class CharacterState(pydantic.BaseModel):
    """人物在场状态变更（arriving=首次登场/正在赶来；departed=离场）。

    ``note`` 兼容工具 outcome 的 ``reason`` 键（入/出场理由，docs/56 §3）。
    """

    type: Literal["character"] = "character"
    name: str
    kind: str
    status: Literal["arriving", "active", "departed"]
    note: str | None = pydantic.Field(
        default=None, validation_alias=pydantic.AliasChoices("note", "reason")
    )


class EncounterState(pydantic.BaseModel):
    """遭遇状态（start/attack/turn/end 四相；字段按 kind 按需填充）。

    ``target_hp`` 兼容工具 outcome 的 ``targetHp`` 驼峰键（docs/56 §3）。
    """

    type: Literal["encounter"] = "encounter"
    kind: Literal["start", "attack", "turn", "end"]
    order: list[str] | None = None
    turn: int | None = None
    round: int | None = None
    attacker: str | None = None
    target: str | None = None
    hit: bool | None = None
    damage: int | None = None
    target_hp: int | None = pydantic.Field(
        default=None, validation_alias=pydantic.AliasChoices("target_hp", "targetHp")
    )
    outcome: str | None = None


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
    | PortraitShow
    | QuestUpdate
    | Ending
    | CharacterState
    | EncounterState
    | TurnEnd
    | StreamError
)
