"""TTS 预合成预热（docs/06 §8「开场/常用句预合成」口径兑现，2026-09-09）。

已知文本（影子素材句）在用户请求前写入预合成缓存 → 影子跟读示范句 **0ms 命中**
（缓存键幂等 + 原子写 + 容量裁剪均由 tts_synthesize_cached 保障；预热本身禁止阻塞
调用方/启动流程）。

触发点（2026-09-21 酒馆迁移后）：
- 建会话预热（`schedule_texts_warm`，create_session）：影子会话逐句素材即刻预热；
- ~~启动预热（全部 published 场景）~~ 随英语场景对话移除（无启动期已知文本）。

语义：预热 = 只补缓存（命中即跳过）；并发限速 + 去重；单句失败仅日志（不抛）。
CI/测试：`settings.testing` 或 TTS 客户端缺失时静默跳过（零外部依赖，docs/06 §6）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from app.audio.base import get_tts_client
from app.audio.tts_cache import warm_tts_cache
from app.core.config import get_settings

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
