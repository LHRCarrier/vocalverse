"""酒馆叙事事实提取器（迁移自 ai4u TrpgExtractorService，P2-27/39）。

- 触发：每 :data:`EXTRACT_EVERY_ROUNDS` 个玩家回合一次（user 消息计数），**后台 fire-and-forget**；
- light 语义：temperature 0.2 / max_tokens 400 / 最多 :data:`EXTRACT_MAX_OPS` 条；
- 失败静默降级（红线 8）：任何异常仅告警，绝不阻塞主对话；
- usage_log.source="factExtract" 分账（调优留数据）；
- 顺带执行待确认实体懒清理（P2-42）。
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import func, select

from app.agent.domains.usage import log_usage
from app.audio.base import LLMClient
from app.db import get_session_factory
from app.models.trpg import TrpgMessage
from app.trpg.constants import (
    DANGLING_WINDOW_MS,
    EXTRACT_EVERY_ROUNDS,
    EXTRACT_MAX_OPS,
    EXTRACT_RECENT_MESSAGES,
)
from app.trpg.facts import parse_fact_ops
from app.trpg.prompts import build_extractor_system_prompt, build_extractor_user_prompt
from app.trpg.state import cleanup_idle_entities, list_entities, list_facts, upsert_facts

logger = logging.getLogger("vocalverse")

#: 每 campaign 一把锁（进程内）：防并发重复提取
_locks: set[int] = set()


async def maybe_extract(campaign_id: int, llm: LLMClient) -> None:
    """回合后台调用；条件不满足直接返回。"""
    if campaign_id in _locks:
        return
    try:
        user_count = await asyncio.to_thread(_count_user_messages, campaign_id)
        if user_count == 0 or user_count % EXTRACT_EVERY_ROUNDS != 0:
            return

        _locks.add(campaign_id)
        try:
            recent = await asyncio.to_thread(_recent_messages, campaign_id)
            if not recent:
                return
            facts = await asyncio.to_thread(list_facts, campaign_id)
            entities = await asyncio.to_thread(list_entities, campaign_id)

            transcript = "\n".join(
                f"{'玩家' if m['role'] == 'user' else '剧情'}：{(m['content'] or '')[:300]}"
                for m in recent
            )
            fact_list = (
                "\n".join(
                    f"- {f['key']} = {f['value']}"
                    + (f"（{f['speaker'] or '?'} 声称）" if f["modality"] != "fact" else "")
                    for f in facts[:10]
                )
                or "（暂无）"
            )
            entity_list = "、".join(e["name"] for e in entities) or "（暂无）"

            extract_messages = [
                {"role": "system", "content": build_extractor_system_prompt()},
                {
                    "role": "user",
                    "content": build_extractor_user_prompt(fact_list, entity_list, transcript),
                },
            ]
            chat_with_usage = getattr(llm, "chat_with_usage", None)
            usage = None
            if chat_with_usage is not None:
                content, usage = await chat_with_usage(extract_messages, 0.2, 400)
            else:
                content = await llm.chat(extract_messages, temperature=0.2, max_tokens=400)
            if usage:
                log_usage("factExtract", usage, meta={"campaign_id": campaign_id})

            ops = parse_fact_ops(content)[:EXTRACT_MAX_OPS]
            if ops:
                source_message_id = next((m["id"] for m in recent if m["role"] == "user"), None)
                results = await asyncio.to_thread(upsert_facts, campaign_id, ops, source_message_id)
                applied = [r for r in results if r["action"] != "reject"]
                rejected = [r for r in results if r["action"] == "reject"]
                if applied:
                    logger.info(
                        "酒馆剧情事实提取已应用 %s 条（campaign=%s）", len(applied), campaign_id
                    )
                if rejected:
                    logger.warning(
                        "酒馆剧情事实提取拒绝 %s 条：%s",
                        len(rejected),
                        "，".join(f"{r.get('reason')}:{r['op'].key}" for r in rejected),
                    )

            # P2-42：待确认实体懒清理（每轮提取时顺带）
            await asyncio.to_thread(cleanup_idle_entities, campaign_id, float(DANGLING_WINDOW_MS))
        finally:
            _locks.discard(campaign_id)
    except Exception as exc:  # noqa: BLE001 - 提取失败绝不阻塞主对话
        logger.warning("酒馆剧情事实提取失败：%s", exc)


def _count_user_messages(campaign_id: int) -> int:
    db = get_session_factory()()
    try:
        return int(
            db.execute(
                select(func.count())
                .select_from(TrpgMessage)
                .where(
                    TrpgMessage.campaign_id == campaign_id,
                    TrpgMessage.role == "user",
                    TrpgMessage.kind == "text",
                )
            ).scalar_one()
        )
    finally:
        db.close()


def _recent_messages(campaign_id: int) -> list[dict]:
    db = get_session_factory()()
    try:
        rows = (
            db.execute(
                select(TrpgMessage)
                .where(TrpgMessage.campaign_id == campaign_id, TrpgMessage.kind == "text")
                .order_by(TrpgMessage.id.desc())
                .limit(EXTRACT_RECENT_MESSAGES)
            )
            .scalars()
            .all()
        )
        return [{"id": r.id, "role": r.role, "content": r.content} for r in reversed(rows)]
    finally:
        db.close()
