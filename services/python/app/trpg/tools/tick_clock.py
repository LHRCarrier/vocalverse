"""tick_clock：推进任务进度钟（系统算术 + 落表；满格提示 DM 可结算）。

设计（docs/56 §3 + docs/55 §2.1）：delta 只有 1~3（可负），系统夹取在 0..segments；
正向钟满格 = 目标达成，威胁钟满格 = 该发生的事发生了——两种都由 DM 在
「克服有意义的障碍 / 遭受重大挫折」时推进，禁止每回合 tick（prompt 规则 8 约束）。
"""

from __future__ import annotations

import asyncio

from app.trpg import progress as progress_rules
from app.trpg.constants import ENTITY_NAME_MAX
from app.trpg.state import get_quest_state, set_quest_facts
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

TICK_CLOCK_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "tick_clock",
        "description": (
            "推进任务进度钟（跑团专用）。只在「克服了有意义的障碍」或「遭受重大挫折」时调用，"
            "禁止每回合推进；系统负责算术与落表，你只需要在叙述里体现进展。"
            "quest 是任务名（与任务表一致）；delta 为 1~3（受挫/恶化用负数）；reason 简述本次变化。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "quest": {"type": "string", "description": "任务名（如 寻找失落的戒指）"},
                "delta": {
                    "type": "integer",
                    "description": "推进格数：1~3；受挫/威胁恶化用 -1~-3",
                },
                "reason": {"type": "string", "description": "本次推进的叙事理由（一句话）"},
            },
            "required": ["quest", "delta"],
        },
    },
}


async def handle(args: ToolArgs, campaign_id: int) -> ToolOutcome:
    quest = str(args.get("quest") or "").strip()[:ENTITY_NAME_MAX]
    if not quest:
        return {"text": "请提供任务名（quest 参数）。"}
    raw_delta = args.get("delta")
    if isinstance(raw_delta, bool) or not isinstance(raw_delta, (int, float)):
        return {"text": "delta 需为 -3~3 的非零整数。"}
    delta = int(raw_delta)
    if delta == 0 or abs(delta) > progress_rules.TICK_DELTA_MAX:
        return {"text": f"delta 需为 -3~3 的非零整数（收到 {delta}）。"}
    reason = str(args.get("reason") or "").strip()[:80] or None

    quest_state = await asyncio.to_thread(get_quest_state, campaign_id, quest)
    kind = progress_rules.normalize_kind(quest_state.get("kind"))
    tick = progress_rules.tick_progress(quest_state.get("progress"), delta)
    await asyncio.to_thread(
        set_quest_facts,
        campaign_id,
        quest,
        progress=tick.text,
        kind=kind,
        status=quest_state.get("status") or "active",
    )

    change = f"{delta:+d}"
    if tick.full:
        text = (
            f"任务「{quest}」进度 {tick.text}（{change}：{reason or '剧情推进'}），"
            "进度钟已满——可以在合适时机调用 complete_quest 结算。"
        )
    else:
        text = f"任务「{quest}」进度 {tick.text}（{change}：{reason or '剧情推进'}）。"
    return {
        "text": text,
        "quest": {
            "name": quest,
            "progress": tick.text,
            "segments": tick.segments,
            "kind": kind,
            "reason": reason,
            "full": tick.full,
        },
    }


register(ToolSpec(name="tick_clock", schema=TICK_CLOCK_SCHEMA, handler=handle))
