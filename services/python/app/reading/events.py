"""读书域 · 听书 SSE 事件模型（docs/45 §4 契约；与 practice turn SSE 独立，docs/46 B-2）。

事件序列：``task_start → sentence_progress* → task_done``；失败复用 ``error`` 事件
（recoverable 语义，同 practice/events.py StreamError 命名）。心跳由
``practice.events.heartbeat_stream`` 承担（docs/46 B-2：复用 sse_heartbeat_seconds）。
模型的负载经 ``sse_payload`` 序列化（exclude_none）——注意与 practice 的
StreamEvent 联合类型分开（本模块自有联合，事件字段超集互不干扰）。
"""

from __future__ import annotations

import json
from typing import Literal

import pydantic


class TaskStart(pydantic.BaseModel):
    type: Literal["task_start"] = "task_start"
    task_id: int
    chapter_id: int
    total: int
    voice: str
    provider: str


class SentenceProgress(pydantic.BaseModel):
    type: Literal["sentence_progress"] = "sentence_progress"
    task_id: int
    idx: int  # 句子下标（0 基）
    status: Literal["done", "cached", "failed"]
    done: int  # 已完成计数（含缓存命中）
    total: int


class TaskDone(pydantic.BaseModel):
    type: Literal["task_done"] = "task_done"
    task_id: int
    status: Literal["done", "failed", "cancelled"]
    done: int
    failed: int
    total: int


class ReadingStreamError(pydantic.BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    recoverable: bool = True


ReadingStreamEvent = TaskStart | SentenceProgress | TaskDone | ReadingStreamError


def sse_payload(event: ReadingStreamEvent) -> str:
    """序列化为 SSE data 行（单行 JSON，无换行；与 practice.events.sse_payload 同式）。"""
    return f"data: {json.dumps(event.model_dump(exclude_none=True), ensure_ascii=False)}\n\n"


__all__ = [
    "TaskStart",
    "SentenceProgress",
    "TaskDone",
    "ReadingStreamError",
    "ReadingStreamEvent",
    "sse_payload",
]
