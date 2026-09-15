"""听书预合成编排器（进程内 asyncio 任务 + DB 进度 + SSE 事件队列）。

借鉴（VoiceStudio jobs 思路，**只借模式不自研拷贝**，docs/46 红线）：
- 状态机 queued → running → done/failed/cancelled，任务持久化于 ``tts_tasks`` 表
  （断线重连/多进程/审计有据，docs/46 V-11）；
- 进度 = done/total 计数（SSE sentence_progress 事件 + GET /tts/tasks/{id} 快照双通道）；
- 启动扫描孤儿：running/queued → failed（崩溃残留不假转圈，同 sweep_orphans 语义）；
- 取消：进程内 asyncio.Task.cancel + cancel_reason/cancelled_at 落库。

并发：Semaphore(4) 逐句合成（edge-tts 网络往返 ~1.3s/句，4 并发 ≈ 3.3 句/s）；
单句失败仅计数（sentence 级容忍，不终止任务；失败句由「播放即取」端点实时补合成）。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.audio.base import TTSClient
from app.db import get_session_factory
from app.models import TtsTask
from app.reading.events import (
    ReadingStreamEvent,
    SentenceProgress,
    TaskDone,
    TaskStart,
)
from app.reading.split import ChapterSplit
from app.reading.tts_cache import reading_tts_cached

logger = logging.getLogger("vocalverse.reading.tts")

#: 并发合成上限（edge 网络往返 1.3s/句 × 4 ≈ 3 句/s，docs/06 §8 同口径）
MAX_CONCURRENCY = 4
#: DB 进度节流：每 N 句写一次（SSE 事件逐句推送不受此限）
PROGRESS_THROTTLE = 5

_TASKS: dict[int, asyncio.Task] = {}
_QUEUES: dict[int, asyncio.Queue[ReadingStreamEvent]] = {}


def _task_row(task_id: int) -> TtsTask | None:
    with get_session_factory()() as session:
        return session.get(TtsTask, task_id)


def _update_task(
    task_id: int,
    *,
    status: str | None = None,
    total: int | None = None,
    done: int | None = None,
    failed: int | None = None,
    error: dict[str, Any] | None = None,
    cancel_reason: str | None = None,
    finished: bool = False,
) -> None:
    with get_session_factory()() as session:
        row = session.get(TtsTask, task_id)
        if row is None:
            return
        if status is not None:
            row.status = status
        if total is not None:
            row.total = total
        if done is not None:
            row.done = done
        if failed is not None:
            row.failed_count = failed
        if error is not None:
            row.error = error
        if cancel_reason is not None:
            row.cancel_reason = cancel_reason
        if finished:
            row.finished_at = datetime.now(UTC)
        session.commit()


def sweep_orphans() -> int:
    """启动扫描：queued/running → failed（进程崩溃残留；返回清理数）。"""
    with get_session_factory()() as session:
        rows = list(
            session.execute(
                select(TtsTask).where(TtsTask.status.in_(("queued", "running")))
            ).scalars()
        )
        for row in rows:
            row.status = "failed"
            row.error = {"reason": "orphan_sweep", "message": "服务重启中断"}
            row.finished_at = datetime.now(UTC)
        if rows:
            session.commit()
        return len(rows)


def start_task(
    task_id: int,
    *,
    chapter_id: int,
    voice: str,
    rate: str,
    provider: str,
    split: ChapterSplit,
    tts: TTSClient,
) -> asyncio.Queue:
    """启动后台任务；**返回事件队列引用**（SSE 消费方必须持引用——任务可能瞬时完成、
    注册表已弹除，事后按 task_id 取会拿到空队列，docs/46 B-2 竞态修复）。"""
    queue: asyncio.Queue[ReadingStreamEvent] = asyncio.Queue()
    _QUEUES[task_id] = queue
    coro = _run(
        task_id,
        chapter_id=chapter_id,
        voice=voice,
        rate=rate,
        provider=provider,
        split=split,
        tts=tts,
    )
    task = asyncio.ensure_future(coro)
    _TASKS[task_id] = task
    return queue


def cancel_task(task_id: int, reason: str = "user") -> bool:
    """取消任务（进程内）：cancel 协程并落库；已终态任务返回 False。"""
    row = _task_row(task_id)
    if row is None or row.status in ("done", "failed", "cancelled"):
        return False
    _update_task(task_id, cancel_reason=reason, status="cancelled", finished=True)
    task = _TASKS.pop(task_id, None)
    if task is not None:
        task.cancel()
    return True


async def _run(
    task_id: int,
    *,
    chapter_id: int,
    voice: str,
    rate: str,
    provider: str,
    split: ChapterSplit,
    tts: TTSClient,
) -> None:
    queue = _QUEUES.get(task_id)
    sentences = split.sentences
    total = len(sentences)
    if queue is not None:
        queue.put_nowait(
            TaskStart(
                task_id=task_id, chapter_id=chapter_id, total=total, voice=voice, provider=provider
            )
        )
    _update_task(task_id, status="running", total=total, done=0, failed=0)
    done = failed = 0
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def one(idx: int, text: str) -> str:
        nonlocal done, failed
        async with sem:
            try:
                from app.audio.textproc.normalize import normalize_for_tts

                await reading_tts_cached(
                    tts, normalize_for_tts(text, language="en"), voice, rate, provider=provider
                )
                return "cached"
            except Exception as exc:
                logger.warning("听书句合成失败 idx=%s: %s", idx, exc)
                return "failed"

    try:
        # 分批并发（每批 MAX_CONCURRENCY 句），逐句推事件 + 节流写库
        for batch_start in range(0, total, MAX_CONCURRENCY):
            batch = sentences[batch_start : batch_start + MAX_CONCURRENCY]
            results = await asyncio.gather(
                *(one(batch_start + i, s.text) for i, s in enumerate(batch)),
                return_exceptions=True,
            )
            for i, res in enumerate(results):
                idx = batch_start + i
                status = "failed" if res in (None, "failed") else "done"
                if status == "failed":
                    failed += 1
                else:
                    done += 1
                if queue is not None:
                    queue.put_nowait(
                        SentenceProgress(
                            task_id=task_id, idx=idx, status=status, done=done, total=total
                        )
                    )
                if (batch_start + i + 1) % PROGRESS_THROTTLE == 0 or batch_start + i + 1 == total:
                    _update_task(task_id, done=done, failed=failed)
        _update_task(task_id, status="done", done=done, failed=failed, finished=True)
        if queue is not None:
            queue.put_nowait(
                TaskDone(task_id=task_id, status="done", done=done, failed=failed, total=total)
            )
    except asyncio.CancelledError:
        # 取消路径：状态已在 cancel_task 置 cancelled + 落库；事件补发
        if queue is not None:
            queue.put_nowait(
                TaskDone(task_id=task_id, status="cancelled", done=done, failed=failed, total=total)
            )
        raise
    except Exception as exc:  # noqa: BLE001 — 任务级兜底（不应发生；失败可见可查）
        logger.exception("听书任务异常 task_id=%s", task_id)
        _update_task(
            task_id,
            status="failed",
            error={"reason": "task_error", "message": str(exc)},
            finished=True,
        )
        if queue is not None:
            queue.put_nowait(
                TaskDone(task_id=task_id, status="failed", done=done, failed=failed, total=total)
            )
    finally:
        _TASKS.pop(task_id, None)
        _QUEUES.pop(task_id, None)


def task_events(task_id: int) -> asyncio.Queue[ReadingStreamEvent] | None:
    """任务事件队列（仅测试/断言用；SSE 消费方应持有 start_task 返回的引用）。"""
    return _QUEUES.get(task_id)


__all__ = [
    "start_task",
    "cancel_task",
    "sweep_orphans",
    "task_events",
    "MAX_CONCURRENCY",
]
