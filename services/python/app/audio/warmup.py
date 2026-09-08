"""TTS 预合成预热（docs/06 §8「开场/常用句预合成」口径兑现，2026-09-09）。

已知文本（开场白/语料短语/影子素材句）在用户请求前写入预合成缓存 →
进场景点「播放开场白/听示范」、影子跟读示范句 **0ms 命中**（缓存键幂等 + 原子写 +
容量裁剪均由 tts_synthesize_cached 保障；预热本身禁止阻塞调用方/启动流程）。

触发点：
- 启动预热（`schedule_startup_warmup`，main.py lifespan）：全部 published 场景；
- 建会话预热（`schedule_session_warm`，create_session）：该会话内容即刻预热
  （不依赖启动预热时序；多副本/一键直达场景）。

语义：预热 = 只补缓存（命中即跳过）；并发限速 + 去重；单句失败仅日志（不抛）。
CI/测试：`settings.testing` 或 TTS 客户端缺失时静默跳过（零外部依赖，docs/06 §6）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from sqlalchemy import select

from app.audio.base import get_tts_client
from app.audio.tts import warm_tts_cache
from app.core.config import get_settings
from app.db import get_session_factory
from app.models import Scenario
from app.models.base import ContentStatus
from app.practice.corpus import parse_corpus
from app.practice.shadow import split_sentences

logger = logging.getLogger("vocalverse")

# 防 GC：后台预热任务持有引用（create_task 裸任务可能在完成前被回收）
_tasks: set[asyncio.Task] = set()


def collect_warm_texts(
    openings: Sequence[str | None], corpus_phrases: Sequence[str], sentences: Sequence[str]
) -> list[str]:
    """预热文本收集（保序去重，纯净字符串供缓存键；不含 SQL/IA 拼装）。"""
    seen: set[str] = set()
    out: list[str] = []
    for text in [*(t for t in openings if t), *corpus_phrases, *sentences]:
        t = (text or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def scenario_warm_texts(scenario: Scenario) -> list[str]:
    """单场景预热文本：开场白 + target_corpus 短语（语料句 = 提示/示范高频句）。"""
    return collect_warm_texts(
        [scenario.opening_line],
        [it.phrase for it in parse_corpus(scenario.target_corpus)],
        [],
    )


def _warm_all_texts() -> list[str]:
    """启动预热文本源：全部 published 场景（sync，线程内执行）。"""
    db = get_session_factory()()
    try:
        rows = (
            db.execute(select(Scenario).where(Scenario.status == ContentStatus.PUBLISHED))
            .scalars()
            .all()
        )
        seen: set[str] = set()
        out: list[str] = []
        for s in rows:
            for t in scenario_warm_texts(s):
                if t not in seen:
                    seen.add(t)
                    out.append(t)
        return out
    finally:
        db.close()


def schedule_texts_warm(texts: Sequence[str]) -> None:
    """建会话后预热（fire-and-forget；测试/无客户端/空文本跳过；缓存命中兜底重复预热）。"""
    settings = get_settings()
    if settings.testing or not settings.tts_cache_ttl_s or not texts:
        return
    client = get_tts_client()
    if client is None:
        return
    task = asyncio.create_task(
        warm_tts_cache(client, list(texts), settings.tts_voice, settings.tts_rate)
    )
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def schedule_startup_warmup() -> asyncio.Task | None:
    """启动预热（main.py lifespan；后台执行不阻塞就绪；返回任务引用或 None）。"""
    settings = get_settings()
    if settings.testing or not settings.tts_cache_ttl_s:
        return None
    client = get_tts_client()
    if client is None:
        return None

    async def _run() -> None:
        try:
            texts = await asyncio.to_thread(_warm_all_texts)
            if texts:
                await warm_tts_cache(client, texts, settings.tts_voice, settings.tts_rate)
                logger.info("TTS 预合成预热完成（%d 句）", len(texts))
        except Exception as exc:  # 预热失败不阻塞启动（docs/06 §8 同口径：告警不阻断）
            logger.warning("TTS 预热失败（不阻塞启动）: %s", exc)

    task = asyncio.create_task(_run())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def shadow_warm_texts(material) -> list[str]:
    """影子素材预热文本：逐句示范句（文本内容由调用方线程内读库）。"""
    return collect_warm_texts([], [], split_sentences(material.text_content))
